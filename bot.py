# bot.py
import os
import pytz
import logging
from flask import Flask, request
import telebot
import psycopg2
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========================== CONFIG =============================
API_TOKEN = os.getenv("BOT_TOKEN") or "YOUR_BOT_TOKEN"
WEBHOOK_URL = os.getenv("WEBHOOK_URL") or "https://skyclock-bot.onrender.com/webhook"
DB_URL = os.getenv("DATABASE_URL") or "postgresql://user:pass@host:port/db"
SKY_TZ = pytz.timezone("America/Los_Angeles")

bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)
scheduler = BackgroundScheduler()
scheduler.start()

# ========================== STATE ==============================
user_sessions = {}

# ========================== DATABASE ===========================
def get_db():
    return psycopg2.connect(DB_URL, sslmode='require')

def init_db():
    with get_db() as conn:
        with conn.cursor() as cur:
            # Create tables if they don't exist
            cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                timezone TEXT NOT NULL,
                time_format TEXT DEFAULT '12hr'
            );
            CREATE TABLE IF NOT EXISTS reminders (
                id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(user_id),
                chat_id BIGINT NOT NULL,
                event_type TEXT NOT NULL,
                event_time_utc TIMESTAMP NOT NULL,
                notify_before INT NOT NULL,
                is_daily BOOLEAN DEFAULT FALSE
            );
            """)
            conn.commit()
    logger.info("Database initialization complete")

# ========================== WEBHOOK ============================
@app.route('/webhook', methods=['POST'])
def webhook():
    json_str = request.stream.read().decode('utf-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return 'OK', 200

@app.route('/')
def index():
    return 'Sky Clock Bot is running.'

# ======================== UTILITIES ============================
def format_time(dt, fmt):
    return dt.strftime('%I:%M %p') if fmt == '12hr' else dt.strftime('%H:%M')

def get_user(user_id):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT timezone, time_format FROM users WHERE user_id = %s", (user_id,))
            return cur.fetchone()

def set_timezone(user_id, chat_id, tz):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO users (user_id, chat_id, timezone) 
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET timezone = EXCLUDED.timezone;
            """, (user_id, chat_id, tz))
            conn.commit()

def set_time_format(user_id, fmt):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET time_format = %s WHERE user_id = %s", (fmt, user_id))
            conn.commit()

# ======================= EVENT LOGIC ===========================
def get_next_event(event_type):
    now_sky = datetime.now(SKY_TZ)
    today = now_sky.replace(minute=0, second=0, microsecond=0)
    times = []
    for hour in range(24):
        if event_type == 'grandma' and hour % 2 == 0:
            times.append(today.replace(hour=hour, minute=5))
        elif event_type == 'geyser' and hour % 2 == 1:
            times.append(today.replace(hour=hour, minute=35))
        elif event_type == 'turtle' and hour % 2 == 0:
            times.append(today.replace(hour=hour, minute=20))

    for t in times:
        if t > now_sky:
            return t
    return times[0] + timedelta(days=1)

# ======================= TELEGRAM UI ===========================
@bot.message_handler(commands=['start'])
def start(message):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.row('🇲🇲 Set to Myanmar Time')
    bot.send_message(message.chat.id, f"Hello {message.from_user.first_name}! 👋\nPlease type your timezone (e.g. Asia/Yangon), or choose an option:", reply_markup=markup)
    bot.register_next_step_handler(message, save_timezone)

def save_timezone(message):
    # FIXED: Properly handle Myanmar timezone button
    if message.text == '🇲🇲 Set to Myanmar Time':
        tz = 'Asia/Yangon'
    else:
        try:
            # Verify it's a valid timezone
            pytz.timezone(message.text)
            tz = message.text
        except pytz.UnknownTimeZoneError:
            bot.send_message(message.chat.id, "❌ Invalid timezone. Please try again:")
            return bot.register_next_step_handler(message, save_timezone)
        except Exception as e:
            logger.error(f"Timezone error: {e}")
            bot.send_message(message.chat.id, "❌ Invalid timezone. Please try again:")
            return bot.register_next_step_handler(message, save_timezone)

    set_timezone(message.from_user.id, message.chat.id, tz)
    bot.send_message(message.chat.id, f"✅ Timezone set to: {tz}")
    send_main_menu(message.chat.id)

def send_main_menu(chat_id):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('🕒 Sky Clock', '🕯 Wax')
    markup.row('💎 Shards', '⚙️ Settings')
    bot.send_message(chat_id, "🏠 Main Menu:", reply_markup=markup)

@bot.message_handler(func=lambda msg: msg.text == '🕒 Sky Clock')
def sky_clock(message):
    user = get_user(message.from_user.id)
    if not user: return
    tz, fmt = user
    user_tz = pytz.timezone(tz)
    now = datetime.now()
    local = now.astimezone(user_tz)
    sky = now.astimezone(SKY_TZ)
    text = f"🌥 Sky Time: {format_time(sky, fmt)}\n🌍 Your Time: {format_time(local, fmt)}"
    bot.send_message(message.chat.id, text)

@bot.message_handler(func=lambda msg: msg.text == '🕯 Wax')
def wax_menu(message):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('🧓 Grandma', '🐢 Turtle', '🌋 Geyser')
    markup.row('🔙 Back')
    bot.send_message(message.chat.id, "✨ Choose a wax event:", reply_markup=markup)

@bot.message_handler(func=lambda msg: msg.text in ['🧓 Grandma', '🐢 Turtle', '🌋 Geyser'])
def handle_event(message):
    mapping = {'🧓 Grandma': 'grandma', '🐢 Turtle': 'turtle', '🌋 Geyser': 'geyser'}
    event_type = mapping[message.text]
    user = get_user(message.from_user.id)
    if not user: 
        bot.send_message(message.chat.id, "❌ Timezone not set. Please use /start first.")
        return
        
    tz, fmt = user
    user_tz = pytz.timezone(tz)

    # Store event type in session
    user_id = message.from_user.id
    if user_id not in user_sessions:
        user_sessions[user_id] = {}
    user_sessions[user_id]['event_type'] = event_type

    # Get next event in user time
    next_event = get_next_event(event_type).astimezone(user_tz)
    now = datetime.now(user_tz)
    diff = next_event - now
    hrs, mins = divmod(diff.seconds // 60, 60)
    text = f"Next {event_type.capitalize()} event at {format_time(next_event, fmt)} ({hrs}h {mins}m left)"

    # Generate list of today's event times in user's timezone
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    now_sky = datetime.now(SKY_TZ)
    
    # Find the next 8 events (4 hours worth)
    event_times = []
    for i in range(8):
        event_time = now_sky + timedelta(hours=i*2)
        if event_type == 'grandma' and event_time.hour % 2 == 0:
            event_time = event_time.replace(minute=5, second=0, microsecond=0)
        elif event_type == 'turtle' and event_time.hour % 2 == 0:
            event_time = event_time.replace(minute=20, second=0, microsecond=0)
        elif event_type == 'geyser' and event_time.hour % 2 == 1:
            event_time = event_time.replace(minute=35, second=0, microsecond=0)
        else:
            continue
            
        # Convert to user's timezone
        user_event_time = event_time.astimezone(user_tz)
        event_times.append(user_event_time)
    
    # Sort and format event times
    event_times.sort()
    for event_time in event_times:
        display = format_time(event_time, fmt)
        markup.row(display)
    
    # Add new reminder type buttons
    markup.row('⏰ One-Time Reminder', '🔄 Daily Reminder')
    markup.row('🔙 Back')
    
    bot.send_message(message.chat.id, text + "\nChoose a time to get a reminder:", reply_markup=markup)
    bot.register_next_step_handler(message, ask_reminder_type)

def ask_reminder_type(message):
    if message.text == '🔙 Back':
        return wax_menu(message)
    
    user_id = message.from_user.id
    event_type = user_sessions.get(user_id, {}).get('event_type')
    if not event_type:
        bot.send_message(message.chat.id, "❌ Session expired. Please start over.")
        return send_main_menu(message.chat.id)
    
    # Handle new buttons
    if message.text in ['⏰ One-Time Reminder', '🔄 Daily Reminder']:
        is_daily = (message.text == '🔄 Daily Reminder')
        bot.send_message(message.chat.id, f"⏰ How many minutes before the event do you want to be reminded? (e.g. 5, 10)")
        bot.register_next_step_handler(message, save_reminder, event_type, None, is_daily)
        return
    
    # Store selected time in session
    selected_time = message.text.strip()
    if user_id not in user_sessions:
        user_sessions[user_id] = {}
    user_sessions[user_id]['selected_time'] = selected_time
    
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('⏰ One-Time', '🔄 Daily')
    bot.send_message(message.chat.id, f"Select reminder type for {selected_time}:", reply_markup=markup)
    bot.register_next_step_handler(message, process_reminder_type, event_type, selected_time)

def process_reminder_type(message, event_type, selected_time):
    if message.text not in ['⏰ One-Time', '🔄 Daily']:
        bot.send_message(message.chat.id, "Please select a valid reminder type")
        return bot.register_next_step_handler(message, process_reminder_type, event_type, selected_time)
    
    is_daily = (message.text == '🔄 Daily')
    bot.send_message(message.chat.id, f"⏰ How many minutes before {selected_time} do you want to be reminded?")
    bot.register_next_step_handler(message, save_reminder, event_type, selected_time, is_daily)

def save_reminder(message, event_type, event_time_str, is_daily):
    try:
        mins = int(message.text.strip())
        user = get_user(message.from_user.id)
        if not user: 
            bot.send_message(message.chat.id, "❌ User not found. Please set your timezone first.")
            return
            
        tz, fmt = user
        user_tz = pytz.timezone(tz)
        user_id = message.from_user.id
        
        if event_time_str:
            # Parse selected time
            try:
                if fmt == '12hr':
                    time_obj = datetime.strptime(event_time_str, '%I:%M %p').time()
                else:
                    time_obj = datetime.strptime(event_time_str, '%H:%M').time()
            except ValueError:
                bot.send_message(message.chat.id, "❌ Invalid time format. Please try again.")
                return
                
            # Get today's date in user's timezone
            now_user = datetime.now(user_tz)
            event_time_user = now_user.replace(hour=time_obj.hour, minute=time_obj.minute, second=0, microsecond=0)
            
            # If the time has already passed today, use tomorrow
            if event_time_user < now_user:
                event_time_user += timedelta(days=1)
                
            event_time_utc = event_time_user.astimezone(pytz.utc)
        else:
            # Use next event
            next_event = get_next_event(event_type)
            event_time_utc = next_event.astimezone(pytz.utc)
        
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO reminders (user_id, chat_id, event_type, event_time_utc, notify_before, is_daily)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (message.from_user.id, message.chat.id, event_type, event_time_utc, mins, is_daily))
                conn.commit()
                
        schedule_reminder(message.chat.id, event_time_utc, mins, event_type, is_daily)
        bot.send_message(message.chat.id, f"✅ {'Daily' if is_daily else 'One-time'} reminder set! ({mins} minutes before)")
    except Exception as e:
        logger.error(f"Error saving reminder: {str(e)}", exc_info=True)
        bot.send_message(message.chat.id, "❌ Failed to set reminder. Please try again.")

def schedule_reminder(chat_id, event_time_utc, mins, event_type, is_daily):
    notify_time = event_time_utc - timedelta(minutes=mins)
    
    if is_daily:
        # Schedule daily job
        scheduler.add_job(
            lambda: bot.send_message(chat_id, f"⏰ Daily Reminder: {event_type.capitalize()} event in {mins} minutes!"),
            'cron',
            hour=notify_time.hour,
            minute=notify_time.minute,
            timezone=pytz.utc
        )
    else:
        # One-time job
        scheduler.add_job(
            lambda: bot.send_message(chat_id, f"⏰ Reminder: {event_type.capitalize()} event in {mins} minutes!"),
            trigger='date',
            run_date=notify_time
        )

@bot.message_handler(func=lambda msg: msg.text == '⚙️ Settings')
def settings_menu(message):
    user = get_user(message.from_user.id)
    if not user: return
    _, fmt = user
    new_fmt = '24hr' if fmt == '12hr' else '12hr'
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(f'🕰 Change Time Format (Now: {fmt})')
    markup.row('🔙 Back')
    bot.send_message(message.chat.id, "⚙️ Settings:", reply_markup=markup)

@bot.message_handler(func=lambda msg: 'Change Time Format' in msg.text)
def toggle_time_format(message):
    user = get_user(message.from_user.id)
    if not user: return
    _, fmt = user
    new_fmt = '24hr' if fmt == '12' else '12hr'
    set_time_format(message.from_user.id, new_fmt)
    bot.send_message(message.chat.id, f"✅ Time format changed to {new_fmt}")

@bot.message_handler(func=lambda msg: msg.text == '💎 Shards')
def shards_placeholder(message):
    bot.send_message(message.chat.id, "💎 Shards feature coming soon! 🚧")

@bot.message_handler(func=lambda msg: msg.text == '🔙 Back')
def go_back(message):
    send_main_menu(message.chat.id)

# ====================== RESCHEDULE REMINDERS ===================
def reschedule_reminders():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT chat_id, event_type, event_time_utc, notify_before FROM reminders")
            for chat_id, event_type, event_time_utc, notify_before in cur.fetchall():
                notify_time = event_time_utc - timedelta(minutes=notify_before)
                if notify_time > datetime.utcnow():
                    scheduler.add_job(
                        lambda cid=chat_id, et=event_type: bot.send_message(cid, f"⏰ Reminder: {et.capitalize()} event is starting soon!"),
                        trigger='date',
                        run_date=notify_time
                    )

def schedule_all_daily_reminders():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id, event_type, event_time_local, notify_before FROM subscriptions")
            for user_id, event_type, time_obj, notify_before in cur.fetchall():
                user = get_user(user_id)
                if not user:
                    continue
                tz, _ = user
                user_tz = pytz.timezone(tz)
                now = datetime.now(user_tz)
                target_time = now.replace(hour=time_obj.hour, minute=time_obj.minute, second=0, microsecond=0)
                reminder_time = target_time - timedelta(minutes=notify_before)
                if reminder_time < now:
                    reminder_time += timedelta(days=1)
                scheduler.add_job(
                    lambda uid=user_id, et=event_type: bot.send_message(uid, f"⏰ Daily reminder: {et.capitalize()} event is starting soon!"),
                    trigger='date',
                    run_date=reminder_time
                )


# ========================== MAIN ===============================
if __name__ == '__main__':
    logger.info("Starting bot...")
    init_db()
    reschedule_reminders()
    schedule_all_daily_reminders()
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))