# bot.py - Implemented with Traveling Spirit Web Scraping Feature

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
from psycopg2 import errors as psycopg2_errors

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

# Environment variables
API_TOKEN = os.getenv("BOT_TOKEN") or "YOUR_BOT_TOKEN"
WEBHOOK_URL = os.getenv("WEBHOOK_URL") or "https://skyclock-bot.onrender.com/webhook"
DB_URL = os.getenv("DATABASE_URL") or "postgresql://user:pass@host:port/db"
ADMIN_USER_ID = os.getenv("ADMIN_USER_ID") or "YOUR_ADMIN_USER_ID"

bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)
scheduler = BackgroundScheduler()
scheduler.start()

# Track bot start time for uptime
start_time = datetime.now()

# Sky timezone
SKY_TZ = pytz.timezone('UTC')

# ========================== DATABASE ===========================
def get_db():
    try:
        conn = psycopg2.connect(DB_URL, sslmode='require')
        return conn
    except Exception as e:
        logger.error(f"Database connection failed: {str(e)}")
        raise

def init_db():
    with get_db() as conn:
        with conn.cursor() as cur:
            # Create users table if not exists
            cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                timezone TEXT NOT NULL,
                time_format TEXT DEFAULT '12hr',
                last_interaction TIMESTAMP DEFAULT NOW()
            );
            """)
            
            # Create reminders table if not exists with created_at column
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
            
            # Add any missing columns
            try:
                cur.execute("ALTER TABLE reminders ADD COLUMN IF NOT EXISTS chat_id BIGINT;")
                cur.execute("ALTER TABLE reminders ADD COLUMN IF NOT EXISTS trigger_time TIMESTAMP;")
            except Exception as e:
                logger.error(f"Error ensuring new columns exist: {str(e)}")

            conn.commit()

# ======================== WEB SCRAPING UTILITY ============================
def scrape_traveling_spirit():
    """
    Scrapes the Sky Fandom Wiki for the current Traveling Spirit.
    Returns a dictionary with the spirit's info, or a dictionary with an error.
    """
    URL = "https://sky-children-of-the-light.fandom.com/wiki/Traveling_Spirits"
    headers = {
        'User-Agent': 'SkyClockBot/1.0 (Python/Requests; Discord: your_username#1234)'
    }
    
    try:
        response = requests.get(URL, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')

        ts_table = soup.find('table', class_='article-table')
        if not ts_table or "Traveling Spirit" not in ts_table.caption.text:
            return {"is_active": False, "error": "Could not find the TS table."}

        data = {"is_active": True, "items": []}
        data['name'] = ts_table.caption.text.replace('Traveling Spirit', '').strip()

        rows = ts_table.find_all('tr')
        if len(rows) > 1:
            date_cells = rows[1].find_all('th')
            for cell in date_cells:
                if 'Arrives:' in cell.text:
                    data['arrives'] = cell.text.replace('Arrives:', '').strip()
                if 'Departs:' in cell.text:
                    data['departs'] = cell.text.replace('Departs:', '').strip()

        for row in rows[2:]:
            cells = row.find_all('td')
            if len(cells) >= 2:
                item_name = cells[0].text.strip()
                item_price = cells[1].text.strip().replace('\n', ' ')
                if item_name and "Total" not in item_name:
                    data["items"].append({"name": item_name, "price": item_price})

        return data

    except requests.exceptions.RequestException as e:
        logger.error(f"Web scraping network error: {e}")
        return {"is_active": False, "error": "Network error while fetching data."}
    except Exception as e:
        logger.error(f"Web scraping parsing error: {e}", exc_info=True)
        return {"is_active": False, "error": "Could not parse the website."}


# ======================== UTILITIES ============================
def format_time(dt, fmt):
    return dt.strftime('%I:%M %p') if fmt == '12hr' else dt.strftime('%H:%M')

def get_user(user_id):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT timezone, time_format FROM users WHERE user_id = %s", (user_id,))
            return cur.fetchone()

def set_timezone(user_id, chat_id, tz):
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

def set_time_format(user_id, fmt):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET time_format = %s, last_interaction = NOW() WHERE user_id = %s", (fmt, user_id))
            conn.commit()

def update_last_interaction(user_id):
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE users SET last_interaction = NOW() WHERE user_id = %s", (user_id,))
                conn.commit()
    except Exception as e:
        logger.error(f"Error updating last interaction for {user_id}: {str(e)}")

# ===================== ADMIN UTILITIES =========================
def is_admin(user_id):
    return str(user_id) == ADMIN_USER_ID

# ===================== NAVIGATION HELPERS ======================
def send_main_menu(chat_id, user_id=None):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('🕒 Sky Clock', '✨ Traveling Spirit')
    markup.row('🕯 Wax Events', '💎 Shards')
    markup.row('⚙️ Settings')
    if user_id and is_admin(user_id):
        markup.row('👤 Admin Panel')
    bot.send_message(chat_id, "Main Menu:", reply_markup=markup)

def send_wax_menu(chat_id):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('🧓 Grandma', '🐢 Turtle', '🌋 Geyser')
    markup.row('🔙 Main Menu')
    bot.send_message(chat_id, "Wax Events:", reply_markup=markup)

def send_settings_menu(chat_id, current_format):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(f'🕰 Change Time Format (Now: {current_format})')
    markup.row('🔙 Main Menu')
    bot.send_message(chat_id, "Settings:", reply_markup=markup)

def send_admin_menu(chat_id):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('👥 User Stats', '📢 Broadcast')
    markup.row('⏰ Manage Reminders', '📊 System Status')
    markup.row('🔍 Find User')
    markup.row('🔙 Main Menu')
    bot.send_message(chat_id, "Admin Panel:", reply_markup=markup)

# ======================= GLOBAL HANDLERS =======================
@bot.message_handler(func=lambda msg: msg.text == '🔙 Main Menu')
def handle_back_to_main(message):
    update_last_interaction(message.from_user.id)
    send_main_menu(message.chat.id, message.from_user.id)

# ======================= START FLOW ============================
@bot.message_handler(commands=['start'])
def start(message):
    update_last_interaction(message.from_user.id)
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.row('🇲🇲 Set to Myanmar Time')
    bot.send_message(
        message.chat.id,
        f"Hello {message.from_user.first_name}! 👋\nWelcome to Sky Clock Bot!\n\nPlease type your timezone (e.g. Asia/Yangon), or choose an option:",
        reply_markup=markup
    )
    bot.register_next_step_handler(message, save_timezone)

def save_timezone(message):
    user_id, chat_id = message.from_user.id, message.chat.id
    tz_text = 'Asia/Yangon' if message.text == '🇲🇲 Set to Myanmar Time' else message.text
    try:
        pytz.timezone(tz_text)
        if set_timezone(user_id, chat_id, tz_text):
            bot.send_message(chat_id, f"✅ Timezone set to: {tz_text}")
            send_main_menu(chat_id, user_id)
        else:
            bot.send_message(chat_id, "⚠️ Failed to save timezone. Please try /start again.")
    except pytz.UnknownTimeZoneError:
        bot.send_message(chat_id, "❌ Invalid timezone. Please try again:")
        bot.register_next_step_handler(message, save_timezone)
    except Exception as e:
        logger.error(f"Error saving timezone: {str(e)}")
        bot.send_message(chat_id, "⚠️ Unexpected error. Please try /start again.")

# ===================== MAIN MENU HANDLERS ======================
@bot.message_handler(func=lambda msg: msg.text == '🕒 Sky Clock')
def sky_clock(message):
    update_last_interaction(message.from_user.id)
    user = get_user(message.from_user.id)
    if not user: return bot.send_message(message.chat.id, "Please set your timezone with /start")
    
    tz, fmt = user
    user_tz = pytz.timezone(tz)
    now = datetime.now()
    local_time, sky_time = now.astimezone(user_tz), now.astimezone(SKY_TZ)
    time_diff = local_time - sky_time
    hours, rem = divmod(abs(time_diff.total_seconds()), 3600)
    minutes = rem // 60
    direction = "ahead of" if time_diff.total_seconds() > 0 else "behind"
    
    text = (f"🌥 Sky Time: {format_time(sky_time, fmt)}\n"
            f"🌍 Your Time: {format_time(local_time, fmt)}\n"
            f"⏱ You are {int(hours)}h {int(minutes)}m {direction} Sky Time")
    bot.send_message(message.chat.id, text)

@bot.message_handler(commands=['ts'])
@bot.message_handler(func=lambda msg: msg.text == '✨ Traveling Spirit')
def show_traveling_spirit(message):
    update_last_interaction(message.from_user.id)
    msg = bot.send_message(message.chat.id, "Searching for the Traveling Spirit... ✨")
    
    ts_data = scrape_traveling_spirit()
    
    if ts_data and ts_data.get("is_active"):
        response = f"**A Traveling Spirit is here!** ✨\n\n" \
                   f"The **{ts_data.get('name', 'Unknown Spirit')}** has arrived!\n\n"
        if ts_data.get('departs'):
             response += f"**Departure:** {ts_data.get('departs')}\n"
        response += "**Location:** You can find them in the Home space!\n\n**Items Available:**\n"
        if ts_data.get("items"):
            for item in ts_data['items']:
                response += f"- {item['name']}: {item['price']}\n"
        else:
            response += "_Could not parse item list._\n"
        response += f"\n_Data from the Sky Fandom Wiki._"
    else:
        response = "The Traveling Spirit has departed or has not been announced yet.\n\n" \
                   "They typically arrive every other Thursday. I'll keep an eye out for the next announcement!"
        if ts_data and ts_data.get("error"):
            logger.warning(f"TS Scraper Info: {ts_data.get('error')}")

    bot.edit_message_text(response, message.chat.id, msg.message_id, parse_mode='Markdown')

# ... The rest of your code (wax events, settings, admin panel, etc.) remains the same ...
# I have omitted it here for brevity, but you should keep it in your file.

# ======================== UTILITIES ============================
def format_time(dt, fmt):
    return dt.strftime('%I:%M %p') if fmt == '12hr' else dt.strftime('%H:%M')

def get_user(user_id):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT timezone, time_format FROM users WHERE user_id = %s", (user_id,))
            return cur.fetchone()

def set_timezone(user_id, chat_id, tz):
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

def set_time_format(user_id, fmt):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE users 
                SET time_format = %s, last_interaction = NOW() 
                WHERE user_id = %s
            """, (fmt, user_id))
            conn.commit()

def update_last_interaction(user_id):
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
def is_admin(user_id):
    return str(user_id) == ADMIN_USER_ID

# ===================== NAVIGATION HELPERS ======================
def send_main_menu(chat_id, user_id=None):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('🕒 Sky Clock', '🕯 Wax Events')
    markup.row('💎 Shards', '⚙️ Settings')
    
    if user_id and is_admin(user_id):
        markup.row('👤 Admin Panel')
    
    bot.send_message(chat_id, "Main Menu:", reply_markup=markup)

def send_wax_menu(chat_id):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('🧓 Grandma', '🐢 Turtle', '🌋 Geyser')
    markup.row('🔙 Main Menu')
    bot.send_message(chat_id, "Wax Events:", reply_markup=markup)

def send_settings_menu(chat_id, current_format):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(f'🕰 Change Time Format (Now: {current_format})')
    markup.row('🔙 Main Menu')
    bot.send_message(chat_id, "Settings:", reply_markup=markup)

def send_admin_menu(chat_id):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('👥 User Stats', '📢 Broadcast')
    markup.row('⏰ Manage Reminders', '📊 System Status')
    markup.row('🔍 Find User')
    markup.row('🔙 Main Menu')
    bot.send_message(chat_id, "Admin Panel:", reply_markup=markup)

# ======================= GLOBAL HANDLERS =======================
@bot.message_handler(func=lambda msg: msg.text == '🔙 Main Menu')
def handle_back_to_main(message):
    update_last_interaction(message.from_user.id)
    send_main_menu(message.chat.id, message.from_user.id)

@bot.message_handler(func=lambda msg: msg.text == '🔙 Admin Panel')
def handle_back_to_admin(message):
    update_last_interaction(message.from_user.id)
    if is_admin(message.from_user.id):
        send_admin_menu(message.chat.id)

# ======================= START FLOW ============================
@bot.message_handler(commands=['start'])
def start(message):
    try:
        update_last_interaction(message.from_user.id)
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.row('🇲🇲 Set to Myanmar Time')
        bot.send_message(
            message.chat.id,
            f"Hello {message.from_user.first_name}! 👋\nWelcome to Sky Clock Bot!\n\n"
            "Please type your timezone (e.g. Asia/Yangon), or choose an option:",
            reply_markup=markup
        )
        bot.register_next_step_handler(message, save_timezone)
    except Exception as e:
        logger.error(f"Error in /start: {str(e)}")
        bot.send_message(message.chat.id, "⚠️ Error in /start command")

def save_timezone(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    try:
        if message.text == '🇲🇲 Set to Myanmar Time':
            tz = 'Asia/Yangon'
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
@bot.message_handler(func=lambda msg: msg.text == '🕒 Sky Clock')
def sky_clock(message):
    update_last_interaction(message.from_user.id)
    user = get_user(message.from_user.id)
    if not user: 
        bot.send_message(message.chat.id, "Please set your timezone first with /start")
        return
        
    tz, fmt = user
    user_tz = pytz.timezone(tz)
    now = datetime.now()
    local = now.astimezone(user_tz)
    sky = now.astimezone(SKY_TZ)
    
    time_diff = local - sky
    hours, remainder = divmod(abs(time_diff.seconds), 3600)
    minutes = remainder // 60
    direction = "ahead" if time_diff.total_seconds() > 0 else "behind"
    
    text = (
        f"🌥 Sky Time: {format_time(sky, fmt)}\n"
        f"🌍 Your Time: {format_time(local, fmt)}\n"
        f"⏱ You are {hours}h {minutes}m {direction} Sky Time"
    )
    bot.send_message(message.chat.id, text)

@bot.message_handler(func=lambda msg: msg.text == '🕯 Wax Events')
def wax_menu(message):
    update_last_interaction(message.from_user.id)
    send_wax_menu(message.chat.id)

@bot.message_handler(func=lambda msg: msg.text == '⚙️ Settings')
def settings_menu(message):
    update_last_interaction(message.from_user.id)
    user = get_user(message.from_user.id)
    if not user: 
        bot.send_message(message.chat.id, "Please set your timezone first with /start")
        return
        
    _, fmt = user
    send_settings_menu(message.chat.id, fmt)

@bot.message_handler(func=lambda msg: msg.text == '💎 Shards')
def shards_menu(message):
    update_last_interaction(message.from_user.id)
    user = get_user(message.from_user.id)
    if not user: 
        bot.send_message(message.chat.id, "Please set your timezone first with /start")
        return
        
    tz, fmt = user
    user_tz = pytz.timezone(tz)
    now = datetime.now(user_tz)
    
    # Shard event times (every 2 hours at :05)
    event_times = []
    for hour in range(0, 24, 2):
        event_times.append(now.replace(hour=hour, minute=5, second=0, microsecond=0))
    
    # Find next shard event
    next_event = next((et for et in event_times if et > now), event_times[0] + timedelta(days=1))
    diff = next_event - now
    hrs, mins = divmod(diff.seconds // 60, 60)
    
    text = (
        "💎 Shard Events occur every 2 hours at :05\n\n"
        f"Next Shard Event: {format_time(next_event, fmt)}\n"
        f"⏳ Time Remaining: {hrs}h {mins}m"
    )
    
    bot.send_message(message.chat.id, text)

# ====================== WAX EVENT HANDLERS =====================
@bot.message_handler(func=lambda msg: msg.text in ['🧓 Grandma', '🐢 Turtle', '🌋 Geyser'])
def handle_event(message):
    update_last_interaction(message.from_user.id)
    mapping = {
        '🧓 Grandma': ('Grandma', 'every 2 hours at :05', 'even'),
        '🐢 Turtle': ('Turtle', 'every 2 hours at :20', 'even'),
        '🌋 Geyser': ('Geyser', 'every 2 hours at :35', 'odd')
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
            # If event already passed today, use tomorrow's time
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
        # Add current time
        time_str = format_time(sorted_event_times[i], fmt)
        row.append(time_str)
        
        # Add next time if exists
        if i+1 < len(sorted_event_times):
            time_str2 = format_time(sorted_event_times[i+1], fmt)
            row.append(time_str2)
        
        markup.row(*row)
    
    markup.row('🔙 Wax Events')
    
    bot.send_message(message.chat.id, text, reply_markup=markup)
    bot.register_next_step_handler(message, ask_reminder_frequency, event_name)

def ask_reminder_frequency(message, event_type):
    update_last_interaction(message.from_user.id)
    # Handle back navigation
    if message.text.strip() == '🔙 Wax Events':
        send_wax_menu(message.chat.id)
        return
        
    try:
        # Clean up selected time (remove emojis and indicators)
        selected_time = message.text.replace("⏩", "").replace("(Next)", "").strip()
        
        # Ask for reminder frequency
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.row('⏰ One Time Reminder')
        markup.row('🔄 Daily Reminder')
        markup.row('🔙 Wax Events')
        
        bot.send_message(
            message.chat.id,
            f"⏰ You selected: {selected_time}\n\n"
            "Choose reminder frequency:",
            reply_markup=markup
        )
        # Pass selected_time to next handler
        bot.register_next_step_handler(message, ask_reminder_minutes, event_type, selected_time)
    except Exception as e:
        logger.error(f"Error in frequency selection: {str(e)}")
        bot.send_message(message.chat.id, "⚠️ Invalid selection. Please try again.")
        send_wax_menu(message.chat.id)

def ask_reminder_minutes(message, event_type, selected_time):
    update_last_interaction(message.from_user.id)
    # Handle back navigation
    if message.text.strip() == '🔙 Wax Events':
        send_wax_menu(message.chat.id)
        return
        
    try:
        # Get frequency choice
        if message.text == '⏰ One Time Reminder':
            is_daily = False
        elif message.text == '🔄 Daily Reminder':
            is_daily = True
        else:
            bot.send_message(message.chat.id, "Please select a valid option")
            return
            
        # Create keyboard with common minute options
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.row('5', '10', '15')
        markup.row('20', '30', '45')
        markup.row('60', '🔙 Wax Events')
        
        bot.send_message(
            message.chat.id, 
            f"⏰ Event: {event_type}\n"
            f"🕑 Time: {selected_time}\n"
            f"🔄 Frequency: {'Daily' if is_daily else 'One-time'}\n\n"
            "How many minutes before should I remind you?\n"
            "Choose an option or type a number (1-60):",
            reply_markup=markup
        )
        # Pass all needed parameters to next handler
        bot.register_next_step_handler(message, save_reminder, event_type, selected_time, is_daily)
    except Exception as e:
        logger.error(f"Error in minutes selection: {str(e)}")
        bot.send_message(message.chat.id, "⚠️ Failed to set reminder. Please try again.")
        send_wax_menu(message.chat.id)

import re

# bot.py - Fixed Version with Reminder Flow Fixes
# ... [code unchanged until inside save_reminder() function] ...

# bot.py - Enhanced with Debug Logs in save_reminder()
# ... [unchanged code above] ...

def save_reminder(message, event_type, selected_time, is_daily):
    update_last_interaction(message.from_user.id)
    if message.text.strip() == '🔙 Wax Events':
        send_wax_menu(message.chat.id)
        return

    try:
        import re
        # Extract numbers from input text (handles button clicks and typed numbers)
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

        # Parse time based on user's format
        try:
            if fmt == '12hr':
                try:
                    time_obj = datetime.strptime(clean_time, '%I:%M%p')
                except:
                    time_obj = datetime.strptime(clean_time, '%I:%M')
            else:
                time_obj = datetime.strptime(clean_time, '%H:%M')
        except ValueError:
            try:
                time_obj = datetime.strptime(clean_time, '%H:%M')
            except:
                raise ValueError(f"Couldn't parse time: {clean_time}")

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
                chat_id = message.chat.id  # Add this line before the query

                cur.execute("""
                INSERT INTO reminders (
                    user_id, chat_id, event_type, event_time_utc, trigger_time,
                    notify_before, is_daily, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                RETURNING id
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
        markup.row('60', '🔙 Wax Events')
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

# ... rest of code unchanged ...



# ==================== REMINDER SCHEDULING =====================
def schedule_reminder(user_id, reminder_id, event_type, event_time_utc, notify_before, is_daily):
    try:
        # Calculate when to send the notification (UTC)
        notify_time = event_time_utc - timedelta(minutes=notify_before)
        current_time = datetime.now(pytz.utc)
        
        # If notification time is in the past, adjust for daily or skip
        if notify_time < current_time:
            if is_daily:
                notify_time += timedelta(days=1)
                event_time_utc += timedelta(days=1)
                # Update database with new time
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
        
        # Schedule the job
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

def send_reminder_notification(user_id, reminder_id, event_type, event_time_utc, notify_before, is_daily):
    try:
        # Get user info
        user_info = get_user(user_id)
        if not user_info:
            logger.warning(f"User {user_id} not found for reminder {reminder_id}")
            return
            
        tz, fmt = user_info
        user_tz = pytz.timezone(tz)
        
        # Convert event time to user's timezone
        event_time_user = event_time_utc.astimezone(user_tz)
        event_time_str = format_time(event_time_user, fmt)
        
        # Prepare message
        message = (
            f"⏰ Reminder: {event_type} is starting in {notify_before} minutes!\n"
            f"🕑 Event Time: {event_time_str}"
        )
        
        # Send message
        bot.send_message(user_id, message)
        logger.info(f"Sent reminder for {event_type} to user {user_id}")
        
        # Reschedule if daily
        if is_daily:
            new_event_time = event_time_utc + timedelta(days=1)
            schedule_reminder(user_id, reminder_id, event_type, 
                             new_event_time, notify_before, True)
            
            # Update database
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
        # Attempt to notify admin
        try:
            bot.send_message(ADMIN_USER_ID, f"⚠️ Reminder failed: {reminder_id}\nError: {str(e)}")
        except:
            pass

# ======================= ADMIN PANEL ===========================
@bot.message_handler(func=lambda msg: msg.text == '👤 Admin Panel' and is_admin(msg.from_user.id))
def handle_admin_panel(message):
    update_last_interaction(message.from_user.id)
    send_admin_menu(message.chat.id)

# User Statistics
@bot.message_handler(func=lambda msg: msg.text == '👥 User Stats' and is_admin(msg.from_user.id))
def user_stats(message):
    try:
        update_last_interaction(message.from_user.id)
        with get_db() as conn:
            with conn.cursor() as cur:
                # Total users
                cur.execute("SELECT COUNT(*) FROM users")
                total_users = cur.fetchone()[0]
                
                # Active users (last 7 days)
                cur.execute("""
                    SELECT COUNT(*) 
                    FROM users 
                    WHERE last_interaction > NOW() - INTERVAL '7 days'
                """)
                active_users = cur.fetchone()[0]
                
                # Users with reminders
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

# Broadcast Messaging
@bot.message_handler(func=lambda msg: msg.text == '📢 Broadcast' and is_admin(msg.from_user.id))
def start_broadcast(message):
    update_last_interaction(message.from_user.id)
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('🔊 Broadcast to All')
    markup.row('👤 Send to Specific User')
    markup.row('🔙 Admin Panel')
    bot.send_message(message.chat.id, "Choose broadcast type:", reply_markup=markup)

@bot.message_handler(func=lambda msg: msg.text == '🔊 Broadcast to All' and is_admin(msg.from_user.id))
def broadcast_to_all(message):
    update_last_interaction(message.from_user.id)
    msg = bot.send_message(message.chat.id, "Enter message to broadcast to ALL users (type /cancel to abort):")
    bot.register_next_step_handler(msg, process_broadcast_all)

@bot.message_handler(func=lambda msg: msg.text == '👤 Send to Specific User' and is_admin(msg.from_user.id))
def send_to_user(message):
    update_last_interaction(message.from_user.id)
    msg = bot.send_message(message.chat.id, "Enter target USER ID (type /cancel to abort):")
    bot.register_next_step_handler(msg, get_target_user)

def get_target_user(message):
    update_last_interaction(message.from_user.id)
    if message.text.strip().lower() == '/cancel':
        send_admin_menu(message.chat.id)
        return
        
    try:
        user_id = int(message.text.strip())
        # Store user ID in message object for next step
        message.target_user_id = user_id
        msg = bot.send_message(message.chat.id, f"Enter message for user {user_id}:")
        bot.register_next_step_handler(msg, process_user_message)
    except ValueError:
        bot.send_message(message.chat.id, "❌ Invalid user ID. Must be a number. Try again:")
        bot.register_next_step_handler(message, get_target_user)

def process_user_message(message):
    update_last_interaction(message.from_user.id)
    if message.text.strip().lower() == '/cancel':
        send_admin_menu(message.chat.id)
        return
        
    target_user_id = getattr(message, 'target_user_id', None)
    if not target_user_id:
        bot.send_message(message.chat.id, "❌ Error: User ID not found. Please start over.")
        return send_admin_menu(message.chat.id)
        
    try:
        # Get user's chat_id from database
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

def process_broadcast_all(message):
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
    
    # Send with progress updates
    progress_msg = bot.send_message(message.chat.id, f"📤 Sending broadcast... 0/{total}")
    
    for i, chat_id in enumerate(chat_ids):
        try:
            bot.send_message(chat_id, f"📢 Admin Broadcast:\n\n{broadcast_text}")
            success += 1
        except Exception as e:
            logger.error(f"Broadcast failed for {chat_id}: {str(e)}")
            failed += 1
            
        # Update progress every 10 messages or last message
        if (i + 1) % 10 == 0 or (i + 1) == total:
            try:
                bot.edit_message_text(
                    f"📤 Sending broadcast... {i+1}/{total}",
                    message.chat.id,
                    progress_msg.message_id
                )
            except:
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
@bot.message_handler(func=lambda msg: msg.text == '⏰ Manage Reminders' and is_admin(msg.from_user.id))
def manage_reminders(message):
    update_last_interaction(message.from_user.id)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT r.id, u.user_id, r.event_type, r.event_time_utc, r.notify_before
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

def handle_reminder_action(message, reminders):
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
                    
            # Also remove from scheduler if exists
            try:
                scheduler.remove_job(f'rem_{rem_id}')
                logger.info(f"Removed job for reminder {rem_id}")
            except:
                pass
                
            bot.send_message(message.chat.id, "✅ Reminder deleted")
        else:
            bot.send_message(message.chat.id, "Invalid selection")
    except ValueError:
        bot.send_message(message.chat.id, "Please enter a valid number")
    
    send_admin_menu(message.chat.id)

# System Status
@bot.message_handler(func=lambda msg: msg.text == '📊 System Status' and is_admin(msg.from_user.id))
def system_status(message):
    update_last_interaction(message.from_user.id)
    # Uptime calculation
    uptime = datetime.now() - start_time
    
    # Database status
    db_status = "✅ Connected"
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
    except Exception as e:
        db_status = f"❌ Error: {str(e)}"
    
    # Recent errors
    error_count = 0
    try:
        with open('bot.log', 'r') as f:
            for line in f:
                if 'ERROR' in line:
                    error_count += 1
    except Exception as e:
        error_count = f"Error reading log: {str(e)}"
    
    # Memory usage
    memory = psutil.virtual_memory()
    memory_usage = f"{memory.used / (1024**3):.1f}GB / {memory.total / (1024**3):.1f}GB ({memory.percent}%)"
    
    # Active jobs
    try:
        job_count = len(scheduler.get_jobs())
    except:
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
@bot.message_handler(func=lambda msg: msg.text == '🔍 Find User' and is_admin(msg.from_user.id))
def find_user(message):
    update_last_interaction(message.from_user.id)
    msg = bot.send_message(message.chat.id, "Enter username or user ID to search (type /cancel to abort):")
    bot.register_next_step_handler(msg, process_user_search)

def process_user_search(message):
    update_last_interaction(message.from_user.id)
    if message.text.strip().lower() == '/cancel':
        send_admin_menu(message.chat.id)
        return
        
    search_term = message.text.strip()
    
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                # Try searching by user ID
                if search_term.isdigit():
                    cur.execute(
                        "SELECT user_id, chat_id, timezone FROM users WHERE user_id = %s",
                        (int(search_term),)
                    )
                    results = cur.fetchall()
                # Search by timezone
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
    return 'Sky Clock Bot is running.'

# ========================== MAIN ===============================
if __name__ == '__main__':
    logger.info("Initializing database...")
    init_db()
    logger.info("Database initialized")
    
    # Schedule existing reminders on startup
    logger.info("Scheduling existing reminders...")
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, user_id, event_type, event_time_utc, notify_before, is_daily
                    FROM reminders
                    WHERE event_time_utc > NOW() - INTERVAL '1 day'
                """)
                reminders = cur.fetchall()
                for rem in reminders:
                    schedule_reminder(rem[1], rem[0], rem[2], rem[3], rem[4], rem[5])
                logger.info(f"Scheduled {len(reminders)} existing reminders")
    except Exception as e:
        logger.error(f"Error scheduling existing reminders: {str(e)}")
    
    logger.info("Setting up webhook...")
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    logger.info(f"Webhook set to: {WEBHOOK_URL}")
    
    logger.info("Starting Flask app...")
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))