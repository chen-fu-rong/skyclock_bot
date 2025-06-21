# services/scheduler.py
from apscheduler.schedulers.background import BackgroundScheduler
from services import shard_service
import logging

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()

def setup_scheduled_tasks():
    """Setup recurring maintenance tasks"""
    # Daily validation at 00:05 UTC
    scheduler.add_job(
        lambda: shard_service.validate_shard_predictions(7),
        'cron',
        hour=0,
        minute=5,
        name="daily_shard_validation"
    )
    
    # Weekly phase map refresh
    scheduler.add_job(
        shard_service.refresh_phase_map,
        'cron',
        day_of_week='sun',
        hour=3,
        minute=0,
        name="weekly_phase_map_refresh"
    )
    
    # Monthly full validation
    scheduler.add_job(
        lambda: shard_service.validate_shard_predictions(30),
        'cron',
        day=1,
        hour=1,
        minute=0,
        name="monthly_full_validation"
    )
    
    # Weekly shard data update
    scheduler.add_job(
        shard_service.update_shard_data_from_official,
        'cron',
        day_of_week='mon',
        hour=4,
        minute=0,
        name="weekly_shard_data_update"
    )

    logger.info("Scheduled tasks registered")