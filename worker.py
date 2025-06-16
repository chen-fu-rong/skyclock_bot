import asyncio
import logging
from main import pool, application, get_tz_offset

logger = logging.getLogger(__name__)

# Calculate next event time (copied from main.py to keep self-contained)
from datetime import datetime, timedelta, timezone

def next_occurrence(base: datetime, minute: int, hour_parity: str) -> datetime:
    candidate = base.replace(minute=minute, second=0, microsecond=0)
    if candidate <= base:
        candidate += timedelta(hours=1)
    while (hour_parity == "even" and candidate.hour % 2 != 0) or \
          (hour_parity == "odd" and candidate.hour % 2 == 0):
        candidate += timedelta(hours=1)
    return candidate

async def get_next_event_time(event: str, user_offset: str) -> datetime:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if event == "grandma":
        next_time = next_occurrence(now, 5, "even")
    elif event == "geyser":
        next_time = next_occurrence(now, 35, "odd")
    elif event == "turtle":
        next_time = next_occurrence(now, 20, "even")
    else:
        return None

    sign = 1 if user_offset.startswith('+') else -1
    h, m = map(int, user_offset[1:].split(":"))
    offset_delta = timedelta(hours=sign * h, minutes=sign * m)
    local_time = next_time + offset_delta
    return next_time, local_time

async def send_notification(user_id: int, event: str, event_utc_time: datetime, local_time: datetime):
    try:
        await application.bot.send_message(
            chat_id=user_id,
            text=f"⏰ Reminder: {event.capitalize()} event starts at {local_time.strftime('%I:%M %p')} (your local time)."
        )
        logger.info(f"Notification sent to {user_id} for {event}")
    except Exception as e:
        logger.error(f"Failed to send notification to {user_id}: {e}")

async def check_and_notify():
    """
    Periodic check for upcoming events to notify users.
    Sends notification 5 minutes before event time.
    """
    logger.info("Checking scheduled notifications...")

    now_utc = datetime.utcnow().replace(second=0, microsecond=0)
    notify_before = timedelta(minutes=5)  # Notify 5 minutes before event

    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            # Fetch all users and events with notifications enabled
            await cur.execute("SELECT user_id, event FROM notifications;")
            rows = await cur.fetchall()

            for user_id, event in rows:
                user_tz = await get_tz_offset(user_id)
                event_utc_time, event_local_time = await get_next_event_time(event, user_tz)
                if event_utc_time is None:
                    continue

                # If current time is within notification window
                if event_utc_time - notify_before <= now_utc < event_utc_time:
                    await send_notification(user_id, event, event_utc_time, event_local_time)

async def run_scheduler():
    while True:
        try:
            await check_and_notify()
        except Exception as e:
            logger.error(f"Error during notification check: {e}")
        await asyncio.sleep(60)  # Run every 60 seconds

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting worker for scheduled notifications...")
    asyncio.run(run_scheduler())
