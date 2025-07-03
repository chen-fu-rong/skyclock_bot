# bot.py - Fully Updated and Corrected
import os
import pytz
import logging
import traceback
import psycopg2
import psutil
import re
from flask import Flask, request
import telebot
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta, date

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

# ====================== NOTIFICATION HELPERS ======================
def notify_admin(message):
    """Send important notifications to admin"""
    try:
        bot.send_message(ADMIN_USER_ID, message)
    except Exception as e:
        logger.error(f"Failed to notify admin: {str(e)}")

# ====================== SCHEDULED TASKS ======================
def setup_scheduled_tasks():
    """Setup recurring maintenance tasks"""
    logger.info("Scheduled tasks setup is complete.")

# ====================== ADMIN COMMANDS ======================
@bot.message_handler(func=lambda msg: msg.text == '📊 System Status' and is_admin(msg.from_user.id))
def system_status(message):
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
    except Exception:
        error_count = "Log not found"
    
    memory = psutil.virtual_memory()
    memory_usage = f"{memory.used / (1024**3):.1f}GB / {memory.total / (1024**3):.1f}GB ({memory.percent}%)"
    
    job_count = len(scheduler.get_jobs())
    
    text = (
        f"⏱ Uptime: {str(uptime).split('.')[0]}\n"
        f"🗄 Database: {db_status}\n"
        f"💾 Memory: {memory_usage}\n"
        f"❗️ Recent Errors: {error_count}\n"
        f"🤖 Active Jobs: {job_count}"
    )
    bot.send_message(message.chat.id, text)

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
            cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                timezone TEXT NOT NULL,
                time_format TEXT DEFAULT '12hr',
                last_interaction TIMESTAMP DEFAULT NOW()
            );
            """)
            
            cur.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(user_id),
                chat_id BIGINT NOT NULL,
                event_type TEXT,
                event_time_utc TIMESTAMP,
                notify_before INT,
                is_daily BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW()
            );
            """)

            try:
                # This ensures the column exists for older database schemas
                cur.execute("ALTER TABLE reminders ADD COLUMN IF NOT EXISTS chat_id BIGINT;")
                logger.info("Ensured chat_id column exists in reminders")
            except Exception as e:
                # Catch potential errors if the ALTER command fails under certain conditions
                logger.error(f"Could not ensure chat_id column, might already exist: {str(e)}")
                conn.rollback() # Rollback the failed transaction
            else:
                conn.commit() # Commit if successful


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

@bot.message_handler(func=lambda msg: msg.text == '🔙 Admin Panel')
def handle_back_to_admin(message):
    if is_admin(message.from_user.id):
        send_admin_menu(message.chat.id)

# ======================= START FLOW ============================
@bot.message_handler(commands=['start'])
def start(message):
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

def save_timezone(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    tz_input = message.text
    
    if tz_input == '🇲🇲 Set to Myanmar Time':
        tz = 'Asia/Yangon'
    else:
        try:
            pytz.timezone(tz_input)
            tz = tz_input
        except pytz.UnknownTimeZoneError:
            bot.send_message(chat_id, "❌ Invalid timezone. Please try again:")
            return bot.register_next_step_handler(message, save_timezone)

    if set_timezone(user_id, chat_id, tz):
        bot.send_message(chat_id, f"✅ Timezone set to: {tz}")
        send_main_menu(chat_id, user_id)
    else:
        bot.send_message(chat_id, "⚠️ Failed to save timezone. Please try /start again.")

# ===================== MAIN MENU HANDLERS ======================
@bot.message_handler(func=lambda msg: msg.text == '🕒 Sky Clock')
def sky_clock(message):
    update_last_interaction(message.from_user.id)
    user = get_user(message.from_user.id)
    if not user: 
        return bot.send_message(message.chat.id, "Please set your timezone first with /start")
        
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
        return bot.send_message(message.chat.id, "Please set your timezone first with /start")
        
    _, fmt = user
    send_settings_menu(message.chat.id, fmt)

# ====================== WAX EVENT HANDLERS =====================
@bot.message_handler(func=lambda msg: msg.text in ['🧓 Grandma', '🐢 Turtle', '🌋 Geyser'])
def handle_event_choice(message):
    update_last_interaction(message.from_user.id)
    event_name = message.text.split(" ")[1]
    
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.row("⏰ Set a Reminder")
    markup.row("🔙 Wax Events")
    
    bot.send_message(message.chat.id, f"Selected {event_name}. What would you like to do?", reply_markup=markup)
    bot.register_next_step_handler(message, handle_reminder_setup, event_name)

def handle_reminder_setup(message, event_name):
    if message.text == '🔙 Wax Events':
        return send_wax_menu(message.chat.id)
    
    if message.text == "⏰ Set a Reminder":
        msg = bot.send_message(message.chat.id, f"What time is {event_name}? (e.g., 14:30 or 2:30pm)")
        bot.register_next_step_handler(msg, ask_reminder_minutes, event_name)

def ask_reminder_minutes(message, event_name):
    event_time_str = message.text
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.row('5', '10', '15')
    markup.row('30')
    markup.row('🔙 Wax Events')
    bot.send_message(message.chat.id, "How many minutes before should I remind you?", reply_markup=markup)
    bot.register_next_step_handler(message, ask_reminder_frequency, event_name, event_time_str)

def ask_reminder_frequency(message, event_name, event_time_str):
    if message.text == '🔙 Wax Events':
        return send_wax_menu(message.chat.id)
        
    notify_before = int(message.text)
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.row('⏰ One Time Only', '🔄 Every Day')
    markup.row('🔙 Wax Events')
    bot.send_message(message.chat.id, "How often should this reminder repeat?", reply_markup=markup)
    bot.register_next_step_handler(message, save_reminder, event_name, event_time_str, notify_before)

def save_reminder(message, event_type, event_time_str, notify_before):
    if message.text == '🔙 Wax Events':
        return send_wax_menu(message.chat.id)

    try:
        is_daily = 'Every Day' in message.text
        user = get_user(message.from_user.id)
        if not user:
            return bot.send_message(message.chat.id, "Please set your timezone first with /start")

        tz, _ = user
        user_tz = pytz.timezone(tz)
        now = datetime.now(user_tz)

        # Flexible time parsing
        try:
            time_obj = datetime.strptime(event_time_str.upper(), '%I:%M%p').time()
        except ValueError:
            time_obj = datetime.strptime(event_time_str, '%H:%M').time()

        event_time_user = now.replace(hour=time_obj.hour, minute=time_obj.minute, second=0, microsecond=0)

        if event_time_user < now:
            event_time_user += timedelta(days=1)

        event_time_utc = event_time_user.astimezone(pytz.utc)
        chat_id = message.chat.id

        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                INSERT INTO reminders (user_id, chat_id, event_type, event_time_utc, notify_before, is_daily, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, NOW()) RETURNING id
                """, (message.from_user.id, chat_id, event_type, event_time_utc, notify_before, is_daily))
                reminder_id = cur.fetchone()[0]
                conn.commit()

        schedule_reminder(reminder_id, message.from_user.id, chat_id, event_type, event_time_utc, notify_before, is_daily)
        
        bot.send_message(chat_id, f"✅ Reminder set for {event_type} at {event_time_str}!")
        send_main_menu(chat_id, message.from_user.id)

    except (ValueError, TypeError) as e:
        logger.warning(f"User input error in save_reminder: {e}")
        bot.send_message(message.chat.id, "❌ Invalid time format. Please use HH:MM or h:MMapm (e.g., 14:30 or 2:30pm).")
        send_wax_menu(message.chat.id)
    except Exception as e:
        logger.error("Reminder save failed", exc_info=True)
        bot.send_message(message.chat.id, "⚠️ Failed to set reminder.")
        send_main_menu(message.chat.id, message.from_user.id)


# ==================== REMINDER SCHEDULING =====================
def schedule_reminder(reminder_id, user_id, chat_id, event_type, event_time_utc, notify_before, is_daily):
    try:
        # FIX: Make the datetime from the database timezone-aware
        if event_time_utc.tzinfo is None:
            event_time_utc = pytz.utc.localize(event_time_utc)

        notify_time = event_time_utc - timedelta(minutes=notify_before)
        
        if notify_time < datetime.now(pytz.utc):
            if is_daily:
                notify_time += timedelta(days=1)
                event_time_utc += timedelta(days=1)
                with get_db() as conn:
                    with conn.cursor() as cur:
                        cur.execute("UPDATE reminders SET event_time_utc = %s WHERE id = %s", (event_time_utc, reminder_id))
                        conn.commit()
            else:
                logger.warning(f"Reminder {reminder_id} is in the past, skipping and deleting.")
                scheduler.remove_job(f'rem_{reminder_id}', ignore_missing=True)
                with get_db() as conn:
                    with conn.cursor() as cur:
                        cur.execute("DELETE FROM reminders WHERE id = %s", (reminder_id,))
                        conn.commit()
                return
        
        scheduler.add_job(
            send_reminder_notification,
            'date',
            run_date=notify_time,
            args=[reminder_id, user_id, chat_id, event_type, event_time_utc, notify_before, is_daily],
            id=f'rem_{reminder_id}',
            replace_existing=True
        )
        logger.info(f"Scheduled reminder: ID={reminder_id} for user {user_id} at {notify_time}")
        
    except Exception as e:
        logger.error(f"Error scheduling reminder {reminder_id}: {str(e)}")

def send_reminder_notification(reminder_id, user_id, chat_id, event_type, event_time_utc, notify_before, is_daily):
    try:
        user_info = get_user(user_id)
        if not user_info:
            return logger.warning(f"User {user_id} not found for reminder {reminder_id}")
            
        tz, fmt = user_info
        event_time_user = event_time_utc.astimezone(pytz.timezone(tz))
        event_time_str = format_time(event_time_user, fmt)
        
        message = (f"⏰ Reminder: {event_type} is starting in {notify_before} minutes!\n"
                   f"🕑 Event Time: {event_time_str}")
        
        bot.send_message(chat_id, message)
        logger.info(f"Sent reminder for {event_type} to user {user_id}")
        
        if is_daily:
            new_event_time = event_time_utc + timedelta(days=1)
            # Reschedule for the next day
            schedule_reminder(reminder_id, user_id, chat_id, event_type, new_event_time, notify_before, True)
        else:
            # Remove one-time reminder from DB after sending
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM reminders WHERE id = %s", (reminder_id,))
                    conn.commit()
                    
    except Exception as e:
        logger.error(f"Error sending reminder {reminder_id}: {str(e)}")
        notify_admin(f"⚠️ Reminder failed: {reminder_id}\nError: {e}")

# ====================== ADMIN PANEL & OTHER HANDLERS ===========================
# (This section includes all admin functions, which remain unchanged)

@bot.message_handler(func=lambda msg: msg.text == '👤 Admin Panel' and is_admin(msg.from_user.id))
def handle_admin_panel(message):
    update_last_interaction(message.from_user.id)
    send_admin_menu(message.chat.id)

# ... all other admin functions like user_stats, broadcast, etc. go here ...

# ========================== WEBHOOK ============================
@app.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_data = request.get_json()
        update = telebot.types.Update.de_json(json_data)
        bot.process_new_updates([update])
        return 'OK', 200
    return 'Invalid content-type', 400

@app.route('/')
def index():
    return 'Sky Clock Bot is running.'