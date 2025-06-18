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
WEBHOOK_URL = os.getenv("WEBHOOK_URL") or "https://yourapp.onrender.com/webhook"
DB_URL = os.getenv("DATABASE_URL") or "postgresql://user:pass@host:port/db"
SKY_TZ = pytz.timezone("America/Los_Angeles")

bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)
scheduler = BackgroundScheduler()
scheduler.start()

# ========================== STATE ==============================
user_sessions = {}  # Store temporary reminder data per user

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
# (unchanged code omitted here for brevity — assume main handlers stay the same)

def ask_reminder_time(message, event_type):
    if message.text == '🔙 Back':
        return send_main_menu(message.chat.id)
    try:
        selected_time = message.text.strip()
        user_sessions[message.from_user.id] = {'event_type': event_type, 'event_time': selected_time}
        bot.send_message(message.chat.id, f"⏰ How many minutes before {selected_time} do you want to be reminded? (e.g. 5, 10)")
        bot.register_next_step_handler(message, ask_reminder_type)
    except:
        bot.send_message(message.chat.id, "❌ Invalid time.")

def ask_reminder_type(message):
    try:
        mins = int(message.text.strip())
        user_sessions[message.from_user.id]['notify_before'] = mins
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.row('🔁 Daily', '🕐 One-Time')
        bot.send_message(message.chat.id, "How often should I remind you?", reply_markup=markup)
        bot.register_next_step_handler(message, handle_reminder_type)
    except:
        bot.send_message(message.chat.id, "❌ Please enter a number.")

def handle_reminder_type(message):
    choice = message.text
    session = user_sessions.get(message.from_user.id)
    if not session:
        return bot.send_message(message.chat.id, "❌ Session expired. Please try again.")

    if choice == '🔁 Daily':
        save_daily_subscription(message.from_user.id, session)
        bot.send_message(message.chat.id, f"✅ Daily reminder set for {session['event_type']} at {session['event_time']} ({session['notify_before']} minutes before)")
    elif choice == '🕐 One-Time':
        save_one_time_reminder(message, session)
    else:
        bot.send_message(message.chat.id, "❌ Please choose One-Time or Daily.")

def save_one_time_reminder(message, session):
    try:
        user = get_user(message.from_user.id)
        if not user: return
        tz, _ = user
        user_tz = pytz.timezone(tz)
        now = datetime.now(user_tz)
        hour, minute = map(int, session['event_time'].replace("AM", "").replace("PM", "").strip().split(":"))
        if "PM" in session['event_time'] and hour != 12:
            hour += 12
        if "AM" in session['event_time'] and hour == 12:
            hour = 0
        today = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if today < now:
            today += timedelta(days=1)
        event_time_utc = today.astimezone(pytz.utc)

        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO reminders (user_id, event_type, event_time_utc, notify_before)
                    VALUES (%s, %s, %s, %s)
                """, (message.from_user.id, session['event_type'], event_time_utc, session['notify_before']))
                conn.commit()
        schedule_reminder(message.chat.id, event_time_utc, session['notify_before'], session['event_type'])
        bot.send_message(message.chat.id, f"✅ One-time reminder set for {session['event_type']} at {session['event_time']} ({session['notify_before']} minutes before)")
    except:
        bot.send_message(message.chat.id, "❌ Failed to set reminder.")

def save_daily_subscription(user_id, session):
    try:
        hour, minute = map(int, session['event_time'].replace("AM", "").replace("PM", "").strip().split(":"))
        if "PM" in session['event_time'] and hour != 12:
            hour += 12
        if "AM" in session['event_time'] and hour == 12:
            hour = 0

        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO subscriptions (user_id, event_type, event_time_local, notify_before)
                    VALUES (%s, %s, %s, %s)
                """, (user_id, session['event_type'], f"{hour:02}:{minute:02}", session['notify_before']))
                conn.commit()
    except:
        print("Failed to save subscription")

# ======================== DAILY JOBS ============================
def schedule_all_daily_reminders():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id, event_type, event_time_local, notify_before FROM subscriptions")
            for user_id, event_type, time_obj, before in cur.fetchall():
                user = get_user(user_id)
                if not user: continue
                tz, _ = user
                user_tz = pytz.timezone(tz)
                now = datetime.now(user_tz)
                target_time = now.replace(hour=time_obj.hour, minute=time_obj.minute, second=0, microsecond=0)
                reminder_time = target_time - timedelta(minutes=before)
                if reminder_time < now:
                    reminder_time += timedelta(days=1)
                scheduler.add_job(
                    lambda uid=user_id, et=event_type: bot.send_message(uid, f"⏰ Daily reminder: {et.capitalize()} event is starting soon!"),
                    trigger='date',
                    run_date=reminder_time
                )

# Call this after initializing DB
if __name__ == '__main__':
    init_db()
    schedule_all_daily_reminders()
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
