import os
import logging
import asyncio
from fastapi import FastAPI, Request
from contextlib import asynccontextmanager
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application, CallbackContext, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters
)
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# === Configuration ===
TOKEN = os.getenv("BOT_TOKEN") or "your-telegram-token"
WEBHOOK_PATH = "/webhook"
PORT = int(os.getenv("PORT", 10000))
DB_URL = os.getenv("DATABASE_URL") or "sqlite:///users.db"

# === Logging ===
logging.basicConfig(level=logging.INFO)

# === Database Setup ===
Base = declarative_base()
engine = create_engine(DB_URL)
SessionLocal = sessionmaker(bind=engine)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    timezone = Column(String)

Base.metadata.create_all(bind=engine)

# === Bot Handlers ===
async def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    session = SessionLocal()
    user = session.query(User).filter(User.id == user_id).first()

    if user:
        await update.message.reply_text("You are already registered.")
    else:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🇲🇲 Myanmar", callback_data="tz:Asia/Yangon")],
        ])
        await update.message.reply_text(
            "Please choose your timezone:", reply_markup=keyboard
        )
    session.close()

async def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    if query.data.startswith("tz:"):
        tz = query.data.split(":", 1)[1]
        user_id = query.from_user.id
        session = SessionLocal()
        user = session.query(User).filter(User.id == user_id).first()
        if not user:
            user = User(id=user_id, timezone=tz)
            session.add(user)
        else:
            user.timezone = tz
        session.commit()
        session.close()
        await query.edit_message_text(f"Timezone set to: {tz}")

async def text_handler(update: Update, context: CallbackContext):
    tz = update.message.text.strip()
    if tz.startswith("UTC") or tz.startswith("+" or "-") or "/" in tz:
        user_id = update.effective_user.id
        session = SessionLocal()
        user = session.query(User).filter(User.id == user_id).first()
        if not user:
            user = User(id=user_id, timezone=tz)
            session.add(user)
        else:
            user.timezone = tz
        session.commit()
        session.close()
        await update.message.reply_text(f"Timezone set to: {tz}")
    else:
        await update.message.reply_text("Invalid timezone. Please use standard format like 'Asia/Yangon' or 'UTC+6:30'.")

# === Telegram Bot App ===
telegram_app = Application.builder().token(TOKEN).build()
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CallbackQueryHandler(button_handler))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

# === FastAPI Integration ===
@asynccontextmanager
async def lifespan(app: FastAPI):
    await telegram_app.initialize()
    await telegram_app.start()
    logging.info("Telegram bot started")
    yield
    await telegram_app.stop()
    await telegram_app.shutdown()
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
