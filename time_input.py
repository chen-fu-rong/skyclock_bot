from telegram import ReplyKeyboardMarkup, KeyboardButton
import re
from datetime import datetime

def get_time_input_keyboard():
    """Create a numeric keyboard for time input"""
    return ReplyKeyboardMarkup([
        [KeyboardButton(str(i)) for i in range(1, 13)],
        [KeyboardButton("00"), KeyboardButton("15"), KeyboardButton("30"), KeyboardButton("45")],
        [KeyboardButton("AM"), KeyboardButton("PM")],
        [KeyboardButton("Cancel")]
    ], resize_keyboard=True, one_time_keyboard=True)

def parse_time_input(text):
    """Convert user time input string to a time object"""
    try:
        text = text.strip().upper()

        # Matches formats like: 10:30 AM, 10 AM
        if re.match(r'^\d{1,2}:\d{2}\s*[AP]M$', text):
            return datetime.strptime(text, '%I:%M %p').time()
        elif re.match(r'^\d{1,2}\s*[AP]M$', text):
            return datetime.strptime(text, '%I %p').time()
        elif re.match(r'^\d{1,2}:\d{2}$', text):  # 24-hour format: 13:30
            return datetime.strptime(text, '%H:%M').time()
        elif re.match(r'^\d{1,2}$', text):  # Only hour provided
            hour = int(text)
            if 0 <= hour <= 23:
                return datetime.strptime(f"{hour:02d}:00", '%H:%M').time()

    except ValueError:
        pass

    return None
