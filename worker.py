import os
import asyncio
import logging
from telegram.ext import Application
from main import pool, check_scheduled_events

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    # Open database pool
    await pool.open()
    await pool.wait()

    # Build bot app (no webhook/polling needed)
    app = Application.builder().token(os.getenv("BOT_TOKEN")).build()

    # Start job to check scheduled notifications every minute
    job_queue = app.job_queue
    job_queue.run_repeating(check_scheduled_events, interval=60, first=5)

    logger.info("✅ Notification worker started")
    await app.initialize()
    await app.start()
    await asyncio.Event().wait()  # Keeps the app running

if __name__ == "__main__":
    asyncio.run(main())
