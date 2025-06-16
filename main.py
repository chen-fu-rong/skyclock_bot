import os
import logging
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
from worker import init_db, get_user, update_user

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
        user_id = query.from_user.id
        data = query.data
        
        logger.info(f"Button pressed by {user_id}: {data}")
        
        if data == 'current_time':
            await query.edit_message_text(
                text="⏰ Current in-game time is: [time would be here]",
                parse_mode='HTML'
            )
        elif data == 'settings':
            keyboard = [
                [InlineKeyboardButton("🔙 Back", callback_data='back')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                text="⚙️ Settings Menu\n\nConfigure your preferences:",
                reply_markup=reply_markup
            )
        elif data == 'help':
            await query.edit_message_text(
                text="ℹ️ Help\n\n"
                "This bot helps track Sky: Children of the Light in-game time.\n\n"
                "Use the buttons to interact with me!",
                parse_mode='HTML'
            )
        elif data == 'back':
            keyboard = [
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
        if query:
            await query.answer("⚠️ Something went wrong. Please try again.", show_alert=True)

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
    application.add_handler(CallbackQueryHandler(button))  # This fixes the button issue
    
    # Webhook setup
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=f"{WEBHOOK_URL}/webhook",
        on_startup=on_startup
    )

if __name__ == "__main__":
    main()