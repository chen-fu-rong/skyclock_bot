import os
import logging
from datetime import datetime, timedelta
from utils import convert_to_user_tz
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes
)
from database import Database
from navigation import NavigationManager
from menu_builder import build_menu_content, build_reminder_templates_menu
from time_input import get_time_input_keyboard, parse_time_input
from utils import validate_timezone
import pytz

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize database and navigation
DB_URL = os.getenv("DATABASE_URL")
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
db = Database(DB_URL)
nav_manager = NavigationManager(db)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        db.ensure_user_exists(user.id, user.username)
        menu = build_menu_content(nav_manager, db, user.id, "main_menu")
        await update.message.reply_text(**menu)
    except Exception as e:
        logger.error(f"Start command error: {e}")
        await update.message.reply_text("⚠️ Bot initialization error. Please try again later.")

async def handle_menu_navigation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    
    if data.startswith("menu_"):
        new_state = data.split("_", 1)[1] + "_menu"
        menu = build_menu_content(nav_manager, db, user_id, new_state)
        await query.edit_message_text(**menu)
    
    elif data == "nav_back":
        prev_state = nav_manager.pop_state(user_id)
        menu = build_menu_content(nav_manager, db, user_id, prev_state)
        await query.edit_message_text(**menu)
    
    elif data.startswith("toggle_"):
        event_type = data.split("_", 1)[1]
        db.toggle_subscription(user_id, event_type)
        current_state = nav_manager.current_state(user_id)
        menu = build_menu_content(nav_manager, db, user_id, current_state)
        await query.edit_message_text(**menu)
        await query.answer(f"Toggled {event_type} alerts")
    
    elif data == "create_reminder":
        context.user_data["reminder_state"] = "awaiting_time"
        await query.message.reply_text(
            "⌚ *Enter reminder time:*\n\n"
            "Examples:\n- 18:30\n- 6:30 PM\n- 14:45\n\n"
            "Use the keyboard below:",
            reply_markup=get_time_input_keyboard(),
            parse_mode="Markdown"
        )
    
    elif data == "reminder_templates":
        menu = build_reminder_templates_menu()
        await query.edit_message_text(**menu)
    
    elif data.startswith("template_"):
        template_type = data.split("_", 1)[1]
        # Store template in context for message
        templates = {
            "candle_run": "Daily candle run!",
            "geyser": "Geyser in Golden Wasteland!",
            "grandma": "Grandma's dinner time!",
            "reset": "Daily reset in 30 minutes!"
        }
        context.user_data["reminder_template"] = templates.get(template_type, "Reminder!")
        context.user_data["reminder_state"] = "awaiting_time"
        await query.message.reply_text(
            f"⌚ *Enter time for:* `{context.user_data['reminder_template']}`\n\n"
            "Use the keyboard below:",
            reply_markup=get_time_input_keyboard(),
            parse_mode="Markdown"
        )
    
    elif data.startswith("edit_"):
        reminder_id = int(data.split("_", 1)[1])
        menu = build_menu_content(nav_manager, db, user_id, f"edit_reminder_{reminder_id}")
        await query.edit_message_text(**menu)
    
    elif data.startswith("edit_time_"):
        reminder_id = int(data.split("_", 2)[2])
        context.user_data["reminder_state"] = "awaiting_time_edit"
        context.user_data["edit_reminder_id"] = reminder_id
        await query.message.reply_text(
            "⌚ *Enter new time for reminder:*",
            reply_markup=get_time_input_keyboard(),
            parse_mode="Markdown"
        )
    
    elif data.startswith("toggle_rec_"):
        reminder_id = int(data.split("_", 2)[2])
        new_state = db.toggle_reminder_recurring(reminder_id, user_id)
        if new_state is not None:
            status = "ON" if new_state else "OFF"
            await query.answer(f"Recurring {status}")
            current_state = nav_manager.current_state(user_id)
            menu = build_menu_content(nav_manager, db, user_id, current_state)
            await query.edit_message_text(**menu)
        else:
            await query.answer("Reminder not found")
    
    elif data.startswith("confirm_del_"):
        reminder_id = int(data.split("_", 2)[2])
        # Build confirmation menu
        content = "❌ *Delete this reminder?*"
        buttons = [
            [InlineKeyboardButton("✅ Yes", callback_data=f"delete_{reminder_id}")],
            [InlineKeyboardButton("❌ No", callback_data="nav_back")]
        ]
        await query.edit_message_text(
            text=content,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="Markdown"
        )
    
    elif data.startswith("delete_"):
        reminder_id = int(data.split("_", 1)[1])
        if db.delete_reminder(reminder_id, user_id):
            await query.answer("Reminder deleted")
            menu = build_menu_content(nav_manager, db, user_id, "reminders_menu")
            await query.edit_message_text(**menu)
        else:
            await query.answer("Delete failed")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    state = context.user_data.get("reminder_state")
    
    if state in ["awaiting_time", "awaiting_time_edit"]:
        parsed_time = parse_time_input(text)
        if parsed_time is None:
            await update.message.reply_text(
                "❌ Invalid time format. Please try again:",
                reply_markup=get_time_input_keyboard()
            )
            return
        
        # Store time and move to next state
        context.user_data["reminder_time"] = parsed_time
        context.user_data["reminder_state"] = "awaiting_message"
        
        # If we were editing, we already have the reminder id
        if state == "awaiting_time_edit":
            context.user_data["reminder_state"] = "awaiting_message_edit"
        
        template = context.user_data.get("reminder_template", "")
        prompt = "📝 *Enter reminder message:*" + (f"\n\nTemplate: `{template}`" if template else "")
        
        await update.message.reply_text(
            prompt,
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="Markdown"
        )
    
    elif state in ["awaiting_message", "awaiting_message_edit"]:
        message = text
        time_obj = context.user_data["reminder_time"]
        now = datetime.utcnow().replace(tzinfo=pytz.utc)
        # Create a datetime for today at the given time
        user_tz = db.get_timezone(user_id) or 'UTC'
        user_now = convert_to_user_tz(now, user_tz)
        
        # Combine date and time
        trigger_time = datetime.combine(user_now.date(), time_obj)
        # Convert to UTC
        trigger_utc = convert_to_user_tz(trigger_time, user_tz).astimezone(pytz.utc)
        
        # If the time has already passed today, set for tomorrow
        if trigger_utc < now:
            trigger_utc += timedelta(days=1)
        
        if state == "awaiting_message_edit":
            # Editing an existing reminder
            reminder_id = context.user_data["edit_reminder_id"]
            db.update_reminder_time(reminder_id, user_id, trigger_utc)
            db.update_reminder_message(reminder_id, user_id, message)
            response = "✅ Reminder updated!"
            # Cleanup
            del context.user_data["edit_reminder_id"]
        else:
            # New reminder
            db.create_reminder(user_id, trigger_utc, message)
            response = "✅ Reminder created!"
        
        # Cleanup common states
        for key in ["reminder_state", "reminder_time", "reminder_template"]:
            if key in context.user_data:
                del context.user_data[key]
        
        menu = build_menu_content(nav_manager, db, user_id, "reminders_menu")
        await update.message.reply_text(response, **menu)

async def set_timezone_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /settimezone command"""
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Usage: /settimezone <Timezone>\nExample: /settimezone Asia/Tokyo")
        return
    
    timezone_str = context.args[0]
    if validate_timezone(timezone_str):
        db.set_timezone(user_id, timezone_str)
        await update.message.reply_text(f"✅ Timezone set to {timezone_str}")
    else:
        await update.message.reply_text("❌ Invalid timezone. Use format: Continent/City")

def main() -> None:
    """Start the bot."""
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Register commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("settimezone", set_timezone_command))
    
    # Navigation and menu handlers
    application.add_handler(CallbackQueryHandler(handle_menu_navigation))
    
    # Message handler for reminders
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Start scheduler
    from scheduler import start_scheduler
    start_scheduler(application, db)
    
    # Run the bot
    application.run_polling()

if __name__ == "__main__":
    main()