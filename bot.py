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
    try:
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
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {str(e)}")
        logger.error(traceback.format_exc())

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

def send_main_menu(chat_id):
    try:
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.row('🕒 Set Reminder')
        markup.row('⏰ My Reminders', '⚙️ Settings')
        bot.send_message(chat_id, "Choose an option:", reply_markup=markup)
    except Exception as e:
        logger.error(f"Failed to send main menu to {chat_id}: {str(e)}")

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
    logger.info("Starting bot...")
    try:
        init_db()
        logger.info("Database initialization complete")
        bot.remove_webhook()
        bot.set_webhook(url=WEBHOOK_URL)
        logger.info(f"Webhook set to: {WEBHOOK_URL}")
        app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
    except Exception as e:
        logger.error(f"Fatal error during startup: {str(e)}")
        logger.error(traceback.format_exc())