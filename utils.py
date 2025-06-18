import pytz
from datetime import datetime, timedelta

def get_next_reset_utc():
    """Calculate next daily reset (00:00 PST → UTC)"""
    pst = pytz.timezone('America/Los_Angeles')
    now_utc = datetime.utcnow().replace(tzinfo=pytz.utc)
    now_pst = now_utc.astimezone(pst)
    
    if now_pst.hour >= 0:
        reset_pst = (now_pst + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    else:
        reset_pst = now_pst.replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    
    return reset_pst.astimezone(pytz.utc)

def convert_to_user_tz(utc_time, user_tz):
    """Convert UTC time to user's timezone"""
    try:
        tz = pytz.timezone(user_tz)
        return utc_time.astimezone(tz)
    except pytz.UnknownTimeZoneError:
        return utc_time  # Fallback to UTC

def format_timedelta(td):
    """Convert timedelta to human-readable format"""
    total_seconds = int(td.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}h {minutes}m"

def validate_timezone(timezone_str):
    """Check if timezone string is valid"""
    try:
        pytz.timezone(timezone_str)
        return True
    except pytz.UnknownTimeZoneError:
        return False