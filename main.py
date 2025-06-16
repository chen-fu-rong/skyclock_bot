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
WEBHOOK_SECRET = os.getenv('WEBHOOK_SECRET', 'your-secret-token-here')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    logger.info(f"User {user.id} started conversation")
    
    # Update user in database
    update_user(user.id, user.full_name)
    
    keyboard = [
        [InlineKeyboardButton("🇲🇲 Myanmar Time", callback_data='myanmar_time')],
        [InlineKeyboardButton("🕒 Game Time", callback_data='game_time')],
        [InlineKeyboardButton("⚙️ Settings", callback_data='settings')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_html(
        f"Hi {user.mention_html()}! I'm Sky Clock Bot ⏰\n\n"
        "What would you like to check?",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'myanmar_time':
        time = get_myanmar_time()
        await query.edit_message_text(
            text=f"🇲🇲 <b>Myanmar Time (UTC+6:30)</b>\n\n"
                 f"🕒 <b>{time.strftime('%H:%M %p')}</b>\n"
                 f"📅 {time.strftime('%A, %d %B %Y')}",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Refresh", callback_data='myanmar_time')],
                [InlineKeyboardButton("🔙 Main Menu", callback_data='main_menu')]
            ])
        )
    
    elif query.data == 'main_menu':
        await start(update, context)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Please use the buttons or /start command to interact with me!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Start", callback_data='main_menu')]
        ])
    )

async def set_webhook(app: Application):
    await app.bot.set_webhook(
        url=f"{WEBHOOK_URL}/webhook",
        secret_token=WEBHOOK_SECRET,
        allowed_updates=["message", "callback_query"]
    )
    logger.info("Webhook set up successfully")

def main():
    application = Application.builder().token(BOT_TOKEN).post_init(set_webhook).build()
    
    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Run bot
    if 'RENDER' in os.environ:
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            webhook_url=f"{WEBHOOK_URL}/webhook",
            secret_token=WEBHOOK_SECRET
        )
    else:
        application.run_polling()

if __name__ == "__main__":
    main()