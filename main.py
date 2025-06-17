import os
import logging
import pytz
import psycopg2
import urllib.parse
from datetime import datetime, time, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters
)

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
TIMEZONE, EVENT_NOTIFICATION, TIME_FORMAT = range(3)

# Database functions
def get_db_connection():
    """Create and return a PostgreSQL database connection"""
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")
    
    result = urllib.parse.urlparse(database_url)
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
    """Initialize database tables and perform migrations"""
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Create users table
            cur.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    chat_id BIGINT NOT NULL,
                    timezone VARCHAR(50) DEFAULT 'Asia/Yangon',
                    time_format VARCHAR(5) DEFAULT '24h',
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
            ''')
            
            # Create events table with all columns
            cur.execute('''
                CREATE TABLE IF NOT EXISTS events (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    chat_id BIGINT NOT NULL,
                    event_type VARCHAR(20) NOT NULL,
                    notify_minutes INT NOT NULL,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                );
            ''')
            
            # Add chat_id column if it doesn't exist (migration)
            cur.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 
                        FROM information_schema.columns 
                        WHERE table_name='events' AND column_name='chat_id'
                    ) THEN
                        ALTER TABLE events ADD COLUMN chat_id BIGINT;
                    END IF;
                END$$;
            """)
            
            # Set default value for existing rows
            cur.execute("UPDATE events SET chat_id = 0 WHERE chat_id IS NULL;")
            cur.execute("ALTER TABLE events ALTER COLUMN chat_id SET NOT NULL;")
            
        conn.commit()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {str(e)}")
    finally:
        if conn:
            conn.close()

# ... (rest of the code remains the same until the create_event function) ...

def create_event(user_id, chat_id, event_type, notify_minutes):
    """Create a new event notification"""
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO events (user_id, chat_id, event_type, notify_minutes) VALUES (%s, %s, %s, %s)",
                (user_id, chat_id, event_type, notify_minutes)
            )
        conn.commit()
    except Exception as e:
        logger.error(f"Error creating event: {str(e)}")
    finally:
        if conn:
            conn.close()

# ... (rest of the code remains the same) ...

# Background tasks
async def check_reminders(context: ContextTypes.DEFAULT_TYPE):
    """Check and send due reminders"""
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            current_time = datetime.now(pytz.utc)
            
            # Get active reminders
            cur.execute('''
                SELECT id, user_id, event_type, notify_minutes, chat_id 
                FROM events
                WHERE is_active = TRUE
            ''')
            events = cur.fetchall()
            
            # Check each event
            for event in events:
                event_id, user_id, event_type, notify_minutes, chat_id = event
                
                # Get user's timezone
                user = get_user(user_id)
                if not user:
                    continue
                    
                user_tz = pytz.timezone(user[2])
                user_time = datetime.now(user_tz)
                
                # Calculate next event time
                if event_type == 'grandma':
                    event_time = calculate_grandma_time(user_time)
                elif event_type == 'geyser':
                    event_time = calculate_geyser_time(user_time)
                elif event_type == 'turtle':
                    event_time = calculate_turtle_time(user_time)
                else:
                    continue
                
                # Calculate notification time
                notification_time = event_time - timedelta(minutes=notify_minutes)
                
                # Check if it's time to notify
                if notification_time <= current_time <= event_time:
                    try:
                        # Format event time
                        formatted_time = format_time(event_time.astimezone(user_tz), user[3])
                        
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=f"🔔 Reminder: {event_type.capitalize()} event starts at {formatted_time}!"
                        )
                    except Exception as e:
                        logger.warning(f"Failed to send reminder to {chat_id}: {str(e)}")
    except Exception as e:
        logger.error(f"Reminder check failed: {str(e)}")

def main() -> None:
    """Start the bot"""
    # Initialize database
    init_db()
    
    # Create Telegram application
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_TOKEN environment variable not set")
    
    # Get Render environment details
    render_external_url = os.getenv('RENDER_EXTERNAL_URL')
    port = os.getenv('PORT', '8443')
    
    application = Application.builder().token(token).build()
    
    # Conversation handler for timezone setup
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            TIMEZONE: [
                CallbackQueryHandler(handle_timezone, pattern='^tz_'),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_manual_timezone)
            ],
            EVENT_NOTIFICATION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_notification_minutes)
            ]
        },
        fallbacks=[CommandHandler("start", start)]
    )
    
    # Register handlers
    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(handle_menu, pattern='^menu_'))
    application.add_handler(CallbackQueryHandler(handle_wax_event, pattern='^wax_'))
    application.add_handler(CallbackQueryHandler(handle_notification_request, pattern='^notify_'))
    application.add_handler(CallbackQueryHandler(show_settings_menu, pattern='^settings_notifications$'))
    application.add_handler(CallbackQueryHandler(show_notification_settings, pattern='^settings_notifications$'))
    application.add_handler(CallbackQueryHandler(handle_notification_toggle, pattern='^toggle_'))
    application.add_handler(CallbackQueryHandler(show_time_format_settings, pattern='^settings_time_format$'))
    application.add_handler(CallbackQueryHandler(handle_time_format, pattern='^timeformat_'))
    
    # Schedule background jobs
    job_queue = application.job_queue
    job_queue.run_repeating(check_reminders, interval=60, first=10)
    
    # Handle Render deployment
    if render_external_url:
        # Running on Render - use webhook
        webhook_url = f'{render_external_url}/{token}'
        application.run_webhook(
            listen="0.0.0.0",
            port=int(port),
            url_path=token,
            webhook_url=webhook_url
        )
        logger.info(f"Using webhook: {webhook_url}")
    else:
        # Running locally - use polling
        application.run_polling(drop_pending_updates=True)
        logger.info("Using polling method")

if __name__ == "__main__":
    main()