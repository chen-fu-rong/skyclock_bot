import os
import logging
import json
import pytz
from datetime import datetime, timedelta
from fastapi import FastAPI, Request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler, Defaults
import httpx
import asyncio

BOT_TOKEN = os.getenv("BOT_TOKEN") or "YOUR_BOT_TOKEN"
WEBHOOK_PATH = "/webhook"
PORT = int(os.getenv("PORT", "10000"))
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "https://skyclock-bot.onrender.com")
WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}"

defaults = Defaults(parse_mode='HTML')
app = FastAPI()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot")

application = ApplicationBuilder().token(BOT_TOKEN).defaults(defaults).build()

# /start handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome to Sky Clock Bot!\nPlease share your timezone offset in hours (e.g., +6.5 or -5):")

# /wax handler
async def wax(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🧓 Grandma", callback_data="wax_grandma")],
        [InlineKeyboardButton("🌋 Geyser", callback_data="wax_geyser")],
        [InlineKeyboardButton("🐢 Turtle", callback_data="wax_turtle")],
    ]
    await update.message.reply_text("Choose a Wax event:", reply_markup=InlineKeyboardMarkup(keyboard))

# Button callbacks
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    now = datetime.utcnow() + timedelta(hours=6.5)  # default UTC+6:30
    current_hour = now.hour
    minutes = now.minute

    if query.data == "wax_grandma":
        next_hour = (current_hour + (2 - current_hour % 2)) % 24
        event_time = now.replace(hour=next_hour, minute=5, second=0, microsecond=0)
        if event_time < now:
            event_time += timedelta(hours=2)
        diff = event_time - now
        await query.edit_message_text(f"🧓 Next Grandma: {event_time.strftime('%H:%M')}\nTime left: {diff}")

    elif query.data == "wax_geyser":
        next_hour = (current_hour + 1 if current_hour % 2 == 0 else current_hour) % 24
        event_time = now.replace(hour=next_hour, minute=35, second=0, microsecond=0)
        if event_time < now:
            event_time += timedelta(hours=2)
        diff = event_time - now
        await query.edit_message_text(f"🌋 Next Geyser: {event_time.strftime('%H:%M')}\nTime left: {diff}")

    elif query.data == "wax_turtle":
        next_hour = (current_hour + (2 - current_hour % 2)) % 24
        event_time = now.replace(hour=next_hour, minute=20, second=0, microsecond=0)
        if event_time < now:
            event_time += timedelta(hours=2)
        diff = event_time - now
        await query.edit_message_text(f"🐢 Next Turtle: {event_time.strftime('%H:%M')}\nTime left: {diff}")

application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("wax", wax))
application.add_handler(CallbackQueryHandler(button))

@app.on_event("startup")
async def on_startup():
    logger.info(f"Setting webhook to {WEBHOOK_URL}")
    async with httpx.AsyncClient() as client:
        await client.post(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook", params={"url": WEBHOOK_URL})
    logger.info("Telegram bot started.")

@app.on_event("shutdown")
async def on_shutdown():
    await application.shutdown()

@app.post(WEBHOOK_PATH)
async def webhook_handler(request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.initialize()
    await application.process_update(update)
    return "ok"

@app.get("/")
async def root():
    return {"status": "OK"}

if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting server on port: {PORT}")
    uvicorn.run("bot:app", host="0.0.0.0", port=PORT, reload=False)
