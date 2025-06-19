# bot.py — Enhanced UI with Reminder Frequency Options
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

# Sky timezone
SKY_TZ = pytz.timezone('UTC')  # Sky clock uses UTC

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
                notify_before INT,
                is_daily BOOLEAN DEFAULT FALSE
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
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO users (user_id, chat_id, timezone) 
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_id) DO UPDATE 
                    SET chat_id = EXCLUDED.chat_id, timezone = EXCLUDED.timezone;
                """, (user_id, chat_id, tz))
                conn.commit()
        logger.info(f"Timezone set for user {user_id}: {tz}")
        return True
    except Exception as e:
        logger.error(f"Failed to set timezone for user {user_id}: {str(e)}")
        logger.error(traceback.format_exc())
        return False

def set_time_format(user_id, fmt):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET time_format = %s WHERE user_id = %s", (fmt, user_id))
            conn.commit()

# ===================== NAVIGATION HELPERS ======================
def send_main_menu(chat_id):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('🕒 Sky Clock', '🕯 Wax Events')
    markup.row('💎 Shards', '⚙️ Settings')
    bot.send_message(chat_id, "Main Menu:", reply_markup=markup)

def send_wax_menu(chat_id):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('🧓 Grandma', '🐢 Turtle', '🌋 Geyser')
    markup.row('🔙 Main Menu')
    bot.send_message(chat_id, "Wax Events:", reply_markup=markup)

def send_settings_menu(chat_id, current_format):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(f'🕰 Change Time Format (Now: {current_format})')
    markup.row('🔙 Main Menu')
    bot.send_message(chat_id, "Settings:", reply_markup=markup)

# ======================= GLOBAL HANDLERS =======================
@bot.message_handler(func=lambda msg: msg.text == '🔙 Main Menu')
def handle_back_to_main(message):
    send_main_menu(message.chat.id)

# ======================= START FLOW ============================
@bot.message_handler(commands=['start'])
def start(message):
    try:
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.row('🇲🇲 Set to Myanmar Time')
        bot.send_message(
            message.chat.id,
            f"Hello {message.from_user.first_name}! 👋\nWelcome to Sky Clock Bot!\n\n"
            "Please type your timezone (e.g. Asia/Yangon), or choose an option:",
            reply_markup=markup
        )
        bot.register_next_step_handler(message, save_timezone)
    except Exception as e:
        logger.error(f"Error in /start: {str(e)}")
        bot.send_message(message.chat.id, "⚠️ Error in /start command")

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

# ===================== MAIN MENU HANDLERS ======================
@bot.message_handler(func=lambda msg: msg.text == '🕒 Sky Clock')
def sky_clock(message):
    user = get_user(message.from_user.id)
    if not user: 
        bot.send_message(message.chat.id, "Please set your timezone first with /start")
        return
        
    tz, fmt = user
    user_tz = pytz.timezone(tz)
    now = datetime.now()
    local = now.astimezone(user_tz)
    sky = now.astimezone(SKY_TZ)
    
    # Calculate time difference
    time_diff = local - sky
    hours, remainder = divmod(abs(time_diff.seconds), 3600)
    minutes = remainder // 60
    direction = "ahead" if time_diff.total_seconds() > 0 else "behind"
    
    text = (
        f"🌥 Sky Time: {format_time(sky, fmt)}\n"
        f"🌍 Your Time: {format_time(local, fmt)}\n"
        f"⏱ You are {hours}h {minutes}m {direction} Sky Time"
    )
    bot.send_message(message.chat.id, text)

@bot.message_handler(func=lambda msg: msg.text == '🕯 Wax Events')
def wax_menu(message):
    send_wax_menu(message.chat.id)

@bot.message_handler(func=lambda msg: msg.text == '⚙️ Settings')
def settings_menu(message):
    user = get_user(message.from_user.id)
    if not user: 
        bot.send_message(message.chat.id, "Please set your timezone first with /start")
        return
        
    _, fmt = user
    send_settings_menu(message.chat.id, fmt)

@bot.message_handler(func=lambda msg: msg.text == '💎 Shards')
def shards_menu(message):
    user = get_user(message.from_user.id)
    if not user: 
        bot.send_message(message.chat.id, "Please set your timezone first with /start")
        return
        
    tz, fmt = user
    user_tz = pytz.timezone(tz)
    now = datetime.now(user_tz)
    
    # Shard event times (every 2 hours at :05)
    event_times = []
    for hour in range(0, 24, 2):
        event_times.append(now.replace(hour=hour, minute=5, second=0, microsecond=0))
    
    # Find next shard event
    next_event = next((et for et in event_times if et > now), event_times[0] + timedelta(days=1))
    diff = next_event - now
    hrs, mins = divmod(diff.seconds // 60, 60)
    
    text = (
        "💎 Shard Events occur every 2 hours at :05\n\n"
        f"Next Shard Event: {format_time(next_event, fmt)}\n"
        f"⏳ Time Remaining: {hrs}h {mins}m"
    )
    
    bot.send_message(message.chat.id, text)

# ====================== WAX EVENT HANDLERS =====================
@bot.message_handler(func=lambda msg: msg.text in ['🧓 Grandma', '🐢 Turtle', '🌋 Geyser'])
def handle_event(message):
    mapping = {
        '🧓 Grandma': ('Grandma', 'every 2 hours at :05', 'even'),
        '🐢 Turtle': ('Turtle', 'every 2 hours at :20', 'even'),
        '🌋 Geyser': ('Geyser', 'every 2 hours at :35', 'odd')
    }
    
    event_name, event_schedule, hour_type = mapping[message.text]
    user = get_user(message.from_user.id)
    if not user: 
        bot.send_message(message.chat.id, "Please set your timezone first with /start")
        return
        
    tz, fmt = user
    user_tz = pytz.timezone(tz)

    # Generate local event times based on user's timezone
    now_user = datetime.now(user_tz)
    today_user = now_user.replace(hour=0, minute=0, second=0, microsecond=0)

    event_times = []
    for hour in range(24):
        if hour_type == 'even' and hour % 2 == 0:
            event_times.append(today_user.replace(hour=hour, minute=int(event_schedule.split(':')[1])))
        elif hour_type == 'odd' and hour % 2 == 1:
            event_times.append(today_user.replace(hour=hour, minute=int(event_schedule.split(':')[1])))

    # Find next event
    next_event = next((et for et in event_times if et > now_user), event_times[0] + timedelta(days=1))
    diff = next_event - now_user
    hrs, mins = divmod(diff.seconds // 60, 60)
    
    # Create event description
    description = {
        'Grandma': "🕯 Grandma offers wax at Home every 2 hours",
        'Turtle': "🐢 Dark Turtle appears at Sanctuary Islands every 2 hours",
        'Geyser': "🌋 Geyser erupts at Vault every 2 hours"
    }[event_name]
    
    text = (
        f"{description}\n\n"
        f"⏰ Next Event: {format_time(next_event, fmt)}\n"
        f"⏳ Time Remaining: {hrs}h {mins}m\n\n"
        "Choose a time to set a reminder:"
    )

    # Send buttons for all event times
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    # Group times in pairs for better layout
    for i in range(0, len(event_times), 2):
        row = [format_time(event_times[i], fmt)]
        if i+1 < len(event_times):
            row.append(format_time(event_times[i+1], fmt))
        markup.row(*row)
    markup.row('🔙 Wax Events')
    
    bot.send_message(message.chat.id, text, reply_markup=markup)
    bot.register_next_step_handler(message, ask_reminder_time, event_name)

def ask_reminder_time(message, event_type):
    # Handle back navigation
    if message.text.strip() == '🔙 Wax Events':
        send_wax_menu(message.chat.id)
        return
        
    try:
        selected_time = message.text.strip()
        bot.send_message(
            message.chat.id, 
            f"⏰ You selected: {selected_time}\n\n"
            f"How many minutes before should I remind you?\n"
            "(e.g., 5 for 5 minutes before)"
        )
        bot.register_next_step_handler(message, ask_reminder_frequency, event_type, selected_time)
    except:
        bot.send_message(message.chat.id, "Invalid time. Please try again.")

def ask_reminder_frequency(message, event_type, event_time_str):
    # Handle back navigation
    if message.text.strip() == '🔙 Wax Events':
        send_wax_menu(message.chat.id)
        return
        
    try:
        mins = int(message.text.strip())
        if mins < 1 or mins > 60:
            bot.send_message(message.chat.id, "Please enter a number between 1 and 60")
            return bot.register_next_step_handler(message, ask_reminder_frequency, event_type, event_time_str)
            
        # Save minutes temporarily in message object
        message.mins_before = mins
        
        # Ask for reminder frequency
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.row('⏰ One Time Reminder')
        markup.row('🔄 Daily Reminder')
        markup.row('🔙 Wax Events')
        
        bot.send_message(
            message.chat.id,
            f"Reminder will be {mins} minutes before event\n\n"
            "Choose reminder frequency:",
            reply_markup=markup
        )
        bot.register_next_step_handler(message, save_reminder, event_type, event_time_str)
    except ValueError:
        bot.send_message(message.chat.id, "Please enter a valid number (e.g., 5, 10)")
        bot.register_next_step_handler(message, ask_reminder_frequency, event_type, event_time_str)
    except Exception as e:
        logger.error(f"Error in reminder setup: {str(e)}")
        bot.send_message(message.chat.id, "Failed to set reminder. Please try again.")

def save_reminder(message, event_type, event_time_str):
    # Handle back navigation
    if message.text.strip() == '🔙 Wax Events':
        send_wax_menu(message.chat.id)
        return
        
    try:
        # Get frequency choice
        if message.text == '⏰ One Time Reminder':
            is_daily = False
        elif message.text == '🔄 Daily Reminder':
            is_daily = True
        else:
            bot.send_message(message.chat.id, "Please select a valid option")
            return
            
        mins = getattr(message, 'mins_before', 5)  # Default to 5 if not set
        user = get_user(message.from_user.id)
        if not user: 
            bot.send_message(message.chat.id, "Please set your timezone first with /start")
            return
            
        tz, fmt = user
        user_tz = pytz.timezone(tz)
        now = datetime.now(user_tz)
        
        # Parse time string
        time_str = event_time_str.replace("AM", "").replace("PM", "").strip()
        hour, minute = map(int, time_str.split(':'))
        
        # Handle 12-hour format
        if "PM" in event_time_str and hour != 12:
            hour += 12
        if "AM" in event_time_str and hour == 12:
            hour = 0

        # Create datetime object in user's timezone
        today = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if today < now:
            today += timedelta(days=1)
            
        event_time_utc = today.astimezone(pytz.utc)

        # Save reminder to database
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                INSERT INTO reminders (user_id, event_type, event_time_utc, notify_before, is_daily)
                VALUES (%s, %s, %s, %s, %s)
                """, (message.from_user.id, event_type, event_time_utc, mins, is_daily))
                conn.commit()
                
        # Format confirmation message
        frequency = "daily" if is_daily else "one time"
        emoji = "🔄" if is_daily else "⏰"
        
        bot.send_message(
            message.chat.id, 
            f"✅ Reminder set!\n\n"
            f"⏰ Event: {event_type}\n"
            f"🕑 Time: {event_time_str}\n"
            f"⏱ Remind: {mins} minutes before\n"
            f"{emoji} Frequency: {frequency}"
        )
        send_main_menu(message.chat.id)
    except Exception as e:
        logger.error(f"Error saving reminder: {str(e)}")
        bot.send_message(message.chat.id, "Failed to set reminder. Please try again.")

# ====================== SETTINGS HANDLERS ======================
@bot.message_handler(func=lambda msg: msg.text.startswith('🕰 Change Time Format'))
def change_time_format(message):
    user = get_user(message.from_user.id)
    if not user: 
        bot.send_message(message.chat.id, "Please set your timezone first with /start")
        return
        
    tz, fmt = user
    new_fmt = '24hr' if fmt == '12hr' else '12hr'
    set_time_format(message.from_user.id, new_fmt)
    bot.send_message(message.chat.id, f"✅ Time format changed to {new_fmt}")
    send_main_menu(message.chat.id)

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