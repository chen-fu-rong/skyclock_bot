# main.py
import os
import logging
from bot import app, bot
from services.database import init_db
from services.scheduler import scheduler, setup_scheduled_tasks
from handlers import register_handlers
from services.shard_service import load_shard_data_from_db, DEFAULT_PHASE_MAP, save_shard_data_to_db, refresh_phase_map

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

    # Load shard data
    logger.info("Loading shard data from database...")
    if not load_shard_data_from_db():
        logger.info("Loading default shard data...")
        save_shard_data_to_db(DEFAULT_PHASE_MAP)
        load_shard_data_from_db()
    
    logger.info("Refreshing phase map...")
    refresh_phase_map()
    
    logger.info("Setting up scheduled tasks...")
    setup_scheduled_tasks()
    
    # Schedule existing reminders
    logger.info("Scheduling existing reminders...")
    from handlers.reminders import schedule_existing_reminders
    schedule_existing_reminders()
    
    logger.info("Registering handlers...")
    register_handlers(bot)

    logger.info("Setting up webhook...")
    bot.remove_webhook()
    WEBHOOK_URL = os.getenv("WEBHOOK_URL") or "https://skyclock-bot.onrender.com/webhook"
    bot.set_webhook(url=WEBHOOK_URL)
    logger.info(f"Webhook set to: {WEBHOOK_URL}")

    logger.info("Starting Flask app...")
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)