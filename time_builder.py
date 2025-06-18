from telegram import ReplyKeyboardMarkup, KeyboardButton
import re

def get_time_input_keyboard():
    """Create a numeric keyboard for time input"""
    return ReplyKeyboardMarkup([
        [KeyboardButton(str(i)) for i in range(1, 13)],
        [KeyboardButton("00"), KeyboardButton("15"), KeyboardButton("30"), KeyboardButton("45")],
        [KeyboardButton("AM"), KeyboardButton("PM")],
        [KeyboardButton("Cancel")]
    ], resize_keyboard=True, one_time_keyboard=True)

def parse_time_input(text):
    """Convert user time input to datetime"""
    try:
        # Try different time formats
        if re.match(r'^\d{1,2}[: ]\d{2}\s*[ap]m?$', text, re.IGNORECASE):
            return datetime.strptime(text, '%I:%M %p')
        elif re.match(r'^\d{1,2}[: ]\d{2}$', text):
            return datetime.strptime(text, '%H:%M')
        elif re.match(r'^\d{1,2}\s*[ap]m?$', text, re.IGNORECASE):
            return datetime.strptime(text, '%I %p')
        return None
    except ValueError:
        return None