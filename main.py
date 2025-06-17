import os
import telebot
import psycopg2
from flask import Flask, request, abort
from datetime import datetime, timedelta
import pytz

# ======================= CONFIG =======================
BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
DEFAULT_TZ = "+0630"
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{os.getenv('RENDER_EXTERNAL_URL', 'https://skyclock-bot.onrender.com')}{WEBHOOK_PATH}"

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# ======================= DATABASE =======================
def get_connection():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def create_users_table():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id BIGINT PRIMARY KEY,
                    timezone TEXT
                )
            """)
            conn.commit()
create_users_table()

# ======================= HELPERS =======================
def get_user_timezone(user_id):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT timezone FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
            return row[0] if row else DEFAULT_TZ

def set_user_timezone(user_id, tz):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO users (id, timezone)
                VALUES (%s, %s)
                ON CONFLICT (id) DO UPDATE SET timezone = EXCLUDED.timezone
            """, (user_id, tz))
            conn.commit()

def get_next_event_time(event_name, now_utc):
    hour = now_utc.hour
    minute = now_utc.minute
    current = now_utc.replace(second=0, microsecond=0)

    if event_name == "Geyser":
        # Odd hours + 35 minutes
        next_hour = hour + 1 if hour % 2 == 0 else hour
        next_time = current.replace(hour=next_hour % 24, minute=35)
        if next_time <= now_utc:
            next_time += timedelta(hours=2)

    elif event_name == "Grandma":
        # Even hours + 5 minutes
        next_hour = hour if hour % 2 == 0 else hour + 1
        next_time = current.replace(hour=next_hour % 24, minute=5)
        if next_time <= now_utc:
            next_time += timedelta(hours=2)

    elif event_name == "Turtle":
        # Even hours + 20 minutes
        next_hour = hour if hour % 2 == 0 else hour + 1
        next_time = current.replace(hour=next_hour % 24, minute=20)
        if next_time <= now_utc:
            next_time += timedelta(hours=2)

    else:
        return None

    return next_time

# ======================= COMMANDS =======================
@bot.message_handler(commands=['start', 'tz'])
def ask_timezone(message):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("+0630", "+0700", "+0800", "+0900")
    bot.send_message(message.chat.id, "🕒 Please choose your timezone offset (e.g., +0630)", reply_markup=markup)

@bot.message_handler(func=lambda msg: msg.text and msg.text.startswith('+') and len(msg.text) in [5, 6])
def save_timezone(message):
    tz = message.text
    set_user_timezone(message.chat.id, tz)
    bot.send_message(message.chat.id, f"✅ Timezone set to {tz}", reply_markup=telebot.types.ReplyKeyboardRemove())

@bot.message_handler(commands=['wax'])
def wax_menu(message):
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(
        telebot.types.InlineKeyboardButton("🧓 Grandma", callback_data='wax_grandma'),
        telebot.types.InlineKeyboardButton("🌋 Geyser", callback_data='wax_geyser'),
        telebot.types.InlineKeyboardButton("🐢 Turtle", callback_data='wax_turtle')
    )
    bot.send_message(message.chat.id, "Choose a wax event:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('wax_'))
def handle_wax_event(call):
    event = call.data.split('_')[1].capitalize()
    user_id = call.from_user.id
    tz_offset = get_user_timezone(user_id)

    now_utc = datetime.utcnow()
    event_time_utc = get_next_event_time(event, now_utc)

    if event_time_utc:
        hours, minutes = int(tz_offset[1:3]), int(tz_offset[3:])
        delta = timedelta(hours=hours, minutes=minutes)
        if tz_offset.startswith('-'):
            delta *= -1
        local_event_time = event_time_utc + delta

        time_remaining = local_event_time - (now_utc + delta)
        msg = (f"Next {event} {get_emoji(event)}\n"
               f"🕓 Time: {local_event_time.strftime('%H:%M')} (UTC{tz_offset})\n"
               f"⏳ Starts in: {str(time_remaining).split('.')[0]}")

        markup = telebot.types.InlineKeyboardMarkup()
        markup.add(telebot.types.InlineKeyboardButton("🔔 Notify Me", callback_data=f"notify_{event.lower()}"))
        markup.add(telebot.types.InlineKeyboardButton("🔙 Back", callback_data="wax_back"))
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=msg, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('notify_'))
def handle_notify(call):
    bot.answer_callback_query(call.id, "🔔 Notification setup coming soon!")

@bot.callback_query_handler(func=lambda call: call.data == "wax_back")
def handle_back(call):
    wax_menu(call.message)

def get_emoji(event):
    return {"Grandma": "🧓", "Geyser": "🌋", "Turtle": "🐢"}.get(event, "")

# ======================= FLASK WEBHOOK =======================
@app.route('/')
def home():
    return 'Bot running...'

@app.route(WEBHOOK_PATH, methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    else:
        abort(403)

# ======================= RUN APP =======================
if __name__ == '__main__':
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    print(f"Webhook set to: {WEBHOOK_URL}")
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
