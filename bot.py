# bot.py
import os
import pytz
import logging
from flask import Flask, request
import telebot
import psycopg2
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta

# ========================== CONFIG =============================
API_TOKEN = os.getenv("BOT_TOKEN") or "YOUR_BOT_TOKEN"
WEBHOOK_URL = os.getenv("WEBHOOK_URL") or "https://skyclock-bot.onrender.com/webhook"
DB_URL = os.getenv("DATABASE_URL") or "postgresql://user:pass@host:port/db"

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

# ======================= WAX TIME CALCULATION ==================
def get_wax_event_times(event_type, tz):
    user_tz = pytz.timezone(tz)
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

    return event_times, now_user

# ======================== DAILY JOBS ============================
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
    logging.basicConfig(level=logging.INFO)
    logging.info("Starting bot...")
    init_db()
    logging.info("Database initialization complete")
    schedule_all_daily_reminders()
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
