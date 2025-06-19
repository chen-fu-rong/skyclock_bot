# bot.py — FIXED TIMEZONE SAVING
import os
import pytz
import logging
import traceback
from flask import Flask, request
import telebot
import psycopg2
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

API_TOKEN = os.getenv("BOT_TOKEN") or "YOUR_BOT_TOKEN"
WEBHOOK_URL = os.getenv("WEBHOOK_URL") or "https://skyclock-bot.onrender.com/webhook"
DB_URL = os.getenv("DATABASE_URL") or "postgresql://user:pass@host:port/db"

bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)
scheduler = BackgroundScheduler()
scheduler.start()

# ========================== DATABASE ===========================
def get_db():
    try:
        conn = psycopg2.connect(DB_URL, sslmode='require')
        logger.info("Database connection successful")
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
                time_format TEXT DEFAULT '12hr'
            );
            CREATE TABLE IF NOT EXISTS reminders (
                id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(user_id),
                event_type TEXT,
                event_time_utc TIMESTAMP,
                notify_before INT
            );
            """)
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

# ======================= TELEGRAM UI ===========================
@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, f"Hello {message.from_user.first_name}! 👋\nPlease type your timezone (e.g. Asia/Yangon):")
    bot.register_next_step_handler(message, save_timezone)

def save_timezone(message):
    try:
        pytz.timezone(message.text)
    except:
        bot.send_message(message.chat.id, "Invalid timezone. Try again:")
        return bot.register_next_step_handler(message, save_timezone)

    set_timezone(message.from_user.id, message.chat.id, message.text)
    send_main_menu(message.chat.id)

def send_main_menu(chat_id):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('🕒 Sky Clock', '🕯 Wax')
    markup.row('💎 Shards', '⚙️ Settings')
    bot.send_message(chat_id, "Main Menu:", reply_markup=markup)

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
    bot.send_message(message.chat.id, "Choose event:", reply_markup=markup)

@bot.message_handler(func=lambda msg: msg.text in ['🧓 Grandma', '🐢 Turtle', '🌋 Geyser'])
def handle_event(message):
    mapping = {'🧓 Grandma': 'grandma', '🐢 Turtle': 'turtle', '🌋 Geyser': 'geyser'}
    event_type = mapping[message.text]
    user = get_user(message.from_user.id)
    if not user: return
    tz, fmt = user
    user_tz = pytz.timezone(tz)

    # Generate local event times based on user's timezone
    now_user = datetime.now(user_tz)
    today_user = now_user.replace(hour=0, minute=0, second=0, microsecond=0)

    event_times = []
    for hour in range(24):
        if event_type == 'grandma' and hour % 2 == 0:
            event_times.append(today_user.replace(hour=hour, minute=5))
        elif event_type == 'turtle' and hour % 2 == 0:
            event_times.append(today_user.replace(hour=hour, minute=20))
        elif event_type == 'geyser' and hour % 2 == 1:
            event_times.append(today_user.replace(hour=hour, minute=35))

    # Find next event
    next_event = next((et for et in event_times if et > now_user), event_times[0] + timedelta(days=1))
    diff = next_event - now_user
    hrs, mins = divmod(diff.seconds // 60, 60)
    text = f"Next {event_type.capitalize()} event at {format_time(next_event, fmt)} ({hrs}h {mins}m left)"

    # Send buttons for all event times
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    for et in event_times:
        markup.row(format_time(et, fmt))
    markup.row('🔙 Back')

    bot.send_message(message.chat.id, text + "\nChoose a time to get a reminder:", reply_markup=markup)
    bot.register_next_step_handler(message, ask_reminder_time, event_type)

def ask_reminder_time(message, event_type):
    try:
        selected_time = message.text.strip()
        bot.send_message(message.chat.id, f"How many minutes before {selected_time} do you want to be reminded? (e.g. 5, 10)")
        bot.register_next_step_handler(message, save_reminder, event_type, selected_time)
    except:
        bot.send_message(message.chat.id, "Invalid time.")

def save_reminder(message, event_type, event_time_str):
    try:
        mins = int(message.text.strip())
        user = get_user(message.from_user.id)
        if not user: return
        tz, _ = user
        user_tz = pytz.timezone(tz)
        now = datetime.now(user_tz)
        hour, minute = map(int, event_time_str.replace("AM", "").replace("PM", "").strip().split(":"))
        if "PM" in event_time_str and hour != 12:
            hour += 12
        if "AM" in event_time_str and hour == 12:
            hour = 0

        today = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if today < now:
            today += timedelta(days=1)
        event_time_utc = today.astimezone(pytz.utc)

        with get_db() as conn:
            with conn.cursor() as cur:
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
                    event_type TEXT,
                    event_time_utc TIMESTAMP,
                    notify_before INT
                );
                CREATE TABLE IF NOT EXISTS subscriptions (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT REFERENCES users(user_id),
                    event_type TEXT,
                    event_time_local TIME,
                    notify_before INT
                );
                """)
                conn.commit()
        schedule_reminder(message.chat.id, event_time_utc, mins, event_type)
        bot.send_message(message.chat.id, f"✅ Reminder set for {event_type} at {event_time_str} ({mins} minutes before)")
    except:
        bot.send_message(message.chat.id, "Failed to set reminder. Try again.")

def set_timezone(user_id, chat_id, timezone):
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                INSERT INTO users (user_id, chat_id, timezone)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE
                SET chat_id = EXCLUDED.chat_id, timezone = EXCLUDED.timezone;
                """, (user_id, chat_id, timezone))
                conn.commit()
        logger.info(f"Timezone set for user {user_id}: {timezone}")
        return True
    except Exception as e:
        logger.error(f"Failed to set timezone for user {user_id}: {str(e)}")
        logger.error(traceback.format_exc())
        return False

@bot.message_handler(func=lambda msg: msg.text == '⚙️ Settings')
def settings_menu(message):
    user = get_user(message.from_user.id)
    if not user: return
    _, fmt = user
    new_fmt = '24hr' if fmt == '12hr' else '12hr'
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(f'🕰 Change Time Format (Now: {fmt})')
    markup.row('🔙 Back')
    bot.send_message(message.chat.id, "Settings:", reply_markup=markup)

# ========================== START HANDLER ======================
@bot.message_handler(commands=['start'])
def start(message):
    try:
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.row('🇲🇲 Set to Myanmar Time')
        bot.send_message(
            message.chat.id,
            f"Hello {message.from_user.first_name}! 👋\nPlease type your timezone (e.g. Asia/Yangon), or choose an option:",
            reply_markup=markup
        )
        bot.register_next_step_handler(message, save_timezone)
    except Exception as e:
        logger.error(f"Error in /start: {str(e)}")
        bot.send_message(message.chat.id, "⚠️ Error in /start command")

# ========================== TIMEZONE SAVE =======================
def save_timezone(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    try:
        if message.text == '🇲🇲 Set to Myanmar Time':
            tz = 'Asia/Yangon'
        else:
            try:
                # Validate timezone
                pytz.timezone(message.text)
                tz = message.text
            except pytz.UnknownTimeZoneError:
                bot.send_message(chat_id, "❌ Invalid timezone. Please try again:")
                return bot.register_next_step_handler(message, save_timezone)

        # Save to database
        if set_timezone(user_id, chat_id, tz):
            bot.send_message(chat_id, f"✅ Timezone set to: {tz}")
            send_main_menu(chat_id)
        else:
            bot.send_message(chat_id, "⚠️ Failed to save timezone to database. Please try /start again.")
    except Exception as e:
        logger.error(f"Error saving timezone: {str(e)}")
        bot.send_message(chat_id, "⚠️ Unexpected error saving timezone. Please try /start again.")

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
    init_db()
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
