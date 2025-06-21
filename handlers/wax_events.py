# handlers/wax_events.py
import telebot
from services.database import get_db
from utils.formatters import format_time
import pytz

def register_wax_handlers(bot):
    @bot.message_handler(func=lambda msg: msg.text == '🕯 Wax Events')
    def wax_menu(message):
        from services.database import update_last_interaction
        update_last_interaction(message.from_user.id)
        from handlers.core import send_wax_menu
        send_wax_menu(bot, message.chat.id)