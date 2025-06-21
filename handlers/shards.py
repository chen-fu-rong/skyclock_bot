# handlers/shards.py
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from services import shard_service
from utils.formatters import format_time
import logging
from datetime import date, datetime, timedelta

logger = logging.getLogger(__name__)

def send_shard_info(bot, chat_id, user_id, target_date=None):
    # Get user timezone
    from services.database import get_user
    user = get_user(user_id)
    if not user: 
        bot.send_message(chat_id, "Please set your timezone first with /start")
        return
        
    tz, fmt = user
    user_tz = pytz.timezone(tz)
    
    # Default to today if no date specified
    if not target_date:
        target_date = datetime.now(user_tz).date()
    
    # Get shard info
    shard_info = shard_service.get_shard_info(target_date)
    
    # Format message
    if shard_info["is_rest_day"]:
        message = (
            f"💎 <b>Shard - {target_date.strftime('%b %d, %Y')}</b>\n\n"
            "🌿 <b>Rest Day</b>\n"
            "No shard eruptions today"
        )
    else:
        type_emoji = "🔴" if shard_info["type"] == "Red" else "⚫"
        message = (
            f"💎 <b>Shard - {target_date.strftime('%b %d, %Y')}</b>\n\n"
            f"<b>Realm:</b> {shard_info['realm']}\n"
            f"<b>Area:</b> {shard_info['area']}\n"
            f"<b>Type:</b> {type_emoji} {shard_info['type']}\n"
            f"<b>Candles:</b> {shard_info['candles']}\n"
        )
    
    # Add eruption schedule
    message += "\n⏰ <b>Eruption Schedule (UTC):</b>\n"
    for hour in shard_service.SHARD_TIMES_UTC:
        hours = int(hour)
        minutes = int((hour - hours) * 60)
        message += f"• {hours:02d}:{minutes:02d}\n"
    
    # Add next eruption in user's timezone
    next_eruption = shard_service.get_next_eruption(user_tz)
    if next_eruption:
        user_time = format_time(next_eruption, fmt)
        time_diff = next_eruption - datetime.now(user_tz)
        hours, remainder = divmod(int(time_diff.total_seconds()), 3600)
        minutes = remainder // 60
        message += f"\n⏱ <b>Next Eruption:</b> {user_time} ({hours}h {minutes}m)"
    
    # Create navigation buttons
    keyboard = InlineKeyboardMarkup()
    prev_date = target_date - timedelta(days=1)
    next_date = target_date + timedelta(days=1)
    
    keyboard.row(
        InlineKeyboardButton("⬅️ Previous", callback_data=f"shard:{prev_date}"),
        InlineKeyboardButton("Next ➡️", callback_data=f"shard:{next_date}")
    )
    
    # Add today button if not viewing today
    today = datetime.now(user_tz).date()
    if target_date != today:
        keyboard.add(InlineKeyboardButton("⏩ Today", callback_data=f"shard:{today}"))
    
    try:
        bot.send_message(
            chat_id, 
            message, 
            parse_mode='HTML', 
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"Error sending shard info: {str(e)}")
        bot.send_message(chat_id, "⚠️ Failed to load shard data")

def register_shard_handlers(bot, admin_user_id):
    @bot.message_handler(func=lambda msg: msg.text == '💎 Shards')
    def shards_menu(message):
        from services.database import update_last_interaction
        update_last_interaction(message.from_user.id)
        send_shard_info(bot, message.chat.id, message.from_user.id)
    
    @bot.callback_query_handler(func=lambda call: call.data.startswith('shard:'))
    def handle_shard_callback(call):
        from services.database import update_last_interaction
        update_last_interaction(call.from_user.id)
        try:
            date_str = call.data.split(':')[1]
            target_date = date.fromisoformat(date_str)
            send_shard_info(bot, call.message.chat.id, call.from_user.id, target_date)
            
            # Edit original message
            try:
                bot.edit_message_reply_markup(
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=None
                )
            except:
                pass
        except Exception as e:
            logger.error(f"Error handling shard callback: {str(e)}")
            bot.answer_callback_query(call.id, "❌ Failed to load shard data")