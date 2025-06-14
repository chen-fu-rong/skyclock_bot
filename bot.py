import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters,
    ContextTypes, CallbackQueryHandler
)

BOT_TOKEN = os.getenv("BOT_TOKEN") or "YOUR_BOT_TOKEN_HERE"
WEBHOOK_PATH = "/webhook"
PORT = int(os.getenv("PORT", "10000"))

logging.basicConfig(level=logging.INFO)

telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()

# /start command handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🕰 Myanmar (UTC+6:30)", callback_data="tz:Myanmar")],
        [InlineKeyboardButton("Other", callback_data="tz:Other")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Welcome! Please select your timezone or type it.",
        reply_markup=reply_markup,
    )

# Button callback handler
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "tz:Myanmar":
        context.user_data["timezone"] = "+0630"
        await query.edit_message_text(text="Timezone set to Myanmar (UTC+6:30). Thank you!")
    elif data == "tz:Other":
        await query.edit_message_text(text="Please type your timezone offset like +0700 or -0500.")

# Text message handler for typed timezone
async def timezone_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tz_text = update.message.text.strip()
    if (len(tz_text) == 5 and (tz_text[0] == "+" or tz_text[0] == "-")
        and tz_text[1:].isdigit()):
        context.user_data["timezone"] = tz_text
        await update.message.reply_text(f"Timezone set to {tz_text}. Thank you!")
    else:
        await update.message.reply_text("Invalid format. Please type timezone like +0700 or -0500.")

# Register handlers BEFORE starting the app
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CallbackQueryHandler(button_handler, pattern="^tz:"))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, timezone_text))

# FastAPI app and lifespan to start/stop telegram app
@asynccontextmanager
async def lifespan(app: FastAPI):
    await telegram_app.start()
    logging.info("Telegram bot started")
    yield
    await telegram_app.stop()
    logging.info("Telegram bot stopped")

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("bot:app", host="0.0.0.0", port=PORT, log_level="info")
