import os
import re
import logging
from fastapi import FastAPI, Request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, ContextTypes,
    CommandHandler, CallbackQueryHandler,
    MessageHandler, filters
)

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN") or "YOUR_BOT_TOKEN"
WEBHOOK_PATH = "/webhook"
PORT = int(os.getenv("PORT", "10000"))

app = FastAPI()

# Store user timezones in memory: user_id -> tz string
user_timezones = {}

# Telegram application instance
telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()

def timezone_keyboard():
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Myanmar (UTC+06:30)", callback_data="timezone_+0630")]]
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome! Please select your timezone or type it in (format +HHMM or -HHMM):",
        reply_markup=timezone_keyboard()
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data.startswith("timezone_"):
        tz = query.data.split("_")[1]
        user_id = query.from_user.id
        user_timezones[user_id] = tz
        await query.edit_message_text(f"Timezone set to UTC{tz}")

async def manual_timezone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.strip()
    if re.fullmatch(r"[+-]\d{4}", text):
        user_timezones[user_id] = text
        await update.message.reply_text(f"Timezone set to UTC{text}")
    else:
        await update.message.reply_text(
            "Invalid format. Enter timezone as +HHMM or -HHMM, e.g. +0700"
        )

@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.update_queue.put(update)
    return {"ok": True}

@app.on_event("startup")
async def on_startup():
    logging.info("Bot started")

@app.on_event("shutdown")
async def on_shutdown():
    await telegram_app.shutdown()
    logging.info("Bot stopped")

# Register handlers
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CallbackQueryHandler(button_callback))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manual_timezone))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
