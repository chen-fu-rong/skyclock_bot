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
    """Convert user time input to time object"""
    try:
        # Normalize input
        text = text.strip().upper()
        # Try formats: HH:MM AM/PM, HH AM/PM, HH:MM
        if re.match(r'^\d{1,2}[: ]\d{1,2}\s*[AP]M$', text):
            return datetime.strptime(text, '%I:%M %p').time()
        elif re.match(r'^\d{1,2}\s*[AP]M$', text):
            return datetime.strptime(text, '%I %p').time()
        elif re.match(r'^\d{1,2}:\d{1,2}$', text):
            return datetime.strptime(text, '%H:%M').time()
        elif re.match(r'^\d{1,2}$', text):
            hour = int(text)
            if 0 <= hour <= 23:
                return datetime.strptime(str(hour), '%H').time()
        return None
    except ValueError:
        return None