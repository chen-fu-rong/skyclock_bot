import pytz
from datetime import datetime, timedelta

def get_next_reset_utc():
    """Calculate next daily reset (00:00 PST → UTC)"""
    pst = pytz.timezone('America/Los_Angeles')
    now_utc = datetime.utcnow().replace(tzinfo=pytz.utc)
    now_pst = now_utc.astimezone(pst)
    
    if now_pst.hour >= 0:
        reset_pst = (now_pst + timedelta(days=1)).replace(hour=0, minute=0, second=0)
    else:
        reset_pst = now_pst.replace(hour=0, minute=0, second=0)
    
    return reset_pst.astimezone(pytz.utc)

def convert_to_user_tz(utc_time, user_tz):
    """Convert UTC time to user's timezone"""
    return utc_time.astimezone(pytz.timezone(user_tz))