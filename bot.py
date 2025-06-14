import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters,
    ContextTypes, CallbackQueryHandler
)

BOT_TOKEN = os.getenv("BOT_TOKEN") or "YOUR_BOT_TOKEN"
WEBHOOK_PATH = "/webhook"
PORT = int(os.getenv("PORT", "10000"))

logging.basicConfig(level=logging.INFO)

# Initialize your Telegram bot application here
telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()

# Lifespan context to replace deprecated on_event startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.info("Bot started")
    yield
    await telegram_app.shutdown()
    logging.info("Bot stopped")

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root():
    return {"message": "Bot is running!"}

@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.update_queue.put(update)
    return {"ok": True}

# Example start handler asking for timezone with Myanmar quick buttons
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("🕰 Myanmar (UTC+6:30)", callback_data="tz:Myanmar"),
        ],
        [
            InlineKeyboardButton("Other", callback_data="tz:Other"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Welcome! Please select your timezone or type it.",
        reply_markup=reply_markup,
    )

# Callback query handler for timezone selection buttons
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "tz:Myanmar":
        # Save user timezone as Myanmar +6:30
        # Save to your DB or dict here, e.g.:
        user_id = query.from_user.id
        context.user_data["timezone"] = "+0630"
        await query.edit_message_text(text="Timezone set to Myanmar (UTC+6:30). Thank you!")
    elif data == "tz:Other":
        await query.edit_message_text(text="Please type your timezone offset like +0700 or -0500.")

# Message handler to receive typed timezone offset
async def timezone_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tz_text = update.message.text.strip()
    if (len(tz_text) == 5 and (tz_text[0] == "+" or tz_text[0] == "-")
        and tz_text[1:].isdigit()):
        context.user_data["timezone"] = tz_text
        await update.message.reply_text(f"Timezone set to {tz_text}. Thank you!")
    else:
        await update.message.reply_text("Invalid format. Please type timezone like +0700 or -0500.")

telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CallbackQueryHandler(button_handler, pattern="^tz:"))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, timezone_text))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("bot:app", host="0.0.0.0", port=PORT, log_level="info")
