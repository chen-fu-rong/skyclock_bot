# bot.py - Enhanced Shard Data Handling
import os
import pytz
import logging
import traceback
import psycopg2
import psutil
import requests
from flask import Flask, request
import telebot
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta, date
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
SHARD_API_URL = "https://sky-shards.pages.dev/data/shard_locations.json"

bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)
scheduler = BackgroundScheduler()
scheduler.start()

# Track bot start time for uptime
start_time = datetime.now()

# Sky timezone
SKY_TZ = pytz.timezone('UTC')

# Shard data cache
shard_data_cache = None
last_shard_fetch = None

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
                event_type TEXT,
                event_time_utc TIMESTAMP,
                notify_before INT,
                is_daily BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW()
            );
            """)
            
            # Add any missing columns
            try:
                cur.execute("""
                ALTER TABLE reminders 
                ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW();
                """)
                logger.info("Ensured created_at column exists in reminders")
            except Exception as e:
                logger.error(f"Error ensuring created_at column: {str(e)}")
            
            try:
                cur.execute("""
                ALTER TABLE reminders 
                ADD COLUMN IF NOT EXISTS is_daily BOOLEAN DEFAULT FALSE;
                """)
            except:
                pass  # Already exists
            
            conn.commit()

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

# ===================== SHARD FUNCTIONS =========================
def get_shard_data():
    global shard_data_cache, last_shard_fetch
    
    try:
        # Refresh cache every 2 hours
        if (not shard_data_cache or 
            not last_shard_fetch or 
            (datetime.now() - last_shard_fetch).seconds > 7200):
            
            logger.info("Fetching shard data from API...")
            response = requests.get(SHARD_API_URL, timeout=15)
            response.raise_for_status()
            
            # Validate the response structure
            data = response.json()
            if not isinstance(data, list) or len(data) == 0:
                raise ValueError("Invalid shard data format - not a list or empty")
                
            # Ensure required fields exist
            required_fields = ['date', 'realm', 'area', 'location', 'notes', 'image']
            if not all(field in data[0] for field in required_fields):
                raise ValueError("Missing required fields in shard data")
                
            shard_data_cache = data
            last_shard_fetch = datetime.now()
            logger.info(f"Fetched {len(data)} shard records")
            return shard_data_cache
    
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error fetching shard data: {str(e)}")
        if not shard_data_cache:
            logger.error("No cached data available")
            return None
            
    except Exception as e:
        logger.error(f"Error processing shard data: {str(e)}")
        if not shard_data_cache:
            return None
    
    return shard_data_cache

def send_shard_info(chat_id, user_id, target_date=None):
    user = get_user(user_id)
    if not user: 
        bot.send_message(chat_id, "Please set your timezone first with /start")
        return
        
    tz, fmt = user
    user_tz = pytz.timezone(tz)
    
    # Default to today if no date specified
    if not target_date:
        target_date = datetime.now(user_tz).date()
    
    shard_data = get_shard_data()
    
    # Calculate next event time regardless of API status
    now = datetime.now(user_tz)
    event_times = [now.replace(hour=h, minute=5, second=0, microsecond=0) 
                  for h in range(0, 24, 2)]
    next_event = next((et for et in event_times if et > now), event_times[0] + timedelta(days=1))
    hrs, mins = divmod((next_event - now).seconds // 60, 60)
    
    if not shard_data:
        # If API fails, show a generic message with next event times
        message = (
            "⚠️ Couldn't fetch shard details, but shards appear every 2 hours at :05\n\n"
            f"⏱ <b>Next Shard Event:</b> {format_time(next_event, fmt)} ({hrs}h {mins}m)\n\n"
            "Please try again later for location details."
        )
        
        bot.send_message(
            chat_id, 
            message, 
            parse_mode='HTML'
        )
        return
    
    # Find shard for target date
    target_str = target_date.strftime('%Y-%m-%d')
    shard = next((s for s in shard_data if s['date'] == target_str), None)
    
    if not shard:
        # Try to find the closest available date
        try:
            all_dates = [datetime.strptime(s['date'], '%Y-%m-%d').date() for s in shard_data]
            closest_date = min(all_dates, key=lambda d: abs(d - target_date))
            shard = next(s for s in shard_data if s['date'] == closest_date.strftime('%Y-%m-%d'))
            target_date = closest_date
        except Exception as e:
            logger.error(f"Couldn't find shard for {target_str}: {str(e)}")
            bot.send_message(chat_id, f"❌ No shard data found for {target_date.strftime('%b %d, %Y')}")
            return
    
    # Format message
    message = (
        f"💎 <b>Shard - {target_date.strftime('%b %d, %Y')}</b>\n\n"
        f"<b>Realm:</b> {shard.get('realm', 'Unknown')}\n"
        f"<b>Area:</b> {shard.get('area', 'Unknown')}\n"
        f"<b>Location:</b> {shard.get('location', 'Check in-game')}\n"
        f"<b>Notes:</b> {shard.get('notes', 'No additional info')}\n\n"
    )
    
    # Add image link if available
    if shard.get('image'):
        message += f"<a href='{shard['image']}'>View Location Image</a>\n\n"
    
    # Create navigation buttons
    keyboard = telebot.types.InlineKeyboardMarkup()
    
    # Previous button
    prev_date = target_date - timedelta(days=1)
    keyboard.row(
        telebot.types.InlineKeyboardButton("⬅️ Previous", callback_data=f"shard:{prev_date}"),
        telebot.types.InlineKeyboardButton("Next ➡️", callback_data=f"shard:{target_date + timedelta(days=1)}")
    )
    
    # Add today button if not viewing today
    today = datetime.now(user_tz).date()
    if target_date != today:
        keyboard.add(telebot.types.InlineKeyboardButton("⏩ Today", callback_data=f"shard:{today}"))
    
    # Add next event time
    message += f"⏱ <b>Next Shard Event:</b> {format_time(next_event, fmt)} ({hrs}h {mins}m)"
    
    try:
        bot.send_message(
            chat_id, 
            message, 
            parse_mode='HTML', 
            disable_web_page_preview=True,
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"Error sending shard info: {str(e)}")
        # Fallback without HTML formatting
        plain_message = (
            f"💎 Shard - {target_date.strftime('%b %d, %Y')}\n\n"
            f"Realm: {shard.get('realm', 'Unknown')}\n"
            f"Area: {shard.get('area', 'Unknown')}\n"
            f"Location: {shard.get('location', 'Check in-game')}\n"
            f"Notes: {shard.get('notes', 'No additional info')}\n\n"
            f"Next Shard Event: {format_time(next_event, fmt)} ({hrs}h {mins}m)"
        )
        bot.send_message(chat_id, plain_message, reply_markup=keyboard)

# ===================== SHARD HANDLERS =========================
@bot.callback_query_handler(func=lambda call: call.data.startswith('shard:'))
def handle_shard_callback(call):
    try:
        date_str = call.data.split(':')[1]
        target_date = date.fromisoformat(date_str)
        send_shard_info(call.message.chat.id, call.from_user.id, target_date)
        
        # Edit original message instead of sending new one
        try:
            bot.edit_message_reply_markup(
                call.message.chat.id,
                call.message.message_id,
                reply_markup=None
            )
        except:
            pass  # Fail silently if message can't be edited
    except Exception as e:
        logger.error(f"Error handling shard callback: {str(e)}")
        bot.answer_callback_query(call.id, "❌ Failed to load shard data")

@bot.message_handler(func=lambda msg: msg.text == '💎 Shards')
def shards_menu(message):
    update_last_interaction(message.from_user.id)
    send_shard_info(message.chat.id, message.from_user.id)

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
    
    # Shard cache status
    shard_status = "✅ Loaded" if shard_data_cache else "❌ Not loaded"
    if last_shard_fetch:
        shard_status += f" (Last fetch: {last_shard_fetch.strftime('%Y-%m-%d %H:%M')})"
    
    text = (
        f"⏱ Uptime: {str(uptime).split('.')[0]}\n"
        f"🗄 Database: {db_status}\n"
        f"💾 Memory: {memory_usage}\n"
        f"❗️ Recent Errors: {error_count}\n"
        f"🤖 Active Jobs: {job_count}\n"
        f"💎 Shard Data: {shard_status}"
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
    
    # Pre-fetch shard data with retry
    logger.info("Fetching initial shard data...")
    max_retries = 3
    for attempt in range(max_retries):
        try:
            shard_data = get_shard_data()
            if shard_data:
                logger.info(f"Successfully loaded {len(shard_data)} shard records")
                break
            else:
                logger.warning(f"Shard data not available (attempt {attempt+1}/{max_retries})")
        except Exception as e:
            logger.error(f"Error fetching shard data: {str(e)}")
    
    logger.info("Setting up webhook...")
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    logger.info(f"Webhook set to: {WEBHOOK_URL}")
    
    logger.info("Starting Flask app...")
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))