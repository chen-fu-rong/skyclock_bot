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
    next_event = get_next_event(event_type).astimezone(user_tz)
    now = datetime.now(user_tz)
    diff = next_event - now
    hrs, mins = divmod(diff.seconds // 60, 60)
    text = f"Next {event_type.capitalize()} event at {format_time(next_event, fmt)} ({hrs}h {mins}m left)"
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    for h in range(24):
        t = get_next_event(event_type).replace(hour=h)
        if event_type == 'grandma' and h % 2 == 0:
            t = t.replace(minute=5)
        elif event_type == 'turtle' and h % 2 == 0:
            t = t.replace(minute=20)
        elif event_type == 'geyser' and h % 2 == 1:
            t = t.replace(minute=35)
        else:
            continue
        t_local = t.astimezone(user_tz)
        markup.row(t_local.strftime('%H:%M'))
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
        today = datetime.now(user_tz).replace(hour=int(event_time_str.split(':')[0]),
                                              minute=int(event_time_str.split(':')[1]),
                                              second=0, microsecond=0)
        event_time_utc = today.astimezone(pytz.utc)
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO reminders (user_id, event_type, event_time_utc, notify_before)
                    VALUES (%s, %s, %s, %s)
                """, (message.from_user.id, event_type, event_time_utc, mins))
                conn.commit()
        schedule_reminder(message.chat.id, event_time_utc, mins, event_type)
        bot.send_message(message.chat.id, f"✅ Reminder set for {event_type} at {event_time_str} ({mins} minutes before)")
    except:
        bot.send_message(message.chat.id, "Failed to set reminder. Try again.")

def schedule_reminder(chat_id, event_time_utc, mins, event_type):
    notify_time = event_time_utc - timedelta(minutes=mins)
    scheduler.add_job(
        lambda: bot.send_message(chat_id, f"⏰ Reminder: {event_type.capitalize()} event is starting soon!"),
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
    bot.send_message(message.chat.id, "Settings:", reply_markup=markup)

@bot.message_handler(func=lambda msg: 'Change Time Format' in msg.text)
def toggle_time_format(message):
    user = get_user(message.from_user.id)
    if not user: return
    _, fmt = user
    new_fmt = '24hr' if fmt == '12hr' else '12hr'
    set_time_format(message.from_user.id, new_fmt)
    bot.send_message(message.chat.id, f"✅ Time format changed to {new_fmt}")

@bot.message_handler(func=lambda msg: msg.text == '💎 Shards')
def shards_placeholder(message):
    bot.send_message(message.chat.id, "💎 Shards feature coming soon! 🚧")

@bot.message_handler(func=lambda msg: msg.text == '🔙 Back')
def go_back(message):
    send_main_menu(message.chat.id)

# ========================== WEBHOOK ============================
@app.route('/webhook', methods=['POST'])
def webhook():
    bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return 'OK', 200

@app.route('/')
def index():
    return 'Sky Clock Bot is running.'

if __name__ == '__main__':
    init_db()
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
