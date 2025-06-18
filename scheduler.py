import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta
import pytz

async def send_reminder(application, user_id, message):
    try:
        await application.bot.send_message(
            chat_id=user_id,
            text=f"⏰ Reminder!\n\n{message}"
        )
        return True
    except Exception as e:
        logging.error(f"Failed to send reminder to {user_id}: {e}")
        return False

def start_scheduler(application, db):
    scheduler = AsyncIOScheduler()
    
    async def check_reminders():
        now = datetime.utcnow().replace(tzinfo=pytz.utc)
        reminders = db.get_due_reminders(now)
        for (reminder_id, user_id, message, is_recurring) in reminders:
            success = await send_reminder(application, user_id, message)
            if success and not is_recurring:
                db.delete_reminder(reminder_id, user_id)
    
    scheduler.add_job(check_reminders, 'interval', minutes=1)
    
    scheduler.start()