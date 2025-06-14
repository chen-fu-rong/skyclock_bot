import os
import logging
import asyncio
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # e.g. "https://your.domain.com/webhook"

app = FastAPI()

# Build your Telegram Application
application = Application.builder().token(BOT_TOKEN).build()

# Add handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello! Bot is running.")

application.add_handler(CommandHandler("start", start))

@app.on_event("startup")
async def on_startup():
    logger.info("Starting Telegram Application")
    await application.initialize()
    # Set webhook to your URL + path
    if WEBHOOK_URL:
        await application.bot.set_webhook(WEBHOOK_URL)
        logger.info(f"Webhook set to {WEBHOOK_URL}")
    await application.start()
    logger.info("Telegram Application started")

@app.on_event("shutdown")
async def on_shutdown():
    logger.info("Stopping Telegram Application")
    await application.stop()
    await application.shutdown()
    logger.info("Telegram Application stopped")

@app.post(WEBHOOK_PATH)
async def webhook(request: Request):
    json_data = await request.json()
    update = Update.de_json(json_data, application.bot)
    await application.process_update(update)
    return {"ok": True}

@app.get("/")
async def root():
    return {"message": "Bot is alive"}

# To run: uvicorn bot:app --host 0.0.0.0 --port 10000
