import os
import logging
import psycopg2
from urllib.parse import urlparse
from datetime import datetime, time, timedelta, timezone
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    CallbackContext
)

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Sky event schedule (UTC)
SKY_EVENTS = {
    "Geyser": {
        "times": [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22],
        "duration": (0, 12),  # Active from :00 to :12
        "message": "🦀 **Geyser is active now!** (0:00-12:00 UTC)\nCollect wax quickly!"
    },
    "Grandma": {
        "times": [1, 7, 13, 19],
        "duration": (35, 45),  # Active from :35 to :45
        "message": "👵 **Grandma's dinner is ready!** (35:00-45:00 UTC)\nGet that wax!"
    },
    "Turtle": {
        "times": [9, 21],
        "duration": (50, 60),  # Active from :50 to :00
        "message": "🐢 **Turtle is here!** (50:00-00:00 UTC)\nFollow for wax!"
    },
    "Sunset": {
        "times": [12],
        "duration": (0, 5),  # Active from :00 to :05
        "message": "🌅 **Sunset time at Sanctuary Islands!** (00:00-05:00 UTC)"
    }
}

# Database functions
def get_db_connection():
    """Create and return a PostgreSQL database connection"""
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")
    
    result = urlparse(database_url)
    conn = psycopg2.connect(
        dbname=result.path[1:],
        user=result.username,
        password=result.password,
        host=result.hostname,
        port=result.port,
        sslmode='require'
    )
    return conn

def init_db():
    """Initialize database tables"""
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute('''
                CREATE TABLE IF NOT EXISTS reminders (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    event_name VARCHAR(100) NOT NULL,
                    event_time TIMESTAMPTZ NOT NULL,
                    chat_id BIGINT NOT NULL,
                    scheduled BOOLEAN DEFAULT FALSE
                );
            ''')
            cur.execute('''
                CREATE TABLE IF NOT EXISTS event_subscriptions (
                    chat_id BIGINT PRIMARY KEY,
                    subscribed BOOLEAN DEFAULT TRUE
                );
            ''')
        conn.commit()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {str(e)}")
    finally:
        if conn:
            conn.close()

# Bot command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send welcome message"""
    await update.message.reply_text(
        "🕯️ **Sky: Children of the Light Reminder Bot**\n\n"
        "I'll notify you about in-game events! Use commands:\n"
        "/events - Show upcoming events\n"
        "/subscribe - Get automatic event reminders\n"
        "/unsubscribe - Stop reminders\n"
        "/setreminder [event] [HH:MM] - Set custom reminder\n"
        "/help - Show all commands"
    )

async def list_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List upcoming Sky events"""
    now = datetime.now(timezone.utc)
    response = "⏰ **Upcoming Sky Events (UTC):**\n\n"
    
    for event_name, details in SKY_EVENTS.items():
        times = details["times"]
        for hour in times:
            # Calculate next occurrence
            event_time = now.replace(
                hour=hour,
                minute=0,
                second=0,
                microsecond=0
            )
            if event_time < now:
                event_time += timedelta(days=1)
            
            # Format time
            time_str = event_time.strftime("%H:%M")
            response += f"• {event_name}: {time_str} UTC\n"
    
    response += "\nUse /subscribe to get automatic reminders!"
    await update.message.reply_text(response)

async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Subscribe chat to automatic event reminders"""
    chat_id = update.effective_chat.id
    
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO event_subscriptions (chat_id, subscribed) "
                "VALUES (%s, TRUE) "
                "ON CONFLICT (chat_id) DO UPDATE SET subscribed = EXCLUDED.subscribed",
                (chat_id,)
            )
        conn.commit()
        await update.message.reply_text("✅ You're now subscribed to event reminders!")
    except Exception as e:
        logger.error(f"Subscription failed: {str(e)}")
        await update.message.reply_text("❌ Failed to update subscription. Please try again.")
    finally:
        if conn:
            conn.close()

async def unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unsubscribe chat from event reminders"""
    chat_id = update.effective_chat.id
    
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE event_subscriptions SET subscribed = FALSE WHERE chat_id = %s",
                (chat_id,)
            )
        conn.commit()
        await update.message.reply_text("❎ You've unsubscribed from event reminders.")
    except Exception as e:
        logger.error(f"Unsubscription failed: {str(e)}")
        await update.message.reply_text("❌ Failed to update subscription. Please try again.")
    finally:
        if conn:
            conn.close()

async def set_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set a custom event reminder"""
    try:
        args = context.args
        if len(args) < 2:
            raise ValueError("Insufficient arguments")
        
        event_name = " ".join(args[:-1])
        time_str = args[-1]
        
        # Parse time
        event_time = datetime.strptime(time_str, '%H:%M').time()
        now = datetime.now(timezone.utc)
        
        # Calculate next occurrence
        next_occurrence = now.replace(
            hour=event_time.hour,
            minute=event_time.minute,
            second=0,
            microsecond=0
        )
        if next_occurrence < now:
            next_occurrence += timedelta(days=1)
        
        # Save to database
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO reminders (user_id, event_name, event_time, chat_id) "
                "VALUES (%s, %s, %s, %s)",
                (update.effective_user.id, event_name, next_occurrence, update.effective_chat.id)
            )
        conn.commit()
        
        await update.message.reply_text(
            f"⏰ Reminder set for '{event_name}' at {next_occurrence.strftime('%H:%M')} UTC!"
        )
    except (ValueError, IndexError):
        await update.message.reply_text("Usage: /setreminder [event name] [HH:MM]\nExample: /setremind Geyser 02:00")
    except Exception as e:
        logger.error(f"Set reminder failed: {str(e)}")
        await update.message.reply_text("❌ Failed to set reminder. Please try again.")
    finally:
        if conn:
            conn.close()

# Background tasks
async def check_reminders(context: CallbackContext):
    """Check and send due reminders"""
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            current_time = datetime.now(timezone.utc)
            
            # Get due reminders
            cur.execute(
                "SELECT id, chat_id, event_name FROM reminders "
                "WHERE event_time <= %s",
                (current_time,)
            )
            reminders = cur.fetchall()
            
            # Send notifications
            for reminder_id, chat_id, event_name in reminders:
                try:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=f"⏰ **Reminder:** {event_name} is happening NOW!"
                    )
                except Exception as e:
                    logger.warning(f"Failed to send reminder to {chat_id}: {str(e)}")
                
                # Delete sent reminder
                cur.execute(
                    "DELETE FROM reminders WHERE id = %s",
                    (reminder_id,)
                )
            
            conn.commit()
    except Exception as e:
        logger.error(f"Reminder check failed: {str(e)}")
    finally:
        if conn:
            conn.close()

async def check_sky_events(context: CallbackContext):
    """Check and notify about active Sky events"""
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            now = datetime.now(timezone.utc)
            current_hour = now.hour
            current_minute = now.minute
            
            # Get subscribed chats
            cur.execute("SELECT chat_id FROM event_subscriptions WHERE subscribed = TRUE")
            subscribed_chats = [row[0] for row in cur.fetchall()]
            
            # Check active events
            for event_name, details in SKY_EVENTS.items():
                if current_hour in details["times"]:
                    start_min, end_min = details["duration"]
                    if start_min <= current_minute < end_min:
                        # Send to all subscribed chats
                        for chat_id in subscribed_chats:
                            try:
                                await context.bot.send_message(
                                    chat_id=chat_id,
                                    text=details["message"],
                                    parse_mode="Markdown"
                                )
                            except Exception as e:
                                logger.warning(f"Failed to send event to {chat_id}: {str(e)}")
    except Exception as e:
        logger.error(f"Event check failed: {str(e)}")
    finally:
        if conn:
            conn.close()

async def schedule_daily_events(context: CallbackContext):
    """Schedule next day's events"""
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            now = datetime.now(timezone.utc)
            tomorrow = now + timedelta(days=1)
            
            # Clear old scheduled events
            cur.execute("DELETE FROM reminders WHERE scheduled = TRUE")
            
            # Schedule events for tomorrow
            for event_name, details in SKY_EVENTS.items():
                for hour in details["times"]:
                    event_time = tomorrow.replace(
                        hour=hour,
                        minute=0,
                        second=0,
                        microsecond=0
                    )
                    
                    # Create reminder 5 minutes before event
                    reminder_time = event_time - timedelta(minutes=5)
                    
                    # Save to database
                    cur.execute(
                        "INSERT INTO reminders (event_name, event_time, chat_id, user_id, scheduled) "
                        "VALUES (%s, %s, %s, %s, TRUE)",
                        (f"{event_name} Reminder", reminder_time, 0, 0)
                    )
            
            conn.commit()
            logger.info("Scheduled next day's events")
    except Exception as e:
        logger.error(f"Daily scheduling failed: {str(e)}")
    finally:
        if conn:
            conn.close()

def main() -> None:
    """Start the bot"""
    # Initialize database
    init_db()
    
    # Create Telegram application
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_TOKEN environment variable not set")
    
    application = Application.builder().token(token).build()
    
    # Register commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", start))
    application.add_handler(CommandHandler("events", list_events))
    application.add_handler(CommandHandler("subscribe", subscribe))
    application.add_handler(CommandHandler("unsubscribe", unsubscribe))
    application.add_handler(CommandHandler("setreminder", set_reminder))
    
    # Schedule background jobs
    job_queue = application.job_queue
    
    # Check reminders every minute
    job_queue.run_repeating(
        callback=check_reminders,
        interval=60,
        first=10
    )
    
    # Check Sky events every minute
    job_queue.run_repeating(
        callback=check_sky_events,
        interval=60,
        first=15
    )
    
    # Schedule daily events at 23:50 UTC
    job_queue.run_daily(
        callback=schedule_daily_events,
        time=time(hour=23, minute=50, tzinfo=timezone.utc),
        days=(0, 1, 2, 3, 4, 5, 6)
    )
    
    # Start the bot
    application.run_polling()

if __name__ == "__main__":
    main()