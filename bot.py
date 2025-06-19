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

# ======================= TELEGRAM UI ===========================
@bot.message_handler(func=lambda m: m.text and m.text.count(':') == 1)
def handle_event_time_selection(message):
    user_id = message.from_user.id
    if user_id not in user_sessions or 'event_type' not in user_sessions[user_id]:
        return
    selected_time = message.text.strip()
    if selected_time == '🔙 Back':
        return send_main_menu(message.chat.id)
    user_sessions[user_id]['event_time'] = selected_time
    bot.send_message(message.chat.id, f"⏰ How many minutes before {selected_time} do you want to be reminded? (e.g. 5, 10)")
    bot.register_next_step_handler(message, ask_reminder_type)
@bot.message_handler(commands=['start'])
def start(message):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.row('🇲🇲 Set to Myanmar Time')
    bot.send_message(message.chat.id, f"Hello {message.from_user.first_name}! 👋\nPlease type your timezone (e.g. Asia/Yangon), or choose an option:", reply_markup=markup)
    bot.register_next_step_handler(message, save_timezone)

def save_timezone(message):
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
    user_sessions[message.from_user.id] = {}
    mapping = {'🧓 Grandma': 'grandma', '🐢 Turtle': 'turtle', '🌋 Geyser': 'geyser'}
    event_type = mapping[message.text]
    user = get_user(message.from_user.id)
    if not user: return
    tz, fmt = user
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

    next_event = next((et for et in event_times if et > now_user), event_times[0] + timedelta(days=1))
    diff = next_event - now_user
    hrs, mins = divmod(diff.seconds // 60, 60)
    text = f"Next {event_type.capitalize()} event at {format_time(next_event, fmt)} ({hrs}h {mins}m left)"

    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    for et in event_times:
        markup.row(format_time(et, fmt))
    markup.row('🔙 Back')

    bot.send_message(message.chat.id, f"📅 {text}\n\n📌 Choose a time below to set a reminder:", reply_markup=markup)
    bot.register_next_step_handler(message, ask_reminder_time, event_type)

# ... other handler and reminder functions remain unchanged (see previous steps)

# ======================== DAILY JOBS ============================
def schedule_all_daily_reminders():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id, event_type, event_time_local, notify_before FROM subscriptions")
            for user_id, event_type, time_obj, before in cur.fetchall():
                user = get_user(user_id)
                if not user:
                    continue
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

# ========================== MAIN ===============================
if __name__ == '__main__':
    init_db()
    schedule_all_daily_reminders()
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
