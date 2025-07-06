# bot.py - FIX: NameError for get_shard_data_for_date in admin editing

import os
import pytz
import logging
import traceback
import psycopg2
import psutil
import requests
from bs4 import BeautifulSoup
from flask import Flask, request
import telebot
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- Environment variables (Removed default values to enforce setup) ---
API_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
DB_URL = os.getenv("DATABASE_URL")
ADMIN_USER_ID = os.getenv("ADMIN_USER_ID")

# Ensure critical environment variables are set
if not API_TOKEN:
    logger.error("BOT_TOKEN environment variable not set. Exiting.")
    exit(1)
if not WEBHOOK_URL:
    logger.error("WEBHOOK_URL environment variable not set. Exiting.")
    exit(1)
if not DB_URL:
    logger.error("DATABASE_URL environment variable not set. Exiting.")
    exit(1)
if not ADMIN_USER_ID:
    logger.warning("ADMIN_USER_ID environment variable not set. Admin features will be disabled.")

# --- Constants ---
# General
MYANMAR_TIMEZONE_NAME = 'Asia/Yangon'
SKY_UTC_TIMEZONE = pytz.timezone('UTC') # Sky Time is UTC
MYANMAR_TIMEZONE = pytz.timezone(MYANMAR_TIMEZONE_NAME) # Specific timezone object for MT
TRAVELING_SPIRIT_DB_ID = 1
SKY_DAILY_RESET_HOUR_MT = 13 # 1 PM in 24-hour format
SKY_DAILY_RESET_MINUTE_MT = 30 # 30 minutes

# Bot Menu Buttons
MAIN_MENU_BUTTON = '🔙 Main Menu'
ADMIN_PANEL_BACK_BUTTON = '🔙 Admin Panel'
SKY_CLOCK_BUTTON = '🕒 Sky Clock'
TRAVELING_SPIRIT_BUTTON = '✨ Traveling Spirit'
WAX_EVENTS_BUTTON = '🕯 Wax Events'
SHARDS_BUTTON = '💎 Shard Events'
SETTINGS_BUTTON = '⚙️ Settings'
ADMIN_PANEL_BUTTON = '👤 Admin Panel'
GRANDMA_BUTTON = '🧓 Grandma'
TURTLE_BUTTON = '🐢 Turtle'
GEYSER_BUTTON = '🌋 Geyser'
CHANGE_TIME_FORMAT_BUTTON_PREFIX = '🕰 Change Time Format (Now:'
USER_STATS_BUTTON = '👥 User Stats'
BROADCAST_BUTTON = '📢 Broadcast'
MANAGE_REMINDERS_BUTTON = '⏰ Manage Reminders'
SYSTEM_STATUS_BUTTON = '📊 System Status'
FIND_USER_BUTTON = '🔍 Find User'
EDIT_TS_BUTTON = '✨ Edit Traveling Spirit'
TS_ACTIVE_BUTTON = '✅ Spirit is Active'
TS_INACTIVE_BUTTON = '❌ Spirit is Inactive'
ONE_TIME_REMINDER_BUTTON = '⏰ One Time Reminder'
DAILY_REMINDER_BUTTON = '🔄 Daily Reminder'

# Shard Navigation Buttons
PREVIOUS_DAY_BUTTON = '◀️ Previous Sky Day' # Updated text
NEXT_DAY_BUTTON = '▶️ Next Sky Day' # Updated text

# Admin Shard Editing Buttons
EDIT_SHARDS_BUTTON = '📝 Edit Shards'
SAVE_SHARD_CHANGES_BUTTON = '💾 Save Changes'
CANCEL_SHARD_EDIT_BUTTON = '❌ Cancel Edit'

# Global dictionary to hold shard edit sessions for each admin user
user_shard_edit_sessions = {}


bot = telebot.TeleBot(API_TOKEN, threaded=False)
app = Flask(__name__)
scheduler = BackgroundScheduler()
scheduler.start()

# Track bot start time for uptime
start_time = datetime.now()

# ========================== DATABASE ===========================
def get_db() -> psycopg2.extensions.connection:
    """Establishes and returns a database connection."""
    try:
        conn = psycopg2.connect(DB_URL, sslmode='require')
        return conn
    except Exception as e:
        logger.error(f"Database connection failed: {str(e)}")
        raise

def init_db():
    """Initializes database tables if they do not exist."""
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                logger.info("Creating table: users")
                cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY ID,
                    chat_id BIGINT NOT NULL,
                    timezone TEXT NOT NULL,
                    time_format TEXT DEFAULT '12hr',
                    last_interaction TIMESTAMP DEFAULT NOW()
                );
                """)

                logger.info("Creating table: reminders")
                cur.execute("""
                CREATE TABLE IF NOT EXISTS reminders (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT REFERENCES users(user_id),
                    chat_id BIGINT,
                    event_type TEXT,
                    event_time_utc TIMESTAMP,
                    trigger_time TIMESTAMP,
                    notify_before INT,
                    is_daily BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT NOW()
                );
                """)

                logger.info("Creating table: traveling_spirit")
                cur.execute("""
                CREATE TABLE IF NOT EXISTS traveling_spirit (
                    id INT PRIMARY KEY DEFAULT 1,
                    is_active BOOLEAN DEFAULT FALSE,
                    name TEXT,
                    dates TEXT,
                    image_file_id TEXT,
                    items TEXT,
                    item_tree_image_file_id TEXT,
                    item_tree_caption TEXT,
                    last_updated TIMESTAMP DEFAULT NOW()
                );
                """)

                logger.info("Ensuring default row exists in traveling_spirit")
                cur.execute("INSERT INTO traveling_spirit (id) VALUES (1) ON CONFLICT (id) DO NOTHING;")

                logger.info("Creating table: shard_events")
                cur.execute("""
                CREATE TABLE IF NOT EXISTS shard_events (
                    date DATE PRIMARY KEY,
                    shard_color TEXT,
                    realm TEXT,
                    location TEXT,
                    reward TEXT,
                    memory TEXT,
                    first_shard_mt TEXT,
                    second_shard_mt TEXT,
                    last_shard_mt TEXT,
                    eruption_status TEXT
                );
                """)
                
                conn.commit()
                logger.info("Database initialization complete.")
    except Exception as e:
        logger.error(f"DATABASE INITIALIZATION FAILED: {e}", exc_info=True)
        raise e

# ======================== WEB SCRAPING UTILITY ============================
def scrape_traveling_spirit() -> dict:
    """
    Placeholder for scraping function. Currently returns inactive status.
    When implemented, it should scrape the wiki for Traveling Spirit data.
    """
    URL = "https://sky-children-of-the-light.fandom.com/wiki/Traveling_Spirits"
    headers = {
        'User-Agent': 'SkyClockBot/Final-Diagnostic (Python/Requests;)'
    }
    
    try:
        response = requests.get(URL, headers=headers, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')

        logger.info(f"DIAGNOSTIC HTML: {soup.prettify()[:2000]}")

        return {"is_active": False}

    except Exception as e:
        logger.error(f"FINAL DIAGNOSTIC SCRAPER FAILED: {e}", exc_info=True)
        return {"is_active": False, "error": "A critical error occurred during final diagnostics."}

# ======================== UTILITIES ============================
def format_time(dt: datetime, fmt: str) -> str:
    """Formats a datetime object to 12hr or 24hr string."""
    return dt.strftime('%I:%M %p') if fmt == '12hr' else dt.strftime('%H:%M')

def get_user(user_id: int) -> tuple | None:
    """Retrieves user timezone and time format from the database."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT timezone, time_format FROM users WHERE user_id = %s", (user_id,))
            return cur.fetchone()

def set_timezone(user_id: int, chat_id: int, tz: str) -> bool:
    """Sets or updates a user's timezone in the database."""
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO users (user_id, chat_id, timezone, last_interaction) 
                    VALUES (%s, %s, %s, NOW())
                    ON CONFLICT (user_id) DO UPDATE 
                    SET chat_id = EXCLUDED.chat_id, timezone = EXCLUDED.timezone, last_interaction = NOW();
                """, (user_id, chat_id, tz))
                conn.commit()
        logger.info(f"Timezone set for user {user_id}: {tz}")
        return True
    except Exception as e:
        logger.error(f"Failed to set timezone for user {user_id}: {str(e)}")
        logger.error(traceback.format_exc())
        return False

def set_time_format(user_id: int, fmt: str):
    """Sets a user's preferred time format."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE users 
                SET time_format = %s, last_interaction = NOW() 
                WHERE user_id = %s
            """, (fmt, user_id))
            conn.commit()

def update_last_interaction(user_id: int) -> bool:
    """Updates the last interaction timestamp for a user."""
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE users 
                    SET last_interaction = NOW() 
                    WHERE user_id = %s
                """, (user_id,))
                conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error updating last interaction for {user_id}: {str(e)}")
        return False

# ===================== ADMIN UTILITIES =========================
def is_admin(user_id: int) -> bool:
    """Checks if a given user ID is the admin ID."""
    return str(user_id) == ADMIN_USER_ID

# ===================== NAVIGATION HELPERS ======================
def send_main_menu(chat_id: int, user_id: int | None = None):
    """Sends the main menu keyboard."""
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(SKY_CLOCK_BUTTON, TRAVELING_SPIRIT_BUTTON)
    markup.row(WAX_EVENTS_BUTTON, SHARDS_BUTTON)
    markup.row(SETTINGS_BUTTON)
    if user_id and is_admin(user_id):
        markup.row(ADMIN_PANEL_BUTTON)
    bot.send_message(chat_id, "Main Menu:", reply_markup=markup)

def send_wax_menu(chat_id: int):
    """Sends the wax events menu keyboard."""
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(GRANDMA_BUTTON, TURTLE_BUTTON, GEYSER_BUTTON)
    markup.row(MAIN_MENU_BUTTON)
    bot.send_message(chat_id, "Wax Events:", reply_markup=markup)

def send_settings_menu(chat_id: int, current_format: str):
    """Sends the settings menu keyboard."""
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(f'{CHANGE_TIME_FORMAT_BUTTON_PREFIX} {current_format})')
    markup.row(MAIN_MENU_BUTTON)
    bot.send_message(chat_id, "Settings:", reply_markup=markup)

def send_admin_menu(chat_id: int):
    """Sends the admin panel menu keyboard."""
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(USER_STATS_BUTTON, BROADCAST_BUTTON)
    markup.row(MANAGE_REMINDERS_BUTTON, EDIT_TS_BUTTON)
    markup.row(EDIT_SHARDS_BUTTON, FIND_USER_BUTTON)
    markup.row(SYSTEM_STATUS_BUTTON)
    markup.row(MAIN_MENU_BUTTON)
    bot.send_message(chat_id, "Admin Panel:", reply_markup=markup)

# ======================= GLOBAL HANDLERS =======================
@bot.message_handler(func=lambda msg: msg.text == MAIN_MENU_BUTTON)
def handle_back_to_main(message: telebot.types.Message):
    """Handles navigation back to the main menu."""
    update_last_interaction(message.from_user.id)
    send_main_menu(message.chat.id, message.from_user.id)

@bot.message_handler(func=lambda msg: msg.text == ADMIN_PANEL_BACK_BUTTON)
def handle_back_to_admin(message: telebot.types.Message):
    """Handles navigation back to the admin panel."""
    update_last_interaction(message.from_user.id)
    if is_admin(message.from_user.id):
        send_admin_menu(message.chat.id)

# ======================= START FLOW ============================
@bot.message_handler(commands=['start'])
def start(message: telebot.types.Message):
    """Handles the /start command, initiating timezone setup."""
    try:
        update_last_interaction(message.from_user.id)
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.row(f'🇲🇲 Set to {MYANMAR_TIMEZONE_NAME} Time')
        bot.send_message(
            message.chat.id,
            f"Hello {message.from_user.first_name} 👋\nWelcome to Sky Clock Bot!\n\n"
            "Please type your timezone (e.g. Asia/Yangon), or choose an option:",
            reply_markup=markup
        )
        bot.register_next_step_handler(message, save_timezone)
    except Exception as e:
        logger.error(f"Error in /start: {str(e)}")
        bot.send_message(message.chat.id, "⚠️ Error in /start command")

def save_timezone(message: telebot.types.Message):
    """Handles saving the user's chosen timezone."""
    user_id, chat_id = message.from_user.id, message.chat.id
    try:
        if message.text == f'🇲🇲 Set to {MYANMAR_TIMEZONE_NAME} Time':
            tz = MYANMAR_TIMEZONE_NAME
        else:
            try:
                pytz.timezone(message.text)
                tz = message.text
            except pytz.UnknownTimeZoneError:
                bot.send_message(chat_id, "❌ Invalid timezone. Please try again:")
                return bot.register_next_step_handler(message, save_timezone)

        if set_timezone(user_id, chat_id, tz):
            bot.send_message(chat_id, f"✅ Timezone set to: {tz}")
            send_main_menu(chat_id, user_id)
        else:
            bot.send_message(chat_id, "⚠️ Failed to save timezone to database. Please try /start again.")
    except Exception as e:
        logger.error(f"Error saving timezone: {str(e)}")
        bot.send_message(chat_id, "⚠️ Unexpected error saving timezone. Please try /start again.")

# ===================== MAIN MENU HANDLERS ======================
@bot.message_handler(func=lambda msg: msg.text == SKY_CLOCK_BUTTON)
def sky_clock(message: telebot.types.Message):
    """Displays current Sky Time and user's local time."""
    update_last_interaction(message.from_user.id)
    user = get_user(message.from_user.id)
    if not user:
        bot.send_message(message.chat.id, "Please set your timezone first with /start")
        return
    
    tz, fmt = user
    user_tz = pytz.timezone(tz)
    now = datetime.now()
    local_time = now.astimezone(user_tz)
    sky_time = now.astimezone(SKY_UTC_TIMEZONE)
    time_diff = local_time - sky_time
    hours, rem = divmod(abs(time_diff.total_seconds()), 3600)
    minutes = rem // 60
    direction = "ahead of" if time_diff.total_seconds() > 0 else "behind"
    
    text = (f"🌥 Sky Time: {format_time(sky_time, fmt)}\n"
            f"🌍 Your Time: {format_time(local_time, fmt)}\n"
            f"⏱ You are {int(hours)}h {int(minutes)}m {direction} Sky Time")
    bot.send_message(message.chat.id, text)

@bot.message_handler(commands=['ts'])
@bot.message_handler(func=lambda msg: msg.text == TRAVELING_SPIRIT_BUTTON)
def show_traveling_spirit(message: telebot.types.Message):
    """Displays information about the current Traveling Spirit."""
    update_last_interaction(message.from_user.id)
    
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                # Updated column names to match the new schema
                cur.execute("""
                    SELECT is_active, name, dates, image_file_id, items, 
                           item_tree_image_file_id, item_tree_caption 
                    FROM traveling_spirit WHERE id = %s
                """, (TRAVELING_SPIRIT_DB_ID,))
                ts_data_row = cur.fetchone()

        if not ts_data_row:
            raise ValueError("Traveling spirit data not found in database.")

        is_active, name, dates, image_file_id, items_text, tree_image_file_id, tree_caption = ts_data_row

        if is_active:
            main_caption = (
                f"**A Traveling Spirit is here!** ✨\n\n"
                f"The **{name}** has arrived!\n\n"
                f"**Dates:** {dates}\n"
                f"**Location:** You can find them in the Home space!\n\n"
                f"**Items Available:**\n{items_text or ''}"
            )
            try:
                if image_file_id:
                    bot.send_photo(message.chat.id, image_file_id, caption=main_caption, parse_mode='Markdown')
                else:
                    bot.send_message(message.chat.id, main_caption, parse_mode='Markdown')
            except Exception as e:
                logger.error(f"Could not send main TS photo by file_id. Error: {e}")
                bot.send_message(message.chat.id, main_caption, parse_mode='Markdown')

            try:
                if tree_image_file_id:
                    bot.send_photo(message.chat.id, tree_image_file_id, caption=tree_caption, parse_mode='Markdown')
            except Exception as e:
                logger.error(f"Could not send item tree photo by file_id. Error: {e}")
        else:
            bot.send_message(message.chat.id, "The Traveling Spirit has departed for now, or has not been announced yet.")

    except Exception as e:
        logger.error(f"Failed to fetch TS data from DB: {e}")
        bot.send_message(message.chat.id, "Sorry, I couldn't retrieve the Traveling Spirit information right now.")

@bot.message_handler(func=lambda msg: msg.text == WAX_EVENTS_BUTTON)
def wax_menu(message: telebot.types.Message):
    """Displays the wax events menu."""
    update_last_interaction(message.from_user.id)
    send_wax_menu(message.chat.id)

@bot.message_handler(func=lambda msg: msg.text == SETTINGS_BUTTON)
def settings_menu(message: telebot.types.Message):
    """Displays the settings menu."""
    update_last_interaction(message.from_user.id)
    user = get_user(message.from_user.id)
    if not user:
        bot.send_message(message.chat.id, "Please set your timezone first with /start")
        return
        
    _, fmt = user
    send_settings_menu(message.chat.id, fmt)


# --- SHARD EVENTS IMPLEMENTATION ---

@bot.message_handler(func=lambda msg: msg.text == SHARDS_BUTTON)
def handle_shard_events(message: telebot.types.Message):
    """Handles the Shard Events button, displaying today's shard info."""
    update_last_interaction(message.from_user.id)
    
    user_info = get_user(message.from_user.id)
    if not user_info:
        bot.send_message(message.chat.id, "Please set your timezone first with /start")
        return

    tz, _ = user_info
    user_tz = pytz.timezone(tz)
    
    # Get the current Sky Game Day's primary calendar date for display
    # This will be the reference date for navigation
    current_calendar_date_in_user_tz = datetime.now(user_tz).date()
    
    display_shard_info(message.chat.id, message.from_user.id, current_calendar_date_in_user_tz)


def get_sky_game_day_window_for_query_date(query_calendar_date: datetime.date) -> tuple[datetime.date, datetime.date]:
    """
    Determines the calendar date range that constitutes the 'Sky Game Day'
    based on a 1:30 PM MMT reset, relative to the query_calendar_date.
    Returns (start_calendar_date_to_query, end_calendar_date_to_query) for DB query.
    
    A Sky Game Day for `query_calendar_date` is defined as:
    from query_calendar_date 1:30 PM MMT to (query_calendar_date + 1 day) 1:29:59 PM MMT.
    To ensure we fetch all shards for this window, we query for `query_calendar_date`
    and `query_calendar_date + 1 day` from the database.
    """
    return query_calendar_date, query_calendar_date + timedelta(days=1)


def get_shard_data_for_sky_day_window(start_calendar_date: datetime.date, end_calendar_date: datetime.date) -> list[dict]:
    """
    Fetches shard data for a range of calendar dates from the database.
    Returns a list of shard data dictionaries.
    """
    all_shard_data_in_window = []
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                # Fetch data for both calendar dates that might comprise a Sky Game Day
                cur.execute("""
                    SELECT date, shard_color, realm, location, reward, memory,
                           first_shard_mt, second_shard_mt, last_shard_mt, eruption_status
                    FROM shard_events
                    WHERE date BETWEEN %s AND %s
                    ORDER BY date, first_shard_mt -- Order by date and then time to process correctly
                """, (start_calendar_date, end_calendar_date))
                
                rows = cur.fetchall()
                for row in rows:
                    all_shard_data_in_window.append({
                        "Date": row[0].strftime("%Y-%m-%d"), # date object needs formatting
                        "Shard Color": row[1],
                        "Realm": row[2],
                        "Location": row[3],
                        "Reward": row[4],
                        "Memory": row[5],
                        "First Shard (MT)": row[6],
                        "Second Shard (MT)": row[7],
                        "Last Shard (MT)": row[8],
                        "Eruption Status": row[9]
                    })
        return all_shard_data_in_window
    except Exception as e:
        logger.error(f"Error fetching shard data for window {start_calendar_date} to {end_calendar_date}: {e}", exc_info=True)
        return []


def get_shard_data_for_single_calendar_date(target_date: datetime.date) -> dict | None:
    """
    Fetches shard data for a specific single calendar date from the database.
    Used by the admin editing flow.
    """
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT shard_color, realm, location, reward, memory,
                           first_shard_mt, second_shard_mt, last_shard_mt, eruption_status
                    FROM shard_events
                    WHERE date = %s
                """, (target_date,))
                row = cur.fetchone()
                if row:
                    return {
                        "Date": target_date.strftime("%Y-%m-%d"),
                        "Shard Color": row[0],
                        "Realm": row[1],
                        "Location": row[2],
                        "Reward": row[3],
                        "Memory": row[4],
                        "First Shard (MT)": row[5],
                        "Second Shard (MT)": row[6],
                        "Last Shard (MT)": row[7],
                        "Eruption Status": row[8]
                    }
                return None
    except Exception as e:
        logger.error(f"Error fetching shard data for single calendar date {target_date}: {e}", exc_info=True)
        return None


def display_shard_info(chat_id: int, user_id: int, query_calendar_date: datetime.date, message_id_to_edit: int | None = None):
    """
    Displays shard information for a specific 'Sky Game Day' based on query_calendar_date.
    The Sky Game Day associated with query_calendar_date starts from 1:30 PM MMT on query_calendar_date
    and runs until 1:29:59 PM MMT the next calendar day.
    """
    user_info = get_user(user_id)
    if not user_info:
        bot.send_message(chat_id, "Please set your timezone first with /start")
        return

    tz, fmt = user_info
    user_tz = pytz.timezone(tz)
    now_user_in_user_tz = datetime.now(user_tz) # Current time in user's display timezone
    now_in_mmt = datetime.now(MYANMAR_TIMEZONE) # Current time in MMT for comparison

    # Determine the calendar dates that make up the relevant Sky Game Day
    fetch_start_date, fetch_end_date = get_sky_game_day_window_for_query_date(query_calendar_date)
    
    # Get all shard data for these calendar dates
    raw_shard_data_list = get_shard_data_for_sky_day_window(fetch_start_date, fetch_end_date)

    # Define the start and end of the 'Sky Game Day' window in MMT
    sky_day_start_datetime_mmt = MYANMAR_TIMEZONE.localize(
        datetime(query_calendar_date.year, query_calendar_date.month, query_calendar_date.day, SKY_DAILY_RESET_HOUR_MT, SKY_DAILY_RESET_MINUTE_MT, 0)
    )
    sky_day_end_datetime_mmt = sky_day_start_datetime_mmt + timedelta(days=1) - timedelta(seconds=1)

    # Filter and sort shards that fall within this specific Sky Game Day window
    relevant_shards_for_sky_day = []
    for shard_data in raw_shard_data_list:
        if shard_data.get("Eruption Status") == "Erupted":
            try:
                # Construct datetime object for the shard's START time in MMT from its stored date and time
                shard_event_calendar_date_obj = datetime.strptime(shard_data["Date"], "%Y-%m-%d").date() # Actual calendar date from DB
                mt_time_str = shard_data.get("First Shard (MT)").split('-')[0].strip()
                
                shard_start_datetime_mt_full = MYANMAR_TIMEZONE.localize(
                    datetime(shard_event_calendar_date_obj.year, shard_event_calendar_date_obj.month, shard_event_calendar_date_obj.day, 
                             int(mt_time_str.split(':')[0]), int(mt_time_str.split(':')[1]), 0)
                )

                # Check if this shard's start time falls within the current Sky Game Day window
                # This handles shards that started before/after the 1:30 PM cut-off
                if sky_day_start_datetime_mmt <= shard_start_datetime_mt_full <= sky_day_end_datetime_mmt:
                    relevant_shards_for_sky_day.append(shard_data)
            except (ValueError, TypeError) as e:
                logger.warning(f"Skipping malformed shard time for filter: {shard_data.get('First Shard (MT)')}. Error: {e}")

    # Sort relevant shards by their full MMT start datetime
    def get_sort_key(shard_data):
        date_obj = datetime.strptime(shard_data["Date"], "%Y-%m-%d").date()
        time_str = shard_data.get("First Shard (MT)").split('-')[0].strip()
        return MYANMAR_TIMEZONE.localize(
            datetime(date_obj.year, date_obj.month, date_obj.day, 
                     int(time_str.split(':')[0]), int(time_str.split(':')[1]), 0)
        )

    relevant_shards_for_sky_day.sort(key=get_sort_key)


    message_text = ""
    message_text += f"💎 **Shard Eruptions for Sky Day starting {query_calendar_date.strftime('%Y-%m-%d (%A)')} (1:30 PM MMT Reset):**\n\n"

    if relevant_shards_for_sky_day:
        for shard_data in relevant_shards_for_sky_day:
            shard_color = shard_data.get("Shard Color")
            realm = shard_data.get("Realm")
            location = shard_data.get("Location")
            reward = shard_data.get("Reward")
            memory = shard_data.get("Memory")
            
            # Use the actual shard's calendar date for its time display
            shard_event_calendar_date_obj = datetime.strptime(shard_data["Date"], "%Y-%m-%d").date() 
            mt_time_range = shard_data.get("First Shard (MT)")
            mt_time_str = mt_time_range.split('-')[0].strip() # Get start time of range

            try:
                # Construct the full MMT datetime for the shard
                shard_start_datetime_mt_full = MYANMAR_TIMEZONE.localize(
                    datetime(shard_event_calendar_date_obj.year, shard_event_calendar_date_obj.month, shard_event_calendar_date_obj.day, 
                             int(mt_time_str.split(':')[0]), int(mt_time_str.split(':')[1]), 0)
                )
                # Convert to user's local timezone for display
                shard_start_datetime_user_display = shard_start_datetime_mt_full.astimezone(user_tz)

                status_emoji = ""
                status_text = ""
                # Compare shard time (full MT datetime) to current time in MMT
                if shard_start_datetime_mt_full < now_in_mmt:
                    status_emoji = "✅"
                    status_text = "Ended"
                else:
                    status_emoji = "⏳"
                    status_text = "Upcoming"
                    
                message_text += (
                    f"--- {shard_color if shard_color is not None else 'N/A'} Shard ---\n"
                    f"⏰ {format_time(shard_start_datetime_user_display, fmt)} {status_emoji} ({status_text})\n"
                    f"🗺️ Realm: {realm if realm is not None else 'N/A'}\n"
                    f"📍 Location: {location if location is not None else 'N/A'}\n"
                    f"🎁 Reward: {reward if reward is not None else 'N/A'}\n"
                    f"🧠 Memory: {memory if memory is not None else 'N/A'}\n\n"
                )
            except (ValueError, TypeError) as e:
                logger.warning(f"Could not parse or process shard time for display: {mt_time_range}. Error: {e}")
                message_text += (
                    f"--- {shard_color if shard_color is not None else 'N/A'} Shard ---\n"
                    f"⏰ {mt_time_range} ⚠️ (Time Format Error)\n"
                    f"🗺️ Realm: {realm if realm is not None else 'N/A'}\n"
                    f"📍 Location: {location if location is not None else 'N/A'}\n"
                    f"🎁 Reward: {reward if reward is not None else 'N/A'}\n"
                    f"🧠 Memory: {memory if memory is not None else 'N/A'}\n\n"
                )
    else:
        message_text += "No major shard eruption expected or data not available for this Sky Day."
    
    message_text += "\n_Times shown are for the start of the shard window in Myanmar Time._"

    # Navigation buttons
    markup = telebot.types.InlineKeyboardMarkup()
    prev_date = query_calendar_date - timedelta(days=1)
    next_date = query_calendar_date + timedelta(days=1)

    markup.row(
        telebot.types.InlineKeyboardButton(PREVIOUS_DAY_BUTTON, callback_data=f"shard_date_{prev_date.strftime('%Y-%m-%d')}"),
        telebot.types.InlineKeyboardButton(NEXT_DAY_BUTTON, callback_data=f"shard_date_{next_date.strftime('%Y-%m-%d')}")
    )
    markup.row(telebot.types.InlineKeyboardButton(MAIN_MENU_BUTTON, callback_data="main_menu_from_shard"))

    if message_id_to_edit:
        try:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id_to_edit,
                text=message_text,
                reply_markup=markup,
                parse_mode='Markdown'
            )
        except telebot.apihelper.ApiTelegramException as e:
            if "message is not modified" in str(e).lower():
                logger.info("Shard message not modified, skipping edit.")
            else:
                logger.error(f"Error editing shard message: {e}", exc_info=True)
                bot.send_message(chat_id, "⚠️ Error updating shard info. Please try again.")
    else:
        bot.send_message(chat_id, message_text, reply_markup=markup, parse_mode='Markdown')


@bot.callback_query_handler(func=lambda call: call.data.startswith("shard_date_"))
def handle_shard_date_navigation(call: telebot.types.CallbackQuery):
    """Handles navigation between shard dates."""
    update_last_interaction(call.from_user.id)
    try:
        target_date_str = call.data.split("_")[2]
        target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
        
        # Use edit_message_text to update the current message instead of sending a new one
        display_shard_info(call.message.chat.id, call.from_user.id, target_date, call.message.message_id)
    except Exception as e:
        logger.error(f"Error handling shard date navigation: {e}", exc_info=True)
        bot.send_message(call.message.chat.id, "⚠️ Error navigating shard dates. Please try again.")
    bot.answer_callback_query(call.id) # Acknowledge the callback

@bot.callback_query_handler(func=lambda call: call.data == "main_menu_from_shard")
def handle_main_menu_from_shard(call: telebot.types.CallbackQuery):
    """Handles returning to the main menu from shard display."""
    update_last_interaction(call.from_user.id)
    bot.delete_message(call.message.chat.id, call.message.message_id) # Delete previous message
    send_main_menu(call.message.chat.id, call.from_user.id)
    bot.answer_callback_query(call.id)


# ====================== WAX EVENT HANDLERS =====================
@bot.message_handler(func=lambda msg: msg.text in [GRANDMA_BUTTON, TURTLE_BUTTON, GEYSER_BUTTON])
def handle_event(message: telebot.types.Message):
    """Handles wax event inquiries (Grandma, Turtle, Geyser)."""
    update_last_interaction(message.from_user.id)
    mapping = {
        GRANDMA_BUTTON: ('Grandma', 'every 2 hours at :05', 'even'),
        TURTLE_BUTTON: ('Turtle', 'every 2 hours at :20', 'even'),
        GEYSER_BUTTON: ('Geyser', 'every 2 hours at :35', 'odd')
    }
    
    event_name, event_schedule, hour_type = mapping[message.text]
    user = get_user(message.from_user.id)
    if not user:
        bot.send_message(message.chat.id, "Please set your timezone first with /start")
        return
        
    tz, fmt = user
    user_tz = pytz.timezone(tz)
    now_user = datetime.now(user_tz)

    # Generate all event times for today in user's timezone
    today_user = now_user.replace(hour=0, minute=0, second=0, microsecond=0)
    event_times = []
    for hour in range(24):
        if hour_type == 'even' and hour % 2 == 0:
            event_times.append(today_user.replace(hour=hour, minute=int(event_schedule.split(':')[1])))
        elif hour_type == 'odd' and hour % 2 == 1:
            event_times.append(today_user.replace(hour=hour, minute=int(event_schedule.split(':')[1])))

    # Calculate next occurrences for each event time
    next_occurrences = []
    for et in event_times:
        if et < now_user:
            next_occurrences.append(et + timedelta(days=1))
        else:
            next_occurrences.append(et)
    
    # Sort by next occurrence
    sorted_indices = sorted(range(len(next_occurrences)), key=lambda i: next_occurrences[i])
    sorted_event_times = [event_times[i] for i in sorted_indices]
    next_event = next_occurrences[sorted_indices[0]]
    
    # Format the next event time for display
    next_event_formatted = format_time(next_event, fmt)
    
    # Calculate time until next event
    diff = next_event - now_user
    hrs, mins = divmod(diff.seconds // 60, 60)
    
    # Create event description
    description = {
        'Grandma': "🕯 Grandma offers wax at Hidden Forest every 2 hours",
        'Turtle': "🐢 Dark Turtle appears at Sanctuary Islands every 2 hours",
        'Geyser': "🌋 Geyser erupts at Sanctuary Islands every 2 hours"
    }[event_name]
    
    text = (
        f"{description}\n\n"
        f"⏰ Next Event: {next_event_formatted}\n"
        f"⏳ Time Remaining: {hrs}h {mins}m\n\n"
        "Choose a time to set a reminder:"
    )

    # Send buttons for event times sorted by next occurrence
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    
    # Highlight next event with a special emoji
    next_event_time_str = format_time(sorted_event_times[0], fmt)
    markup.row(f"⏩ {next_event_time_str} (Next)")
    
    # Add other times in pairs
    for i in range(1, len(sorted_event_times), 2):
        row = []
        time_str = format_time(sorted_event_times[i], fmt)
        row.append(time_str)
        
        if i+1 < len(sorted_event_times):
            time_str2 = format_time(sorted_event_times[i+1], fmt)
            row.append(time_str2)
        
        markup.row(*row)
    
    markup.row(WAX_EVENTS_BUTTON)
    
    bot.send_message(message.chat.id, text, reply_markup=markup)
    bot.register_next_step_handler(message, ask_reminder_frequency, event_name)

def ask_reminder_frequency(message: telebot.types.Message, event_type: str):
    """Asks the user for reminder frequency (one-time or daily)."""
    update_last_interaction(message.from_user.id)
    if message.text.strip() == WAX_EVENTS_BUTTON:
        send_wax_menu(message.chat.id)
        return
        
    try:
        selected_time = message.text.replace("⏩", "").replace("(Next)", "").strip()
        
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.row(ONE_TIME_REMINDER_BUTTON)
        markup.row(DAILY_REMINDER_BUTTON)
        markup.row(WAX_EVENTS_BUTTON)
        
        bot.send_message(
            message.chat.id,
            f"⏰ You selected: {selected_time}\n\n"
            "Choose reminder frequency:",
            reply_markup=markup
        )
        bot.register_next_step_handler(message, ask_reminder_minutes, event_type, selected_time)
    except Exception as e:
        logger.error(f"Error in frequency selection: {str(e)}")
        bot.send_message(message.chat.id, "⚠️ Invalid selection. Please try again.")
        send_wax_menu(message.chat.id)

def ask_reminder_minutes(message: telebot.types.Message, event_type: str, selected_time: str):
    """Asks the user how many minutes before the event to remind them."""
    update_last_interaction(message.from_user.id)
    if message.text.strip() == WAX_EVENTS_BUTTON:
        send_wax_menu(message.chat.id)
        return
        
    try:
        is_daily = False
        if message.text == ONE_TIME_REMINDER_BUTTON:
            is_daily = False
        elif message.text == DAILY_REMINDER_BUTTON:
            is_daily = True
        else:
            bot.send_message(message.chat.id, "Please select a valid option")
            return
            
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.row('5', '10', '15')
        markup.row('20', '30', '45')
        markup.row('60', WAX_EVENTS_BUTTON)
        
        bot.send_message(
            message.chat.id, 
            f"⏰ Event: {event_type}\n"
            f"🕑 Time: {selected_time}\n"
            f"🔄 Frequency: {'Daily' if is_daily else 'One-time'}\n\n"
            "How many minutes before should I remind you?\n"
            "Choose an option or type a number (1-60):",
            reply_markup=markup
        )
        bot.register_next_step_handler(message, save_reminder, event_type, selected_time, is_daily)
    except Exception as e:
        logger.error(f"Error in minutes selection: {str(e)}")
        bot.send_message(message.chat.id, "⚠️ Failed to set reminder. Please try again.")
        send_wax_menu(message.chat.id)

def save_reminder(message: telebot.types.Message, event_type: str, selected_time: str, is_daily: bool):
    """Saves the reminder to the database and schedules it."""
    update_last_interaction(message.from_user.id)
    if message.text.strip() == WAX_EVENTS_BUTTON:
        send_wax_menu(message.chat.id)
        return

    try:
        input_text = message.text.strip()
        match = re.search(r'\d+', input_text)
        if not match:
            raise ValueError("No numbers found in input")

        mins = int(match.group())
        if mins < 1 or mins > 60:
            raise ValueError("Minutes must be between 1-60")

        user = get_user(message.from_user.id)
        if not user:
            bot.send_message(message.chat.id, "Please set your timezone first with /start")
            return

        tz, fmt = user
        user_tz = pytz.timezone(tz)
        now = datetime.now(user_tz)

        # Clean time string from button text (remove emojis, parentheses, etc.)
        clean_time = selected_time.strip()
        clean_time = re.sub(r'[^\d:apmAPM\s]', '', clean_time)
        clean_time = re.sub(r'\s+', '', clean_time)

        # Parse time based on user's format (Improved logic)
        try:
            if fmt == '12hr':
                time_obj = datetime.strptime(clean_time, '%I:%M%p')
            else: # '24hr'
                time_obj = datetime.strptime(clean_time, '%H:%M')
        except ValueError:
            # Fallback for cases like '10:00' given to a 12hr format user
            # or if AM/PM is missing from 12hr string for any reason
            try:
                time_obj = datetime.strptime(clean_time, '%H:%M')
            except ValueError:
                raise ValueError(f"Couldn't parse time: {clean_time}. Ensure correct format (HH:MM or HH:MM AM/PM).")


        # Create datetime in user's timezone
        event_time_user = now.replace(
            hour=time_obj.hour,
            minute=time_obj.minute,
            second=0,
            microsecond=0
        )

        if event_time_user < now:
            event_time_user += timedelta(days=1)

        event_time_utc = event_time_user.astimezone(pytz.utc)
        trigger_time = event_time_utc - timedelta(minutes=mins)

        logger.info(f"[DEBUG] Trying to insert reminder: "
                    f"user_id={message.from_user.id}, "
                    f"event_type={event_type}, "
                    f"event_time_utc={event_time_utc}, "
                    f"trigger_time={trigger_time}, "
                    f"notify_before={mins}, "
                    f"is_daily={is_daily}")

        with get_db() as conn:
            with conn.cursor() as cur:
                chat_id = message.chat.id

                cur.execute("""
                INSERT INTO reminders (
                    user_id, chat_id, event_type, event_time_utc, trigger_time,
                    notify_before, is_daily, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                ECOMING id
                """, (
                    message.from_user.id, chat_id, event_type, event_time_utc,
                    trigger_time, mins, is_daily
                    ))

                reminder_id = cur.fetchone()[0]
                conn.commit()

        schedule_reminder(message.from_user.id, reminder_id, event_type,
                          event_time_utc, mins, is_daily)

        frequency = "daily" if is_daily else "one time"
        emoji = "🔄" if is_daily else "⏰"

        bot.send_message(
            message.chat.id,
            f"✅ Reminder set!\n\n"
            f"⏰ Event: {event_type}\n"
            f"🕑 Time: {selected_time}\n"
            f"⏱ Remind: {mins} minutes before\n"
            f"{emoji} Frequency: {frequency}"
        )
        send_main_menu(message.chat.id, message.from_user.id)

    except ValueError as ve:
        logger.warning(f"User input error: {str(ve)}")
        bot.send_message(
            message.chat.id,
            f"❌ Invalid input: {str(ve)}. Please choose minutes from buttons or type 1-60."
        )
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.row('5', '10', '15')
        markup.row('20', '30', '45')
        markup.row('60', WAX_EVENTS_BUTTON)
        bot.send_message(
            message.chat.id,
            "Please choose how many minutes before the event to remind you:",
            reply_markup=markup
        )
        bot.register_next_step_handler(message, save_reminder, event_type, selected_time, is_daily)

    except Exception as e:
        logger.error("Reminder save failed", exc_info=True)
        bot.send_message(
            message.chat.id,
            "⚠️ Failed to set reminder. Please try again later."
        )
        send_main_menu(message.chat.id, message.from_user.id)


# ==================== REMINDER SCHEDULING =====================
def schedule_reminder(user_id: int, reminder_id: int, event_type: str, event_time_utc: datetime, notify_before: int, is_daily: bool):
    """Schedules a reminder using APScheduler."""
    try:
        notify_time = event_time_utc - timedelta(minutes=notify_before)
        current_time = datetime.now(pytz.utc)
        
        if notify_time < current_time:
            if is_daily:
                # Adjust notify_time and event_time_utc to the next day
                notify_time += timedelta(days=1)
                event_time_utc += timedelta(days=1)
                
                # Update database with new event_time_utc for daily reminders
                with get_db() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            UPDATE reminders 
                            SET event_time_utc = %s 
                            WHERE id = %s
                        """, (event_time_utc, reminder_id))
                        conn.commit()
            else:
                logger.warning(f"Reminder {reminder_id} is in the past, skipping")
                return
        
        scheduler.add_job(
            send_reminder_notification,
            'date',
            run_date=notify_time,
            args=[user_id, reminder_id, event_type, event_time_utc, notify_before, is_daily],
            id=f'rem_{reminder_id}'
        )
        
        logger.info(f"Scheduled reminder: ID={reminder_id}, RunAt={notify_time}, "
                    f"EventTime={event_time_utc}, NotifyBefore={notify_before} mins")
        
    except Exception as e:
        logger.error(f"Error scheduling reminder {reminder_id}: {str(e)}")

def send_reminder_notification(user_id: int, reminder_id: int, event_type: str, event_time_utc: datetime, notify_before: int, is_daily: bool):
    """Sends a reminder notification to the user."""
    try:
        user_info = get_user(user_id)
        if not user_info:
            logger.warning(f"User {user_id} not found for reminder {reminder_id}")
            return
            
        tz, fmt = user_info
        user_tz = pytz.timezone(tz)
        
        event_time_user = event_time_utc.astimezone(user_tz)
        event_time_str = format_time(event_time_user, fmt)
        
        message_text = (
            f"⏰ Reminder: {event_type} is starting in {notify_before} minutes!\n"
            f"🕑 Event Time: {event_time_str}"
        )
        
        bot.send_message(user_id, message_text)
        logger.info(f"Sent reminder for {event_type} to user {user_id}")
        
        if is_daily:
            new_event_time = event_time_utc + timedelta(days=1)
            schedule_reminder(user_id, reminder_id, event_type, 
                             new_event_time, notify_before, True)
            
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE reminders 
                        SET event_time_utc = %s 
                        WHERE id = %s
                    """, (new_event_time, reminder_id))
                    conn.commit()
                    
    except Exception as e:
        logger.error(f"Error sending reminder {reminder_id}: {str(e)}")
        try:
            if ADMIN_USER_ID:
                bot.send_message(ADMIN_USER_ID, f"⚠️ Reminder failed: {reminder_id}\nError: {str(e)}")
        except Exception:
            pass # Fail silently if admin notification fails too

# ======================= ADMIN PANEL ===========================
@bot.message_handler(func=lambda msg: msg.text == ADMIN_PANEL_BUTTON and is_admin(msg.from_user.id))
def handle_admin_panel(message: telebot.types.Message):
    """Handles access to the admin panel."""
    update_last_interaction(message.from_user.id)
    send_admin_menu(message.chat.id)

@bot.message_handler(func=lambda msg: msg.text == USER_STATS_BUTTON and is_admin(msg.from_user.id))
def user_stats(message: telebot.types.Message):
    """Displays user statistics."""
    try:
        update_last_interaction(message.from_user.id)
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM users")
                total_users = cur.fetchone()[0]
                
                cur.execute("""
                    SELECT COUNT(*) 
                    FROM users 
                    WHERE last_interaction > NOW() - INTERVAL '7 days'
                """)
                active_users = cur.fetchone()[0]
                
                cur.execute("SELECT COUNT(DISTINCT user_id) FROM reminders")
                users_with_reminders = cur.fetchone()[0]
    
        text = (
            f"👤 Total Users: {total_users}\n"
            f"🚀 Active Users (7 days): {active_users}\n"
            f"⏰ Users with Reminders: {users_with_reminders}"
        )
        bot.send_message(message.chat.id, text)
    except Exception as e:
        logger.error(f"Error in user_stats: {str(e)}")
        error_msg = f"❌ Error generating stats: {str(e)}"
        if "column \"last_interaction\" does not exist" in str(e):
            error_msg += "\n\n⚠️ Database needs migration! Please restart the bot."
        bot.send_message(message.chat.id, error_msg)

# ===================== ADMIN TS EDITOR FLOW (Database Version) =====================
def process_ts_name(message: telebot.types.Message, ts_info: dict):
    """Processes the Traveling Spirit name."""
    ts_info['name'] = message.text.strip()
    msg = bot.send_message(message.chat.id, f"Name set. Now, send the dates:")
    bot.register_next_step_handler(msg, process_ts_dates, ts_info)

def process_ts_dates(message: telebot.types.Message, ts_info: dict):
    """Processes the Traveling Spirit dates."""
    ts_info['dates'] = message.text.strip()
    msg = bot.send_message(message.chat.id, f"Dates set. Now, please send the main photo for the spirit:")
    bot.register_next_step_handler(msg, process_ts_main_image, ts_info)

def process_ts_main_image(message: telebot.types.Message, ts_info: dict):
    """Processes the main Traveling Spirit image."""
    if message.photo:
        ts_info['image_file_id'] = message.photo[-1].file_id
        msg = bot.send_message(message.chat.id, f"Main photo received.\n\nNow, send the item list (each item on a new line):")
        bot.register_next_step_handler(msg, process_ts_items_list, ts_info)
    else:
        msg = bot.send_message(message.chat.id, "That's not a photo. Please send an image.")
        bot.register_next_step_handler(msg, process_ts_main_image, ts_info)

def process_ts_items_list(message: telebot.types.Message, ts_info: dict):
    """Processes the Traveling Spirit item list."""
    ts_info['items'] = message.text.strip()
    msg = bot.send_message(message.chat.id, "Item list set.\n\nNext, please send the item tree picture:")
    bot.register_next_step_handler(msg, process_ts_tree_image, ts_info)

def process_ts_tree_image(message: telebot.types.Message, ts_info: dict):
    """Processes the Traveling Spirit item tree image."""
    if message.photo:
        ts_info['tree_image_file_id'] = message.photo[-1].file_id
        msg = bot.send_message(message.chat.id, "Item tree picture received.\n\nFinally, what caption should go under the item tree picture?")
        bot.register_next_step_handler(msg, process_ts_tree_caption, ts_info)
    else:
        msg = bot.send_message(message.chat.id, "That's not a photo. Please send an image.")
        bot.register_next_step_handler(msg, process_ts_tree_image, ts_info)

def process_ts_tree_caption(message: telebot.types.Message, ts_info: dict):
    """Processes the Traveling Spirit item tree caption and saves all info."""
    ts_info['tree_caption'] = message.text.strip()
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                # Updated column names here as well
                cur.execute("""
                    UPDATE traveling_spirit 
                    SET is_active = TRUE, name = %s, dates = %s, image_file_id = %s, items = %s, 
                        item_tree_image_file_id = %s, item_tree_caption = %s, last_updated = NOW()
                    WHERE id = %s
                """, (ts_info['name'], ts_info['dates'], ts_info['image_file_id'], ts_info['items'], 
                      ts_info['tree_image_file_id'], ts_info['tree_caption'], TRAVELING_SPIRIT_DB_ID))
                conn.commit()
        bot.send_message(message.chat.id, "✅ **Success!** All Traveling Spirit information has been updated.")
    except Exception as e:
        logger.error(f"Failed to save TS info to DB: {e}")
        bot.send_message(message.chat.id, "⚠️ **Database Error!**")
    send_admin_menu(message.chat.id)

def process_ts_status(message: telebot.types.Message):
    """Processes the initial Traveling Spirit status selection."""
    if message.text == ADMIN_PANEL_BACK_BUTTON:
        return send_admin_menu(message.chat.id)
    if message.text == TS_ACTIVE_BUTTON:
        ts_info = {}
        msg = bot.send_message(message.chat.id, "Please send the spirit's name:", reply_markup=telebot.types.ReplyKeyboardRemove())
        bot.register_next_step_handler(msg, process_ts_name, ts_info)
    elif message.text == TS_INACTIVE_BUTTON:
        try:
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute("UPDATE traveling_spirit SET is_active = FALSE, last_updated = NOW() WHERE id = %s", (TRAVELING_SPIRIT_DB_ID,))
                    conn.commit()
            bot.send_message(message.chat.id, "✅ Traveling Spirit status set to INACTIVE.")
        except Exception as e:
            logger.error(f"Failed to set TS inactive: {e}")
        send_admin_menu(message.chat.id)
    else:
        bot.send_message(message.chat.id, "Invalid option.")
        handle_ts_edit_start(message)

@bot.message_handler(func=lambda msg: msg.text == EDIT_TS_BUTTON and is_admin(msg.from_user.id))
def handle_ts_edit_start(message: telebot.types.Message):
    """Starts the Traveling Spirit editing flow for admins."""
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(TS_ACTIVE_BUTTON, TS_INACTIVE_BUTTON)
    markup.row(ADMIN_PANEL_BACK_BUTTON)
    bot.send_message(message.chat.id, "Set the Traveling Spirit's status:", reply_markup=markup)
    bot.register_next_step_handler(message, process_ts_status)
    # Removed redundant database save logic here as it's handled in process_ts_tree_caption

# --- ADMIN SHARD EDITING FLOW (NEW) ---

# Global dictionary to hold shard edit sessions for each admin user
# IMPORTANT: This is in-memory and will reset if the bot restarts.
# For production, consider using a database to store in-progress edit states.
user_shard_edit_sessions = {}

@bot.message_handler(func=lambda msg: msg.text == EDIT_SHARDS_BUTTON and is_admin(msg.from_user.id))
def handle_edit_shards_start(message: telebot.types.Message):
    """Starts the process of editing shard data for a specific date."""
    update_last_interaction(message.from_user.id)
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(ADMIN_PANEL_BACK_BUTTON)
    msg = bot.send_message(message.chat.id, "Enter the date for shard data (YYYY-MM-DD), or /cancel to abort:", reply_markup=markup)
    bot.register_next_step_handler(msg, get_shard_date_to_edit_specific)

def get_shard_date_to_edit_specific(message: telebot.types.Message):
    """Parses shard date for specific editing and initiates the edit menu."""
    if message.text.lower() == '/cancel':
        send_admin_menu(message.chat.id)
        return

    try:
        shard_date_str = message.text.strip()
        shard_date = datetime.strptime(shard_date_str, "%Y-%m-%d").date()
        
        existing_data = get_shard_data_for_single_calendar_date(shard_date) # USE THE SINGLE DATE FETCH
        
        # Initialize the session data for this admin user
        user_shard_edit_sessions[message.from_user.id] = {
            "date": shard_date,
            "data": existing_data if existing_data else {
                "Date": shard_date.strftime("%Y-%m-%d"), # Ensure date is explicitly in data
                "Shard Color": None, "Realm": None, "Location": None,
                "Reward": None, "Memory": None,
                "First Shard (MT)": None, "Second Shard (MT)": None, "Last Shard (MT)": None,
                "Eruption Status": None
            }
        }
        
        # Send a NEW message from the bot for the editing menu
        initial_message_text = f"Loading shard data for {shard_date_str}..." # Or similar
        sent_message = bot.send_message(message.chat.id, initial_message_text)
        
        # Now pass the ID of the message *sent by the bot* for subsequent edits
        send_shard_edit_menu(message.chat.id, message.from_user.id, sent_message.message_id)

    except ValueError:
        msg = bot.send_message(message.chat.id, "❌ Invalid date format. Please use `YYYY-MM-DD`. Try again:")
        bot.register_next_step_handler(msg, get_shard_date_to_edit_specific)
    except Exception as e:
        logger.error(f"Error getting shard date for specific edit: {e}", exc_info=True)
        bot.send_message(message.chat.id, "⚠️ An unexpected error occurred. Try again.")
        send_admin_menu(message.chat.id)

def send_shard_edit_menu(chat_id: int, user_id: int, message_id_to_edit: int | None = None):
    """Displays the current shard data being edited and provides editing options."""
    session = user_shard_edit_sessions.get(user_id)
    if not session:
        bot.send_message(chat_id, "❌ No active shard editing session found. Please start again.")
        send_admin_menu(chat_id)
        return

    shard_date = session["date"]
    current_shard_data = session["data"]

    message_text = f"📝 **Editing Shard Data for {shard_date.strftime('%Y-%m-%d (%A)')}:**\n\n"
    # Display current values (excluding 'Date' as it's in the header)
    for key, value in current_shard_data.items():
        if key == "Date": continue
        message_text += f"**{key.replace('(MT)', '').strip()}:** {value if value is not None else 'N/A'}\n"
    
    markup = telebot.types.InlineKeyboardMarkup(row_width=2)
    
    # Buttons for each editable field
    markup.add(
        telebot.types.InlineKeyboardButton("Edit Shard Color", callback_data=f"edit_shard_field_Shard Color"),
        telebot.types.InlineKeyboardButton("Edit Realm", callback_data=f"edit_shard_field_Realm"),
        telebot.types.InlineKeyboardButton("Edit Location", callback_data=f"edit_shard_field_Location"),
        telebot.types.InlineKeyboardButton("Edit Reward", callback_data=f"edit_shard_field_Reward"),
        telebot.types.InlineKeyboardButton("Edit Memory", callback_data=f"edit_shard_field_Memory"),
        telebot.types.InlineKeyboardButton("Edit First Shard (MT)", callback_data=f"edit_shard_field_First Shard (MT)"),
        telebot.types.InlineKeyboardButton("Edit Second Shard (MT)", callback_data=f"edit_shard_field_Second Shard (MT)"),
        telebot.types.InlineKeyboardButton("Edit Last Shard (MT)", callback_data=f"edit_shard_field_Last Shard (MT)"),
        telebot.types.InlineKeyboardButton("Edit Eruption Status", callback_data=f"edit_shard_field_Eruption Status")
    )
    
    markup.row(
        telebot.types.InlineKeyboardButton(SAVE_SHARD_CHANGES_BUTTON, callback_data="save_shard_changes"),
        telebot.types.InlineKeyboardButton(CANCEL_SHARD_EDIT_BUTTON, callback_data="cancel_shard_edit")
    )

    if message_id_to_edit:
        try:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id_to_edit,
                text=message_text,
                reply_markup=markup,
                parse_mode='Markdown'
            )
        except telebot.apihelper.ApiTelegramException as e:
            if "message is not modified" in str(e).lower():
                logger.info("Shard edit menu message not modified, skipping edit.")
            else:
                logger.error(f"Error editing shard edit menu: {e}", exc_info=True)
                bot.send_message(chat_id, "⚠️ Error updating shard edit menu. Please try again.")
    else:
        bot.send_message(chat_id, message_text, reply_markup=markup, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data.startswith("edit_shard_field_"))
def handle_edit_shard_field_callback(call: telebot.types.CallbackQuery):
    """Handles callback when an admin selects a specific field to edit."""
    update_last_interaction(call.from_user.id)
    user_id = call.from_user.id
    field_name = call.data.split("edit_shard_field_")[1] # Extract field name
    
    session = user_shard_edit_sessions.get(user_id)
    if not session:
        bot.send_message(call.message.chat.id, "❌ No active editing session. Please start again.")
        send_admin_menu(call.message.chat.id)
        bot.answer_callback_query(call.id)
        return

    # Prompt for the new value for the selected field
    msg = bot.send_message(call.message.chat.id, f"Enter new value for **{field_name}** (Type 'N/A' or '-' to clear, /cancel to abort edit):", parse_mode='Markdown')
    
    # Register the next step to process this specific field's input
    bot.register_next_step_handler(msg, process_shard_field_update_input, user_id, field_name, call.message.message_id)
    
    bot.answer_callback_query(call.id) # Acknowledge the callback

def process_shard_field_update_input(message: telebot.types.Message, user_id: int, field_name: str, original_message_id: int):
    """Processes the text input for a specific shard field."""
    update_last_interaction(user_id)
    
    if message.text.lower() == '/cancel':
        bot.send_message(message.chat.id, "Edit cancelled for this field. Returning to menu.")
        send_shard_edit_menu(message.chat.id, user_id, original_message_id) # Return to edit menu
        return

    session = user_shard_edit_sessions.get(user_id)
    if not session:
        bot.send_message(message.chat.id, "❌ No active editing session. Please start again.")
        send_admin_menu(message.chat.id)
        return

    new_value = message.text.strip()
    # Interpret 'N/A' or '-' as None (NULL in DB)
    session["data"][field_name] = None if new_value.lower() in ('n/a', '-') else new_value
    
    bot.send_message(message.chat.id, f"✅ **{field_name}** updated temporarily. Review changes below.", parse_mode='Markdown')
    send_shard_edit_menu(message.chat.id, user_id, original_message_id) # Re-display menu with updated data

@bot.callback_query_handler(func=lambda call: call.data == "save_shard_changes")
def handle_save_shard_changes_callback(call: telebot.types.CallbackQuery):
    """Saves all modified shard data to the database."""
    update_last_interaction(call.from_user.id)
    user_id = call.from_user.id
    session = user_shard_edit_sessions.pop(user_id, None) # Remove session after attempting to save
    
    if not session:
        bot.send_message(call.message.chat.id, "❌ No active editing session to save.")
        send_admin_menu(call.message.chat.id)
        bot.answer_callback_query(call.id)
        return

    shard_date = session["date"]
    data_to_save = session["data"]

    try:
        # Prepare data for insertion/update (order must match SQL query)
        params = (
            shard_date, # Date comes first for the VALUES part
            data_to_save.get("Shard Color"),
            data_to_save.get("Realm"),
            data_to_save.get("Location"),
            data_to_save.get("Reward"),
            data_to_save.get("Memory"),
            data_to_save.get("First Shard (MT)"), # Use new key
            data_to_save.get("Second Shard (MT)"), # Use new key
            data_to_save.get("Last Shard (MT)"), # Use new key
            data_to_save.get("Eruption Status")
        )
        
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO shard_events (
                        date, shard_color, realm, location, reward, memory,
                        first_shard_mt, second_shard_mt, last_shard_mt, eruption_status
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (date) DO UPDATE SET
                        shard_color = EXCLUDED.shard_color,
                        realm = EXCLUDED.realm,
                        location = EXCLUDED.location,
                        reward = EXCLUDED.reward,
                        memory = EXCLUDED.memory,
                        first_shard_mt = EXCLUDED.first_shard_mt,
                        second_shard_mt = EXCLUDED.second_shard_mt,
                        last_shard_mt = EXCLUDED.last_shard_mt,
                        eruption_status = EXCLUDED.eruption_status
                """, params) # params directly matches the (date, + other fields)
                conn.commit()

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"✅ Shard data for {shard_date.strftime('%Y-%m-%d')} successfully saved/updated!",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error saving shard data: {e}", exc_info=True)
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="⚠️ Failed to save shard data. Please check logs.",
            parse_mode='Markdown'
        )
    finally:
        send_admin_menu(call.message.chat.id)
        bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "cancel_shard_edit")
def handle_cancel_shard_edit_callback(call: telebot.types.CallbackQuery):
    """Cancels the shard editing session."""
    update_last_interaction(call.from_user.id)
    user_id = call.from_user.id
    if user_id in user_shard_edit_sessions:
        del user_shard_edit_sessions[user_id] # Remove session
    
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="❌ Shard data editing cancelled. No changes saved."
    )
    send_admin_menu(call.message.chat.id)
    bot.answer_callback_query(call.id)

# Broadcast Messaging
@bot.message_handler(func=lambda msg: msg.text == BROADCAST_BUTTON and is_admin(msg.from_user.id))
def start_broadcast(message: telebot.types.Message):
    """Starts the broadcast message flow."""
    update_last_interaction(message.from_user.id)
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('🔊 Broadcast to All')
    markup.row('👤 Send to Specific User')
    markup.row(ADMIN_PANEL_BACK_BUTTON)
    bot.send_message(message.chat.id, "Choose broadcast type:", reply_markup=markup)

@bot.message_handler(func=lambda msg: msg.text == '🔊 Broadcast to All' and is_admin(msg.from_user.id))
def broadcast_to_all(message: telebot.types.Message):
    """Prompts for message to broadcast to all users."""
    update_last_interaction(message.from_user.id)
    msg = bot.send_message(message.chat.id, "Enter message to broadcast to ALL users (type /cancel to abort):")
    bot.register_next_step_handler(msg, process_broadcast_all)

@bot.message_handler(func=lambda msg: msg.text == '👤 Send to Specific User' and is_admin(msg.from_user.id))
def send_to_user(message: telebot.types.Message):
    """Prompts for user ID to send a specific message."""
    update_last_interaction(message.from_user.id)
    msg = bot.send_message(message.chat.id, "Enter target USER ID (type /cancel to abort):")
    bot.register_next_step_handler(msg, get_target_user)

def get_target_user(message: telebot.types.Message):
    """Gets the target user ID for a specific message."""
    update_last_interaction(message.from_user.id)
    if message.text.strip().lower() == '/cancel':
        send_admin_menu(message.chat.id)
        return
        
    try:
        user_id = int(message.text.strip())
        message.target_user_id = user_id # Store user ID in message object for next step
        msg = bot.send_message(message.chat.id, f"Enter message for user {user_id}:")
        bot.register_next_step_handler(msg, process_user_message)
    except ValueError:
        bot.send_message(message.chat.id, "❌ Invalid user ID. Must be a number. Try again:")
        bot.register_next_step_handler(msg, get_target_user)

def process_user_message(message: telebot.types.Message):
    """Sends a message to a specific user."""
    update_last_interaction(message.from_user.id)
    if message.text.strip().lower() == '/cancel':
        send_admin_menu(message.chat.id)
        return
        
    target_user_id = getattr(message, 'target_user_id', None)
    if not target_user_id:
        bot.send_message(message.chat.id, "❌ Error: User ID not found. Please start over.")
        return send_admin_menu(message.chat.id)
        
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT chat_id FROM users WHERE user_id = %s", (target_user_id,))
                result = cur.fetchone()
                
                if result:
                    chat_id = result[0]
                    try:
                        bot.send_message(chat_id, f"📢 Admin Message:\n\n{message.text}")
                        bot.send_message(message.chat.id, f"✅ Message sent to user {target_user_id}")
                    except Exception as e:
                        logger.error(f"Failed to send to user {target_user_id}: {str(e)}")
                        bot.send_message(message.chat.id, f"❌ Failed to send to user {target_user_id}. They may have blocked the bot.")
                else:
                    bot.send_message(message.chat.id, f"❌ User {target_user_id} not found in database")
    except Exception as e:
        logger.error(f"Error sending to specific user: {str(e)}")
        bot.send_message(message.chat.id, "❌ Error sending message. Please try again.")
    
    send_admin_menu(message.chat.id)

def process_broadcast_all(message: telebot.types.Message):
    """Sends a broadcast message to all users."""
    update_last_interaction(message.from_user.id)
    if message.text.strip().lower() == '/cancel':
        send_admin_menu(message.chat.id)
        return
        
    broadcast_text = message.text
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT chat_id FROM users")
            chat_ids = [row[0] for row in cur.fetchall()]
    
    success = 0
    failed = 0
    total = len(chat_ids)
    
    progress_msg = bot.send_message(message.chat.id, f"📤 Sending broadcast... 0/{total}")
    
    for i in range(total):
        chat_id = chat_ids[i]
        try:
            bot.send_message(chat_id, f"📢 Admin Broadcast:\n\n{broadcast_text}")
            success += 1
        except Exception as e:
            logger.error(f"Broadcast failed for {chat_id}: {str(e)}")
            failed += 1
            
        if (i + 1) % 10 == 0 or (i + 1) == total:
            try:
                bot.edit_message_text(
                    f"📤 Sending broadcast... {i+1}/{total}",
                    message.chat.id,
                    progress_msg.message_id
                )
            except Exception:
                pass  # Fail silently on edit errors
    
    bot.send_message(
        message.chat.id,
        f"📊 Broadcast complete!\n"
        f"✅ Success: {success}\n"
        f"❌ Failed: {failed}\n"
        f"📩 Total: {total}"
    )
    send_admin_menu(message.chat.id)

# Reminder Management
@bot.message_handler(func=lambda msg: msg.text == MANAGE_REMINDERS_BUTTON and is_admin(msg.from_user.id))
def manage_reminders(message: telebot.types.Message):
    """Displays active reminders and allows deletion."""
    update_last_interaction(message.from_user.id)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, user_id, event_type, event_time_utc, notify_before
                FROM reminders r
                JOIN users u ON r.user_id = u.user_id
                WHERE r.event_time_utc > NOW()
                ORDER BY r.event_time_utc
                LIMIT 50
            """)
            reminders = cur.fetchall()
    
    if not reminders:
        bot.send_message(message.chat.id, "No active reminders found")
        return
    
    text = "⏰ Active Reminders:\n\n"
    for i, rem in enumerate(reminders, 1):
        text += f"{i}. {rem[2]} @ {rem[3].strftime('%Y-%m-%d %H:%M')} UTC (User: {rem[1]})\n"
    
    text += "\nReply with reminder number to delete or /cancel"
    msg = bot.send_message(message.chat.id, text)
    bot.register_next_step_handler(msg, handle_reminder_action, reminders)

def handle_reminder_action(message: telebot.types.Message, reminders: list):
    """Handles deletion of a selected reminder."""
    update_last_interaction(message.from_user.id)
    if message.text.strip().lower() == '/cancel':
        send_admin_menu(message.chat.id)
        return
    
    try:
        index = int(message.text) - 1
        if 0 <= index < len(reminders):
            rem_id = reminders[index][0]
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM reminders WHERE id = %s", (rem_id,))
                    conn.commit()
                    
            try:
                scheduler.remove_job(f'rem_{rem_id}')
                logger.info(f"Removed job for reminder {rem_id}")
            except Exception:
                pass # Fail silently if job not found in scheduler
                
            bot.send_message(message.chat.id, "✅ Reminder deleted")
        else:
            bot.send_message(message.chat.id, "Invalid selection")
    except ValueError:
        bot.send_message(message.chat.id, "Please enter a valid number")
    
    send_admin_menu(message.chat.id)

# System Status
@bot.message_handler(func=lambda msg: msg.text == SYSTEM_STATUS_BUTTON and is_admin(msg.from_user.id))
def system_status(message: telebot.types.Message):
    """Displays system status information."""
    update_last_interaction(message.from_user.id)
    uptime = datetime.now() - start_time
    
    db_status = "✅ Connected"
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
    except Exception as e:
        db_status = f"❌ Error: {str(e)}"
    
    error_count = 0
    try:
        with open('bot.log', 'r') as f:
            for line in f:
                if 'ERROR' in line:
                    error_count += 1
    except Exception as e:
        error_count = f"Error reading log: {str(e)}"
    
    memory = psutil.virtual_memory()
    memory_usage = f"{memory.used / (1024**3):.1f}GB / {memory.total / (1024**3):.1f}GB ({memory.percent}%)"
    
    try:
        job_count = len(scheduler.get_jobs())
    except Exception:
        job_count = "N/A"
    
    text = (
        f"⏱ Uptime: {str(uptime).split('.')[0]}\n"
        f"🗄 Database: {db_status}\n"
        f"💾 Memory: {memory_usage}\n"
        f"❗️ Recent Errors: {error_count}\n"
        f"🤖 Active Jobs: {job_count}"
    )
    bot.send_message(message.chat.id, text)

# User Search
@bot.message_handler(func=lambda msg: msg.text == FIND_USER_BUTTON and is_admin(msg.from_user.id))
def find_user(message: telebot.types.Message):
    """Initiates user search by ID or timezone."""
    update_last_interaction(message.from_user.id)
    msg = bot.send_message(message.chat.id, "Enter username or user ID to search (type /cancel to abort):")
    bot.register_next_step_handler(msg, process_user_search)

def process_user_search(message: telebot.types.Message):
    """Processes the user search query."""
    update_last_interaction(message.from_user.id)
    if message.text.strip().lower() == '/cancel':
        send_admin_menu(message.chat.id)
        return
        
    search_term = message.text.strip()
    
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                if search_term.isdigit():
                    cur.execute(
                        "SELECT user_id, chat_id, timezone FROM users WHERE user_id = %s",
                        (int(search_term),)
                    )
                    results = cur.fetchall()
                else:
                    cur.execute(
                        "SELECT user_id, chat_id, timezone FROM users WHERE timezone ILIKE %s",
                        (f'%{search_term}%',)
                    )
                    results = cur.fetchall()
                
                if not results:
                    bot.send_message(message.chat.id, "❌ No users found")
                    return send_admin_menu(message.chat.id)
                    
                response = "🔍 Search Results:\n\n"
                for i, user in enumerate(results, 1):
                    user_id, chat_id, tz = user
                    response += f"{i}. User ID: {user_id}\nChat ID: {chat_id}\nTimezone: {tz}\n\n"
                
                bot.send_message(message.chat.id, response)
                
    except Exception as e:
        logger.error(f"User search error: {str(e)}")
        bot.send_message(message.chat.id, "❌ Error during search")
    
    send_admin_menu(message.chat.id)

# ========================== WEBHOOK ============================
@app.route('/webhook', methods=['POST'])
def webhook():
    """Receives and processes Telegram webhook updates."""
    try:
        if request.headers.get('content-type') == 'application/json':
            json_data = request.get_json()
            update = telebot.types.Update.de_json(json_data)
            bot.process_new_updates([update])
            return 'OK', 200
        else:
            logger.warning("Invalid content-type for webhook")
            return 'Invalid content-type', 400
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
        return 'Error processing webhook', 500

@app.route('/')
def index():
    """Simple health check endpoint."""
    return 'Sky Clock Bot is running.'


# ===================== BOT INITIALIZATION ======================
logger.info("Initializing database...")
init_db()
logger.info("Database initialized")

logger.info("Scheduling existing reminders...")
try:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, user_id, event_type, event_time_utc, notify_before, is_daily
                FROM reminders
            """)
            reminders = cur.fetchall()
            for rem in reminders:
                event_time_from_db = rem[3]
                if event_time_from_db.tzinfo is None:
                    aware_event_time_utc = pytz.utc.localize(event_time_from_db)
                else:
                    aware_event_time_utc = event_time_from_db
                
                schedule_reminder(rem[1], rem[0], rem[2], aware_event_time_utc, rem[4], rem[5])

            logger.info(f"Scheduled {len(reminders)} existing reminders")
except Exception as e:
    logger.error(f"Error scheduling existing reminders: {str(e)}")

logger.info("Setting up webhook...")
bot.remove_webhook()
bot.set_webhook(url=WEBHOOK_URL)
logger.info(f"BOT IS LIVE - Webhook set to: {WEBHOOK_URL}")