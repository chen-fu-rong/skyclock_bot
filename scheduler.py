from apscheduler.schedulers.asyncio import AsyncIOScheduler
from utils import get_next_reset_utc

def start_scheduler(application, db):
    scheduler = AsyncIOScheduler()
    
    # Daily reset notification (runs every day at 07:30 UTC)
    @scheduler.scheduled_job('cron', hour=7, minute=30)
    async def notify_reset():
        query = "SELECT user_id FROM users WHERE ..."  # Get users who want reset alerts
        reset_utc = get_next_reset_utc()
        
        async with application:
            for user_id in users:
                await application.bot.send_message(
                    chat_id=user_id,
                    text=f"⏰ Daily reset in 30 minutes! ({reset_utc})"
                )
    
    # Traveling Spirit alerts (Thursdays 00:00 PST → 08:00 UTC)
    @scheduler.scheduled_job('cron', day_of_week='thu', hour=8)
    async def notify_spirit():
        # Implementation
        pass
        
    scheduler.start()