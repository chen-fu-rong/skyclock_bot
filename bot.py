import os
import logging
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
from telegram.ext import defaults
from telegram.ext import PicklePersistence
from telegram.ext import MessageHandler, filters
import httpx
import asyncio
from contextlib import asynccontextmanager

TOKEN = os.getenv("BOT_TOKEN") or "YOUR_TELEGRAM_BOT_TOKEN"
WEBHOOK_PATH = "/webhook"
PORT = int(os.getenv("PORT", 10000))
BASE_URL = os.getenv("BASE_URL", "https://skyclock-bot.onrender.com")
WEBHOOK_URL = f"{BASE_URL}{WEBHOOK_PATH}"

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastAPI lifespan handler
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Telegram bot...")
    await application.initialize()
    await application.bot.set_webhook(WEBHOOK_URL)
    await application.start()
    yield
    logger.info("Shutting down Telegram bot...")
    await application.stop()
    await application.shutdown()

# FastAPI app
app = FastAPI(lifespan=lifespan)

@app.get("/")
async def home():
    return {"status": "SkyClock bot is running!"}

@app.post(WEBHOOK_PATH)
async def webhook_handler(request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return {"ok": True}

# Define command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello! I am your SkyClock bot.")

# Build application
application = Application.builder().token(TOKEN).build()

# Add handlers to application
application.add_handler(CommandHandler("start", start))

# Entrypoint for local or Render
if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting server on port: {PORT}")
    uvicorn.run("bot:app", host="0.0.0.0", port=PORT, reload=False)
