import os
import telebot
from telebot import types
import psycopg2
from datetime import datetime, timedelta
import pytz
import time
from flask import Flask

# Initialize bot
BOT_TOKEN = os.environ.get('BOT_TOKEN')
bot = telebot.TeleBot(BOT_TOKEN)

# Create a simple HTTP server for Render
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running", 200

def run_flask_app():
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

# Database connection
DATABASE_URL = os.environ.get('DATABASE_URL')
conn = psycopg2.connect(DATABASE_URL, sslmode='require')
cursor = conn.cursor()

# Create tables with timezone support
cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    username VARCHAR(255),
    timezone VARCHAR(50) DEFAULT 'UTC'
);
''')
conn.commit()

# Timezone Validation
def is_valid_timezone(timezone_str):
    return timezone_str in pytz.all_timezones

# User Management
def get_user_timezone(user_id):
    cursor.execute("SELECT timezone FROM users WHERE user_id = %s", (user_id,))
    result = cursor.fetchone()
    return result[0] if result else 'UTC'

def set_user_timezone(user_id, timezone_str):
    cursor.execute('''
    INSERT INTO users (user_id, timezone) 
    VALUES (%s, %s)
    ON CONFLICT (user_id) 
    DO UPDATE SET timezone = EXCLUDED.timezone
    ''', (user_id, timezone_str))
    conn.commit()

# Event Calculations (always in UTC)
def next_reset_utc():
    now = datetime.utcnow()
    return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

def next_grandma_utc():
    now = datetime.utcnow()
    base = now.replace(minute=0, second=0, microsecond=0)
    even_hour = base.hour - base.hour % 2
    for offset in range(0, 24, 2):
        candidate = base.replace(hour=(even_hour + offset) % 24, minute=35)
        if candidate > now:
            return candidate
    return base.replace(hour=0, minute=35) + timedelta(days=1)

def next_geyser_utc():
    now = datetime.utcnow()
    next_odd_hour = (now.hour + 1) | 1
    for offset in range(0, 24, 2):
        candidate = now.replace(hour=(next_odd_hour + offset) % 24, minute=5, second=0, microsecond=0)
        if candidate > now:
            return candidate
    return now.replace(hour=1, minute=5) + timedelta(days=1)

def next_turtle_utc():
    now = datetime.utcnow()
    even_hour = now.hour - (now.hour % 2)
    for offset in range(0, 24, 2):
        candidate = now.replace(hour=(even_hour + offset) % 24, minute=50, second=0, microsecond=0)
        if candidate > now:
            return candidate
    return now.replace(hour=0, minute=50) + timedelta(days=1)

# Timezone Conversion
def to_user_time(utc_dt, user_id):
    user_tz = get_user_timezone(user_id)
    localized = pytz.utc.localize(utc_dt)
    return localized.astimezone(pytz.timezone(user_tz))

# Formatting Functions
def format_time(dt):
    return dt.strftime("%Y-%m-%d %H:%M")

def format_timedelta(td):
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    return f"{hours}h {minutes}m"

# Bot Commands
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    help_text = """
🕰️ <b>Sky Clock Bot</b> 🕰️
Track Sky: Children of the Light events!

<b>Commands:</b>
/wax - Show next wax events
/events - All upcoming events
/settimezone <zone> - Set your timezone (e.g. /settimezone Asia/Tokyo)
/timezone - Show current timezone
/reset - Next daily reset time

<b>Timezones</b> must be valid (e.g. America/New_York, Europe/London). 
See full list: <a href=\"https://gist.github.com/heyalexej/8bf688fd67d7199be4a1682b3eec7568\">Timezones</a>
    """
    bot.reply_to(message, help_text, parse_mode='HTML', disable_web_page_preview=True)

@bot.message_handler(commands=['settimezone'])
def set_timezone(message):
    try:
        timezone_str = message.text.split()[1]
        if not is_valid_timezone(timezone_str):
            bot.reply_to(message, "❌ Invalid timezone! Use format like 'Asia/Tokyo' or 'America/New_York'")
            return
        set_user_timezone(message.from_user.id, timezone_str)
        bot.reply_to(message, f"✅ Timezone set to {timezone_str}")
    except IndexError:
        bot.reply_to(message, "❌ Please specify a timezone. Example: /settimezone Asia/Tokyo")

@bot.message_handler(commands=['timezone'])
def show_timezone(message):
    user_tz = get_user_timezone(message.from_user.id)
    bot.reply_to(message, f"⏱️ Your current timezone: {user_tz}")

@bot.message_handler(commands=['reset'])
def send_reset(message):
    reset_utc = next_reset_utc()
    user_time = to_user_time(reset_utc, message.from_user.id)
    time_left = reset_utc - datetime.utcnow()
    response = (
        f"🕛 <b>Next Daily Reset</b>\n"
        f"• Your time: <code>{format_time(user_time)}</code>\n"
        f"• UTC: <code>{format_time(reset_utc)}</code>\n"
        f"• Time left: <code>{format_timedelta(time_left)}</code>"
    )
    bot.reply_to(message, response, parse_mode='HTML')

@bot.message_handler(commands=['wax'])
def send_wax(message):
    user_id = message.from_user.id
    now = datetime.utcnow()

    events = {
        "Grandma": next_grandma_utc(),
        "Geyser": next_geyser_utc(),
        "Turtle": next_turtle_utc()
    }

    lines = ["🕯️ <b>Next Wax Events</b>\n"]
    for name, utc_time in events.items():
        local_time = to_user_time(utc_time, user_id)
        time_left = utc_time - now
        emoji = "🧓" if name == "Grandma" else "⛲" if name == "Geyser" else "🐢"
        lines.append(f"{emoji} <b>{name}</b>")
        lines.append(f"• Your time: <code>{format_time(local_time)}</code>")
        lines.append(f"• UTC: <code>{format_time(utc_time)}</code>")
        lines.append(f"• In: <code>{format_timedelta(time_left)}</code>\n")

    bot.reply_to(message, "\n".join(lines), parse_mode='HTML')

@bot.message_handler(commands=['events'])
def send_events(message):
    user_id = message.from_user.id
    user_tz = get_user_timezone(user_id)

    events = {
        "Daily Reset": next_reset_utc(),
        "Grandma": next_grandma_utc(),
        "Geyser": next_geyser_utc(),
        "Turtle": next_turtle_utc()
    }

    lines = [f"⏰ <b>Event Times (Your timezone: {user_tz})</b>\n"]
    for name, utc_time in events.items():
        local_time = to_user_time(utc_time, user_id)
        emoji = "🕛" if name == "Daily Reset" else "🧓" if name == "Grandma" else "⛲" if name == "Geyser" else "🐢"
        lines.append(f"{emoji} {name}: <code>{format_time(local_time)}</code>")

    bot.reply_to(message, "\n".join(lines), parse_mode='HTML')

# Inline Buttons
@bot.message_handler(func=lambda message: True)
def handle_buttons(message):
    if message.text == "⏰ Wax Events":
        send_wax(message)
    elif message.text == "📅 All Events":
        send_events(message)
    elif message.text == "🕛 Daily Reset":
        send_reset(message)
    else:
        bot.reply_to(message, "I don't understand that command. Try /help")

# Main loop
if __name__ == '__main__':
    bot.remove_webhook()
    from threading import Thread
    Thread(target=run_flask_app).start()
    print("Bot running...")
    while True:
        try:
            bot.polling(none_stop=True)
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(15)
