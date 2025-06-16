import os
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from telegram import Bot
from psycopg_pool import AsyncConnectionPool

# Initialize logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Create database pool
pool = AsyncConnectionPool(
    conninfo=os.getenv("DATABASE_URL"),
    min_size=1,
    max_size=3,
    open=False
)

# Create bot instance
bot = Bot(token=os.getenv("BOT_TOKEN"))

# Constants
MYANMAR_OFFSET = timedelta(hours=6, minutes=30)
EVENT_TIMES = {
    "grandma": {"minute": 5, "hour_parity": "even"},
    "geyser": {"minute": 35, "hour_parity": "odd"},
    "turtle": {"minute": 20, "hour_parity": "even"}
}

# Time utilities
def format_12h(dt: datetime) -> str:
    return dt.strftime("%I:%M %p").lstrip("0")

def next_occurrence(base: datetime, minute: int, hour_parity: str) -> datetime:
    candidate = base.replace(minute=minute, second=0, microsecond=0)
    if candidate <= base:
        candidate += timedelta(hours=1)
    while (hour_parity == "even" and candidate.hour % 2 != 0) or \
          (hour_parity == "odd" and candidate.hour % 2 == 0):
        candidate += timedelta(hours=1)
    return candidate

def get_next_event_time(event: str) -> tuple:
    now_utc = datetime.utcnow().replace(tzinfo=timezone.utc)
    config = EVENT_TIMES[event]
    
    # Calculate next occurrence in UTC
    next_utc = next_occurrence(now_utc, config["minute"], config["hour_parity"])
    
    # Convert to Myanmar time
    next_myanmar = next_utc + MYANMAR_OFFSET
    
    return next_utc, next_myanmar

async def send_notification(user_id: int, event: str, next_utc: datetime, next_myanmar: datetime):
    try:
        # Calculate remaining minutes
        now = datetime.utcnow().replace(tzinfo=timezone.utc)
        remaining = int((next_utc - now).total_seconds() // 60)
        
        # Format the message
        message = (
            f"⏰ <b>Reminder: {event.capitalize()} starts soon!</b>\n"
            f"🕒 <b>Myanmar Time:</b> {format_12h(next_myanmar)}\n"
            f"⏱️ <b>Starting in:</b> {remaining} minutes"
        )
        
        await bot.send_message(
            chat_id=user_id,
            text=message,
            parse_mode="HTML"
        )
        logger.info(f"✅ Notification sent to {user_id} for {event}")
    except Exception as e:
        logger.error(f"❌ Failed to send notification to {user_id}: {e}")

async def check_and_notify():
    logger.info("🔍 Checking scheduled notifications...")
    now_utc = datetime.utcnow().replace(tzinfo=timezone.utc)
    notify_before = timedelta(minutes=5)  # Notify 5 minutes before event

    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT user_id, event FROM notifications;")
            rows = await cur.fetchall()

            for user_id, event in rows:
                try:
                    # Get event times
                    event_utc_time, event_myanmar_time = get_next_event_time(event)
                    
                    # Check if current time is within notification window
                    if event_utc_time - notify_before <= now_utc < event_utc_time:
                        await send_notification(user_id, event, event_utc_time, event_myanmar_time)
                except Exception as e:
                    logger.error(f"❌ Error processing user {user_id}: {e}")

async def run_scheduler():
    # Open database pool
    await pool.open()
    await pool.wait()
    logger.info("✅ Database pool connected")
    
    while True:
        try:
            await check_and_notify()
        except Exception as e:
            logger.error(f"⚠️ Error during notification check: {e}")
        await asyncio.sleep(60)  # Run every 60 seconds

if __name__ == "__main__":
    logger.info("🚀 Starting worker for scheduled notifications...")
    asyncio.run(run_scheduler())