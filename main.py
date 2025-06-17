import os
import telebot
from telebot import types
import psycopg2
from datetime import datetime, timedelta
import pytz
import time

# Initialize bot
BOT_TOKEN = os.environ.get('BOT_TOKEN')
bot = telebot.TeleBot(BOT_TOKEN)

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

# Myanmar time is UTC+6:30
MYANMAR_OFFSET = timedelta(hours=6, minutes=30)

# Event Calculations (UTC-based)
def next_reset_utc():
    now = datetime.utcnow()
    next_reset = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    return next_reset

def next_grandma_utc():
    now = datetime.utcnow()
    base_hour = now.hour - (now.hour % 2)  # Previous even hour
    candidates = [
        now.replace(hour=base_hour, minute=35, second=0, microsecond=0),
        now.replace(hour=base_hour, minute=35, second=0, microsecond=0) + timedelta(hours=2)
    ]
    return min(t for t in candidates if t > now)

def next_geyser_utc():
    now = datetime.utcnow()
    base_hour = (now.hour + 1) % 24  # Next odd hour
    if base_hour % 2 == 0:
        base_hour = (base_hour + 1) % 24
    candidates = [
        now.replace(hour=base_hour, minute=5, second=0, microsecond=0),
        now.replace(hour=(base_hour + 2) % 24, minute=5, second=0, microsecond=0)
    ]
    # Handle day wrap
    for t in candidates:
        if t < now:
            t += timedelta(days=1)
    return min(t for t in candidates if t > now)

def next_turtle_utc():
    now = datetime.utcnow()
    base_hour = now.hour - (now.hour % 2)  # Previous even hour
    candidates = [
        now.replace(hour=base_hour, minute=50, second=0, microsecond=0),
        now.replace(hour=base_hour, minute=50, second=0, microsecond=0) + timedelta(hours=2)
    ]
    return min(t for t in candidates if t > now)

# Timezone Conversion
def to_user_time(utc_time, user_id):
    user_tz = get_user_timezone(user_id)
    utc_dt = pytz.utc.localize(utc_time)
    return utc_dt.astimezone(pytz.timezone(user_tz))

# Formatting Functions
def format_time(dt):
    return dt.strftime("%Y-%m-%d %H:%M")

def format_timedelta(td):
    hours, remainder = divmod(td.seconds, 3600)
    minutes = remainder // 60
    return f"{hours}h {minutes}m"

# Bot Commands
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    help_text = """
🕰️ *Sky Clock Bot* 🕰️
Track Sky: Children of the Light events!

*/wax* - Show next wax events
*/events* - All upcoming events
*/settimezone <zone>* - Set your timezone (e\.g\. /settimezone Asia/Tokyo)
*/timezone* - Show current timezone
*/reset* - Next daily reset time

*Timezones must be valid* \(e\.g\. America/New\_York, Europe/London\)\. 
See full list: [Timezones](https://gist.github.com/heyalexej/8bf688fd67d7199be4a1682b3eec7568)
    """
    bot.reply_to(message, help_text, parse_mode='Markdown', disable_web_page_preview=True)

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
        f"🕛 *Next Daily Reset*\n"
        f"• Your time: `{format_time(user_time)}`\n"
        f"• UTC: `{format_time(reset_utc)}`\n"
        f"• Time left: `{format_timedelta(time_left)}`"
    )
    bot.reply_to(message, response, parse_mode='Markdown')

@bot.message_handler(commands=['wax'])
def send_wax(message):
    # Get event times in UTC
    grandma_utc = next_grandma_utc()
    geyser_utc = next_geyser_utc()
    turtle_utc = next_turtle_utc()
    
    # Convert to user's timezone
    user_id = message.from_user.id
    grandma_user = to_user_time(grandma_utc, user_id)
    geyser_user = to_user_time(geyser_utc, user_id)
    turtle_user = to_user_time(turtle_utc, user_id)
    
    # Calculate time until events
    now = datetime.utcnow()
    grandma_delta = grandma_utc - now
    geyser_delta = geyser_utc - now
    turtle_delta = turtle_utc - now
    
    # Format response
    response = (
        "🕯️ *Next Wax Events*\n\n"
        f"🧓 *Grandma*\n"
        f"• Your time: `{format_time(grandma_user)}`\n"
        f"• UTC: `{format_time(grandma_utc)}`\n"
        f"• In: `{format_timedelta(grandma_delta)}`\n\n"
        f"⛲ *Geyser*\n"
        f"• Your time: `{format_time(geyser_user)}`\n"
        f"• UTC: `{format_time(geyser_utc)}`\n"
        f"• In: `{format_timedelta(geyser_delta)}`\n\n"
        f"🐢 *Turtle*\n"
        f"• Your time: `{format_time(turtle_user)}`\n"
        f"• UTC: `{format_time(turtle_utc)}`\n"
        f"• In: `{format_timedelta(turtle_delta)}`"
    )
    bot.reply_to(message, response, parse_mode='Markdown')

@bot.message_handler(commands=['events'])
def send_events(message):
    # Get all events
    reset_utc = next_reset_utc()
    grandma_utc = next_grandma_utc()
    geyser_utc = next_geyser_utc()
    turtle_utc = next_turtle_utc()
    
    # Convert to user's timezone
    user_id = message.from_user.id
    user_tz = get_user_timezone(user_id)
    reset_user = to_user_time(reset_utc, user_id)
    grandma_user = to_user_time(grandma_utc, user_id)
    geyser_user = to_user_time(geyser_utc, user_id)
    turtle_user = to_user_time(turtle_utc, user_id)
    
    # Format response
    response = (
        f"⏰ *Event Times \(in your time: {user_tz}\)*\n\n"
        f"🕛 Daily Reset: `{format_time(reset_user)}`\n"
        f"🧓 Grandma: `{format_time(grandma_user)}`\n"
        f"⛲ Geyser: `{format_time(geyser_user)}`\n"
        f"🐢 Turtle: `{format_time(turtle_user)}`"
    )
    bot.reply_to(message, response, parse_mode='Markdown')

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
    print("Bot running...")
    while True:
        try:
            bot.polling(none_stop=True)
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(15)