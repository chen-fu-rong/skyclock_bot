import os
import logging
from telegram.ext import Application, CommandHandler
from database import Database
from utils import convert_to_utc

# Initialize
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
DB_URL = os.getenv("DATABASE_URL")
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")

async def start(update, context):
    """Send welcome message"""
    user = update.effective_user
    await update.message.reply_html(f"✨ Welcome {user.mention_html()}!\n"
                                   "I'm your Sky: CotL assistant\n\n"
                                   "Available commands:\n"
                                   "/settimezone - Configure reminders\n"
                                   "/reset - Show daily reset timer\n"
                                   "/remind - Create custom reminder")

async def set_timezone(update, context):
    """Set user timezone"""
    # Implementation using pytz
    pass

async def daily_reset(update, context):
    """Show time until next reset"""
    # PST/PDT to UTC conversion logic
    pass

async def create_reminder(update, context):
    """Create custom reminder"""
    # Parse: /remind 18:30 "Candle run at Sanctuary"
    pass

def main():
    # Connect to DB
    db = Database(DB_URL)
    
    # Create bot
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("settimezone", set_timezone))
    application.add_handler(CommandHandler("reset", daily_reset))
    application.add_handler(CommandHandler("remind", create_reminder))
    
    # Start scheduler
    from scheduler import start_scheduler
    start_scheduler(application, db)
    
    # Run bot
    application.run_polling()

if __name__ == "__main__":
    main()