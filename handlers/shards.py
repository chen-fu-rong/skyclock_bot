# handlers/shards.py
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from services import shard_service
from services.database import get_db
from utils.formatters import format_time
import logging
from datetime import date, datetime, timedelta

logger = logging.getLogger(__name__)

def notify_admin(message, admin_user_id):
    """Send important notifications to admin"""
    try:
        bot.send_message(admin_user_id, message)
    except Exception as e:
        logger.error(f"Failed to notify admin: {str(e)}")

def send_shard_info(bot, chat_id, user_id, target_date=None):
    user = get_db().get_user(user_id)
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

    # Admin commands
    @bot.message_handler(func=lambda msg: msg.text == '🔄 Update Shard Data' and str(msg.from_user.id) == admin_user_id)
    def handle_update_shard_data(message):
        from services.database import update_last_interaction
        update_last_interaction(message.from_user.id)
        bot.send_message(message.chat.id, "🔍 Validating shard data before update...")
        
        if shard_service.update_shard_data_with_validation():
            bot.send_message(message.chat.id, "✅ Shard data updated successfully!")
        else:
            bot.send_message(message.chat.id, "❌ Update failed! Check admin notifications")
    
    @bot.message_handler(func=lambda msg: msg.text == '✅ Validate Shard Data' and str(msg.from_user.id) == admin_user_id)
    def handle_validate_shard_data(message):
        from services.database import update_last_interaction
        update_last_interaction(message.from_user.id)
        msg = bot.send_message(
            message.chat.id,
            "Enter validation date range (format: YYYY-MM-DD to YYYY-MM-DD) or press /cancel:"
        )
        bot.register_next_step_handler(msg, process_validation_range, message.chat.id, admin_user_id)
    
    def process_validation_range(message, chat_id, admin_user_id):
        if message.text.strip().lower() == '/cancel':
            from handlers.admin import send_admin_menu
            send_admin_menu(bot, chat_id)
            return
            
        try:
            parts = message.text.split(" to ")
            start_date = datetime.strptime(parts[0].strip(), "%Y-%m-%d").date()
            end_date = datetime.strptime(parts[1].strip(), "%Y-%m-%d").date()
            
            if start_date > end_date:
                raise ValueError("Start date must be before end date")
                
            bot.send_message(
                chat_id,
                f"🔍 Validating shard data from {start_date} to {end_date}..."
            )
            
            is_valid, discrepancies = shard_service.validate_against_official(start_date, end_date)
            
            if is_valid:
                bot.send_message(
                    chat_id,
                    f"✅ All predictions match official data for {start_date} to {end_date}!"
                )
            else:
                report = f"❌ Found {len(discrepancies)} discrepancies:\n\n"
                for i, d in enumerate(discrepancies[:10]):  # Show first 10
                    report += f"{d['date']}:\n" + "\n".join(d['details']) + "\n\n"
                if len(discrepancies) > 10:
                    report += f"... and {len(discrepancies)-10} more\n"
                
                # Send summary to user
                bot.send_message(
                    chat_id,
                    f"❌ Found {len(discrepancies)} discrepancies. Details sent to admin."
                )
                
                # Send full report to admin
                notify_admin(report, admin_user_id)
                
        except Exception as e:
            bot.send_message(
                chat_id,
                f"❌ Validation failed: {str(e)}. Use format: YYYY-MM-DD to YYYY-MM-DD"
            )
        
        from handlers.admin import send_admin_menu
        send_admin_menu(bot, chat_id)