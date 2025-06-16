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

# Calculate next event time
def next_occurrence(base: datetime, minute: int, hour_parity: str) -> datetime:
    candidate = base.replace(minute=minute, second=0, microsecond=0)
    if candidate <= base:
        candidate += timedelta(hours=1)
    while (hour_parity == "even" and candidate.hour % 2 != 0) or \
          (hour_parity == "odd" and candidate.hour % 2 == 0):
        candidate += timedelta(hours=1)
    return candidate

async def get_tz_offset(user_id: int) -> str:
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT tz_offset FROM users WHERE user_id = %s;",
                (user_id,)
            )
            row = await cur.fetchone()
            return row[0] if row else "+00:00"

async def get_next_event_time(event: str, user_offset: str) -> tuple:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if event == "grandma":
        next_time = next_occurrence(now, 5, "even")
    elif event == "geyser":
        next_time = next_occurrence(now, 35, "odd")
    elif event == "turtle":
        next_time = next_occurrence(now, 20, "even")
    else:
        return None, None

    sign = 1 if user_offset.startswith('+') else -1
    h, m = map(int, user_offset[1:].split(":"))
    offset_delta = timedelta(hours=sign * h, minutes=sign * m)
    local_time = next_time + offset_delta
    return next_time, local_time

async def send_notification(user_id: int, event: str):
    try:
        user_tz = await get_tz_offset(user_id)
        event_utc_time, event_local_time = await get_next_event_time(event, user_tz)
        if not event_utc_time:
            return
            
        await bot.send_message(
            chat_id=user_id,
            text=f"⏰ Reminder: {event.capitalize()} starts at {event_local_time.strftime('%I:%M %p')} (your time)!"
        )
        logger.info(f"✅ Notification sent to {user_id} for {event}")
    except Exception as e:
        logger.error(f"❌ Failed to send notification to {user_id}: {e}")

async def check_and_notify():
    logger.info("🔍 Checking scheduled notifications...")
    now_utc = datetime.utcnow().replace(second=0, microsecond=0)
    notify_before = timedelta(minutes=5)  # Notify 5 minutes before event

    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT user_id, event FROM notifications;")
            rows = await cur.fetchall()

            for user_id, event in rows:
                try:
                    user_tz = await get_tz_offset(user_id)
                    event_utc_time, _ = await get_next_event_time(event, user_tz)
                    if not event_utc_time:
                        continue

                    # Check if current time is within notification window
                    if event_utc_time - notify_before <= now_utc < event_utc_time:
                        await send_notification(user_id, event)
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