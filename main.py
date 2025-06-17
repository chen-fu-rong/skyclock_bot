import os
import logging
import pytz
import psycopg2
import urllib.parse
from datetime import datetime, time, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters
)

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
TIMEZONE, EVENT_NOTIFICATION, TIME_FORMAT = range(3)

# ... [Database functions - same as before] ...

# ... [Time functions - same as before] ...

# ... [Event calculations - same as before] ...

# Bot command handlers - MOVED ABOVE THE main() FUNCTION
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command with timezone setup"""
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    # Create user in database if not exists
    create_user(user.id, chat_id)
    
    # Greet with first name
    greeting = f"✨ Welcome to Sky: Children of the Light Reminder Bot, {user.first_name}! ✨"
    
    # Ask for timezone
    keyboard = [
        [InlineKeyboardButton("🇲🇲 Myanmar Time (Asia/Yangon)", callback_data='tz_myanmar')],
        [InlineKeyboardButton("⌨ Enter Timezone Manually", callback_data='tz_manual')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"{greeting}\n\n"
        "⏰ Please select your timezone:",
        reply_markup=reply_markup
    )
    
    return TIMEZONE

async def handle_timezone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle timezone selection"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    if data == 'tz_myanmar':
        # Set to Myanmar time
        update_user_timezone(user_id, 'Asia/Yangon')
        await query.edit_message_text("✅ Timezone set to Myanmar Time (Asia/Yangon)")
        await show_main_menu(update, context)
        return ConversationHandler.END
    elif data == 'tz_manual':
        await query.edit_message_text(
            "🌍 Please enter your timezone in the format 'Continent/City' (e.g., 'America/New_York', 'Europe/London').\n\n"
            "You can find your timezone here: https://kevinnovak.github.io/Time-Zone-Picker/"
        )
        return TIMEZONE

async def handle_manual_timezone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle manual timezone input"""
    user_id = update.message.from_user.id
    timezone_str = update.message.text.strip()
    
    try:
        # Validate timezone
        pytz.timezone(timezone_str)
        update_user_timezone(user_id, timezone_str)
        await update.message.reply_text(f"✅ Timezone set to {timezone_str}")
        await show_main_menu(update, context)
    except pytz.UnknownTimeZoneError:
        await update.message.reply_text(
            "❌ Invalid timezone. Please enter a valid timezone in the format 'Continent/City'.\n\n"
            "Example: 'Asia/Yangon', 'America/Los_Angeles'"
        )
        return TIMEZONE
    
    return ConversationHandler.END

async def show_main_menu(update, context):
    """Show the main menu"""
    keyboard = [
        [InlineKeyboardButton("🕰 Sky Clock", callback_data='menu_clock')],
        [InlineKeyboardButton("🕯 Wax Events", callback_data='menu_wax')],
        [InlineKeyboardButton("💎 Shards", callback_data='menu_shards')],
        [InlineKeyboardButton("⚙️ Settings", callback_data='menu_settings')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Edit existing message or send new one
    if update.callback_query:
        await update.callback_query.edit_message_text(
            "🏠 Main Menu:",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "🏠 Main Menu:",
            reply_markup=reply_markup
        )

async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle main menu selections"""
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == 'menu_clock':
        await show_sky_clock(query)
    elif data == 'menu_wax':
        await show_wax_menu(query)
    elif data == 'menu_shards':
        await show_shards_info(query)
    elif data == 'menu_settings':
        await show_settings_menu(query)
    elif data == 'menu_back':
        await show_main_menu(update, context)

async def show_sky_clock(query):
    """Show Sky Clock information"""
    sky_time = get_sky_time()
    user = get_user(query.from_user.id)
    
    if user:
        user_time = convert_to_user_time(sky_time, user[2])
        formatted_time = format_time(user_time, user[3])
        
        message = (
            f"🕰 Current Sky Time: {sky_time.strftime('%H:%M')} (America/Los_Angeles)\n"
            f"⏱ Your Local Time: {formatted_time}"
        )
    else:
        message = "🕰 Current Sky Time: " + sky_time.strftime('%H:%M') + " (America/Los_Angeles)"
    
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data='menu_back')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(message, reply_markup=reply_markup)

async def show_wax_menu(query):
    """Show wax events menu"""
    keyboard = [
        [InlineKeyboardButton("👵 Grandma", callback_data='wax_grandma')],
        [InlineKeyboardButton("🦀 Geyser", callback_data='wax_geyser')],
        [InlineKeyboardButton("🐢 Turtle", callback_data='wax_turtle')],
        [InlineKeyboardButton("🔙 Back", callback_data='menu_back')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🕯 Wax Events:",
        reply_markup=reply_markup
    )

async def handle_wax_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle wax event selection"""
    query = update.callback_query
    await query.answer()
    data = query.data
    
    user_id = query.from_user.id
    user = get_user(user_id)
    
    if not user:
        await query.edit_message_text("Please use /start to initialize your settings")
        return
    
    # Get user's current time
    user_tz = pytz.timezone(user[2])
    user_time = datetime.now(user_tz)
    
    # Calculate event time based on selection
    if data == 'wax_grandma':
        event_type = "Grandma"
        event_time = calculate_grandma_time(user_time)
    elif data == 'wax_geyser':
        event_type = "Geyser"
        event_time = calculate_geyser_time(user_time)
    elif data == 'wax_turtle':
        event_type = "Turtle"
        event_time = calculate_turtle_time(user_time)
    else:
        return
    
    # Format times
    formatted_event_time = format_time(event_time, user[3])
    time_until = format_time_difference(event_time, datetime.now(pytz.utc))
    
    # Create message
    message = (
        f"⏰ Next {event_type} Event:\n"
        f"🕒 Time: {formatted_event_time} (your time)\n"
        f"⏳ Starts in: {time_until}"
    )
    
    # Create keyboard
    keyboard = [
        [InlineKeyboardButton(f"🔔 Get Notification for {event_type}", callback_data=f'notify_{event_type.lower()}')],
        [InlineKeyboardButton("🔙 Back", callback_data='menu_wax')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(message, reply_markup=reply_markup)

async def handle_notification_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle notification request"""
    query = update.callback_query
    await query.answer()
    data = query.data
    
    # Extract event type
    event_type = data.split('_')[1].capitalize()
    context.user_data['event_type'] = event_type
    
    # Ask for notification minutes
    await query.edit_message_text(
        f"🔔 How many minutes before the {event_type} event would you like to be notified?\n\n"
        "Please enter a number (e.g., 5, 10, 15):"
    )
    
    return EVENT_NOTIFICATION

async def handle_notification_minutes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle notification minutes input"""
    user_id = update.message.from_user.id
    chat_id = update.message.chat.id
    text = update.message.text.strip()
    
    try:
        minutes = int(text)
        if minutes <= 0 or minutes > 60:
            raise ValueError("Invalid minutes")
        
        event_type = context.user_data.get('event_type', 'Grandma')
        
        # Create event notification
        create_event(user_id, chat_id, event_type.lower(), minutes)
        
        await update.message.reply_text(
            f"✅ Notification set! You'll be notified {minutes} minutes before the {event_type} event."
        )
        await show_main_menu(update, context)
    except ValueError:
        await update.message.reply_text(
            "❌ Please enter a valid number between 1 and 60."
        )
        return EVENT_NOTIFICATION
    
    return ConversationHandler.END

async def show_settings_menu(query):
    """Show settings menu"""
    user_id = query.from_user.id
    user = get_user(user_id)
    
    if not user:
        await query.edit_message_text("Please use /start to initialize your settings")
        return
    
    # Get user's events
    events = get_user_events(user_id)
    
    # Create message
    message = "⚙️ Settings:\n\n"
    message += f"⏱ Time Format: {'12-hour' if user[3] == '12h' else '24-hour'}\n"
    message += f"🌍 Timezone: {user[2]}\n\n"
    message += "🔔 Notifications:\n"
    
    if events:
        for event in events:
            status = "✅ ON" if event[4] else "❌ OFF"
            message += f"- {event[2].capitalize()}: {event[3]} mins before ({status})\n"
    else:
        message += "No notifications set\n"
    
    # Create keyboard
    keyboard = [
        [InlineKeyboardButton("🔔 Manage Notifications", callback_data='settings_notifications')],
        [InlineKeyboardButton("🕒 Change Time Format", callback_data='settings_time_format')],
        [InlineKeyboardButton("🌍 Change Timezone", callback_data='settings_timezone')],
        [InlineKeyboardButton("🔙 Back", callback_data='menu_back')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(message, reply_markup=reply_markup)

async def show_notification_settings(query):
    """Show notification settings"""
    user_id = query.from_user.id
    events = get_user_events(user_id)
    
    if not events:
        await query.edit_message_text("You have no notifications set.")
        return
    
    # Create keyboard
    keyboard = []
    for event in events:
        event_id, user_id, event_type, minutes, is_active, created_at = event
        status = "Disable" if is_active else "Enable"
        text = f"{'✅' if is_active else '❌'} {event_type.capitalize()} ({minutes} mins)"
        keyboard.append([InlineKeyboardButton(text, callback_data=f'toggle_{event_id}_{not is_active}')])
    
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='menu_settings')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🔔 Notification Settings:\nToggle notifications on/off:",
        reply_markup=reply_markup
    )

async def handle_notification_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle notification toggle"""
    query = update.callback_query
    await query.answer()
    data = query.data
    
    # Extract event ID and new status
    parts = data.split('_')
    event_id = int(parts[1])
    new_status = parts[2] == 'True'
    
    # Update event status
    toggle_event(event_id, new_status)
    
    # Refresh notification settings
    await show_notification_settings(query)

async def show_time_format_settings(query):
    """Show time format settings"""
    user_id = query.from_user.id
    user = get_user(user_id)
    
    if not user:
        await query.edit_message_text("Please use /start to initialize your settings")
        return
    
    # Create keyboard
    keyboard = [
        [InlineKeyboardButton("🕒 12-hour format", callback_data='timeformat_12h')],
        [InlineKeyboardButton("⏰ 24-hour format", callback_data='timeformat_24h')],
        [InlineKeyboardButton("🔙 Back", callback_data='menu_settings')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🕒 Select your preferred time format:",
        reply_markup=reply_markup
    )

async def handle_time_format(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle time format selection"""
    query = update.callback_query
    await query.answer()
    data = query.data
    
    user_id = query.from_user.id
    time_format = data.split('_')[1]
    
    # Update user's time format
    update_user_time_format(user_id, time_format)
    
    await query.edit_message_text(
        f"✅ Time format set to {'12-hour' if time_format == '12h' else '24-hour'}"
    )
    await show_settings_menu(query)

async def show_shards_info(query):
    """Show shards information"""
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data='menu_back')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "💎 Shard Events:\n\n"
        "Shards appear randomly throughout the realms. Check the official "
        "Sky Discord or Reddit for current locations and times!",
        reply_markup=reply_markup
    )

# Background tasks
async def check_reminders(context: ContextTypes.DEFAULT_TYPE):
    """Check and send due reminders"""
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            current_time = datetime.now(pytz.utc)
            
            # Get active reminders
            cur.execute('''
                SELECT id, user_id, event_type, notify_minutes, chat_id 
                FROM events
                WHERE is_active = TRUE
            ''')
            events = cur.fetchall()
            
            # Check each event
            for event in events:
                event_id, user_id, event_type, notify_minutes, chat_id = event
                
                # Get user's timezone
                user = get_user(user_id)
                if not user:
                    continue
                    
                user_tz = pytz.timezone(user[2])
                user_time = datetime.now(user_tz)
                
                # Calculate next event time
                if event_type == 'grandma':
                    event_time = calculate_grandma_time(user_time)
                elif event_type == 'geyser':
                    event_time = calculate_geyser_time(user_time)
                elif event_type == 'turtle':
                    event_time = calculate_turtle_time(user_time)
                else:
                    continue
                
                # Calculate notification time
                notification_time = event_time - timedelta(minutes=notify_minutes)
                
                # Check if it's time to notify
                if notification_time <= current_time <= event_time:
                    try:
                        # Format event time
                        formatted_time = format_time(event_time.astimezone(user_tz), user[3])
                        
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=f"🔔 Reminder: {event_type.capitalize()} event starts at {formatted_time}!"
                        )
                    except Exception as e:
                        logger.warning(f"Failed to send reminder to {chat_id}: {str(e)}")
    except Exception as e:
        logger.error(f"Reminder check failed: {str(e)}")

def main() -> None:
    """Start the bot"""
    # Initialize database
    init_db()
    
    # Create Telegram application
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_TOKEN environment variable not set")
    
    # Get Render environment details
    render_external_url = os.getenv('RENDER_EXTERNAL_URL')
    port = os.getenv('PORT', '8443')
    
    application = Application.builder().token(token).build()
    
    # Conversation handler for timezone setup
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            TIMEZONE: [
                CallbackQueryHandler(handle_timezone, pattern='^tz_'),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_manual_timezone)
            ],
            EVENT_NOTIFICATION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_notification_minutes)
            ]
        },
        fallbacks=[CommandHandler("start", start)]
    )
    
    # Register handlers
    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(handle_menu, pattern='^menu_'))
    application.add_handler(CallbackQueryHandler(handle_wax_event, pattern='^wax_'))
    application.add_handler(CallbackQueryHandler(handle_notification_request, pattern='^notify_'))
    application.add_handler(CallbackQueryHandler(show_settings_menu, pattern='^settings_notifications$'))
    application.add_handler(CallbackQueryHandler(show_notification_settings, pattern='^settings_notifications$'))
    application.add_handler(CallbackQueryHandler(handle_notification_toggle, pattern='^toggle_'))
    application.add_handler(CallbackQueryHandler(show_time_format_settings, pattern='^settings_time_format$'))
    application.add_handler(CallbackQueryHandler(handle_time_format, pattern='^timeformat_'))
    
    # Schedule background jobs
    job_queue = application.job_queue
    job_queue.run_repeating(check_reminders, interval=60, first=10)
    
    # Handle Render deployment
    if render_external_url:
        # Running on Render - use webhook
        webhook_url = f'{render_external_url}/{token}'
        application.run_webhook(
            listen="0.0.0.0",
            port=int(port),
            url_path=token,
            webhook_url=webhook_url
        )
        logger.info(f"Using webhook: {webhook_url}")
    else:
        # Running locally - use polling
        application.run_polling(drop_pending_updates=True)
        logger.info("Using polling method")

if __name__ == "__main__":
    main()