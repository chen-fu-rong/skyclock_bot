# main.py
import os
import logging
from bot import app, bot
from services.database import init_db
from services.scheduler import scheduler, setup_scheduled_tasks
from handlers import register_handlers

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

if __name__ == '__main__':
    logger.info("Initializing database...")
    init_db()
    logger.info("Database initialized")

    logger.info("Setting up scheduled tasks...")
    setup_scheduled_tasks()
    
    # Schedule existing reminders
    logger.info("Scheduling existing reminders...")
    from handlers.reminders import schedule_existing_reminders
    schedule_existing_reminders()
    
    logger.info("Registering handlers...")
    register_handlers(bot)

    logger.info("Setting up webhook...")
    WEBHOOK_URL = os.getenv("WEBHOOK_URL") or "https://skyclock-bot.onrender.com/webhook"
    try:
        bot.remove_webhook()
        bot.set_webhook(url=WEBHOOK_URL)
        logger.info(f"Webhook set to: {WEBHOOK_URL}")
    except Exception as e:
        logger.error(f"Error setting webhook: {str(e)}")

    logger.info("Starting Flask app...")
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)