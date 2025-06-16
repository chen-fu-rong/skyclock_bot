import os
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)
from worker import init_db, get_user, update_user, get_myanmar_time


# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize database
init_db()

# Bot configuration
BOT_TOKEN = os.getenv('BOT_TOKEN')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')
PORT = int(os.getenv('PORT', 10000))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    # Check if user exists in DB
    db_user = get_user(user_id)
    if not db_user:
        update_user(user_id, user.full_name)
    
    keyboard = [
        [InlineKeyboardButton("🇲🇲 Myanmar Time", callback_data='myanmar_time')],
        [InlineKeyboardButton("🕒 Check Current Time", callback_data='current_time')],
        [InlineKeyboardButton("⚙️ Settings", callback_data='settings')],
        [InlineKeyboardButton("ℹ️ Help", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"Hi {user.mention_html()}! I'm Sky Clock Bot ⏰\n\n"
        "Choose an option below:",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()
        
        if query.data == 'myanmar_time':
            myanmar_time = get_myanmar_time()
            time_until_reset = calculate_reset_time()
            
            await query.edit_message_text(
                text=f"🇲🇲 <b>Myanmar Time (UTC+6:30)</b>\n\n"
                     f"🕒 <b>{myanmar_time.strftime('%H:%M %p')}</b>\n"
                     f"📅 {myanmar_time.strftime('%d %B %Y')}\n\n"
                     f"⏳ Next reset in: {time_until_reset}",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Refresh", callback_data='myanmar_time')],
                    [InlineKeyboardButton("🔙 Back", callback_data='back')]
                ])
            )
            
        elif query.data == 'current_time':
            await query.edit_message_text(
                text="⏰ Current in-game time is: [time would be here]",
                parse_mode='HTML'
            )
            
        elif query.data == 'settings':
            keyboard = [
                [InlineKeyboardButton("🔙 Back", callback_data='back')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                text="⚙️ Settings Menu\n\nConfigure your preferences:",
                reply_markup=reply_markup
            )
            
        elif query.data == 'help':
            await query.edit_message_text(
                text="ℹ️ <b>Help</b>\n\n"
                "This bot helps track Sky: Children of the Light in-game time.\n\n"
                "<b>Time Zones:</b>\n"
                "🇲🇲 Myanmar Time (UTC+6:30)\n\n"
                "<b>Commands:</b>\n"
                "/start - Show main menu\n"
                "/time - Check current time",
                parse_mode='HTML'
            )
            
        elif query.data == 'back':
            keyboard = [
                [InlineKeyboardButton("🇲🇲 Myanmar Time", callback_data='myanmar_time')],
                [InlineKeyboardButton("🕒 Check Current Time", callback_data='current_time')],
                [InlineKeyboardButton("⚙️ Settings", callback_data='settings')],
                [InlineKeyboardButton("ℹ️ Help", callback_data='help')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                text="Main Menu:",
                reply_markup=reply_markup
            )
            
    except Exception as e:
        logger.error(f"Button error: {str(e)}")
        await query.answer("⚠️ Something went wrong. Please try again.", show_alert=True)

def calculate_reset_time():
    now = datetime.utcnow()
    next_reset = now.replace(hour=0, minute=0, second=0) + timedelta(days=1)
    time_left = next_reset - now
    hours, remainder = divmod(time_left.seconds, 3600)
    minutes = remainder // 60
    return f"{hours}h {minutes}m"

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Please use the menu buttons or commands to interact with me!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Menu", callback_data='back')]
        ])
    )

async def on_startup(application):
    await application.bot.set_webhook(
        f"{WEBHOOK_URL}/webhook",
        allowed_updates=["message", "callback_query"]
    )
    logger.info(f"✅ Webhook set to {WEBHOOK_URL}/webhook")

def main():
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button))
    
    # Webhook setup
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=f"{WEBHOOK_URL}/webhook",
        on_startup=on_startup
    )

if __name__ == "__main__":
    main()