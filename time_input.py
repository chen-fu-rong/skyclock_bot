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
    try:
        text = text.strip().upper()
        # Handle formats like "6:30 PM"
        if re.match(r'^\d{1,2}[: ]\d{1,2}\s*[AP]M$', text):
            return datetime.strptime(text, '%I:%M %p').time()
        # Handle formats like "6 PM"
        elif re.match(r'^\d{1,2}\s*[AP]M$', text):
            return datetime.strptime(text, '%I %p').time()
        # Handle 24-hour formats like "18:30"
        elif re.match(r'^\d{1,2}:\d{1,2}$', text):
            return datetime.strptime(text, '%H:%M').time()
        # Handle single numbers (hours)
        elif re.match(r'^\d{1,2}$', text):
            hour = int(text)
            if 0 <= hour <= 23:
                return time(hour=hour)
        return None
    except ValueError:
        return None
