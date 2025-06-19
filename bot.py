# bot.py — FIXED START HANDLER
import os
import pytz
import logging
import traceback
from flask import Flask, request
import telebot
import psycopg2
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta

API_TOKEN = os.getenv("BOT_TOKEN") or "YOUR_BOT_TOKEN"
WEBHOOK_URL = os.getenv("WEBHOOK_URL") or "https://skyclock-bot.onrender.com/webhook"
DB_URL = os.getenv("DATABASE_URL") or "postgresql://user:pass@host:port/db"

bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)
scheduler = BackgroundScheduler()
scheduler.start()

user_sessions = {}

# ========================== DATABASE ===========================
def get_db():
    return psycopg2.connect(DB_URL, sslmode='require')

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
            CREATE TABLE IF NOT EXISTS subscriptions (
                id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(user_id),
                event_type TEXT,
                event_time_local TIME,
                notify_before INT
            );
            """)
            conn.commit()

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
        bot.send_message(message.chat.id, "⚠️ Error in /start")
        print(traceback.format_exc())

def set_timezone(user_id, chat_id, tz):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO users (user_id, chat_id, timezone)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET timezone = EXCLUDED.timezone;
            """, (user_id, chat_id, tz))
            conn.commit()

# ========================== TIMEZONE SAVE =======================
def save_timezone(message):
    try:
        if message.text == '🇲🇲 Set to Myanmar Time':
            tz = 'Asia/Yangon'
        else:
            try:
                pytz.timezone(message.text)
                tz = message.text
            except:
                bot.send_message(message.chat.id, "❌ Invalid timezone. Please try again:")
                return bot.register_next_step_handler(message, save_timezone)

        set_timezone(message.from_user.id, message.chat.id, tz)
        bot.send_message(message.chat.id, f"✅ Timezone set to: {tz}")
        send_main_menu(message.chat.id)
    except Exception as e:
        bot.send_message(message.chat.id, "⚠️ Failed to save timezone")
        print(traceback.format_exc())

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

# ========================== MAIN ===============================
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    logging.info("Starting bot...")
    init_db()
    logging.info("Database initialization complete")
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
