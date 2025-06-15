import os
import logging
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Request
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    constants,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from sqlalchemy import Column, Integer, String, create_engine, select
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# --- Config ---
TOKEN = os.getenv("BOT_TOKEN")
RENDER = os.getenv("RENDER", "true") == "true"
DEFAULT_OFFSET = "+0630"

# --- DB Setup ---
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    tz_offset = Column(String)

Base.metadata.create_all(engine)

# --- Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- App Setup ---
app = FastAPI()

# --- Telegram App ---
telegram_app = Application.builder().token(TOKEN).build()

# --- Timezone Helper ---
def parse_offset(offset_str: str) -> timezone:
    try:
        sign = 1 if offset_str.startswith("+") else -1
        hours = int(offset_str[1:3])
        minutes = int(offset_str[3:5])
        return timezone(timedelta(hours=sign * hours, minutes=sign * minutes))
    except:
        return parse_offset(DEFAULT_OFFSET)

def get_user_offset(user_id: int) -> timezone:
    session = Session()
    user = session.get(User, user_id)
    session.close()
    if user:
        return parse_offset(user.tz_offset)
    return parse_offset(DEFAULT_OFFSET)

# --- Keyboard Buttons ---
def main_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🕯 Wax Events", callback_data="wax")],
    ])

def wax_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👵 Grandma", callback_data="grandma")],
        [InlineKeyboardButton("🌋 Geyser", callback_data="geyser")],
        [InlineKeyboardButton("🌿 Turtle", callback_data="turtle")],
        [InlineKeyboardButton("⬅ Back", callback_data="back")],
    ])

def timezone_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🇲🇲 Myanmar", callback_data="tz_mm")],
    ])

# --- Wax Event Logic ---
def get_next_event(now: datetime, minute: int, even: bool) -> datetime:
    base = now.replace(minute=0, second=0, microsecond=0)
    hour = base.hour + (1 if now.minute >= minute else 0)
    if even:
        hour += hour % 2
    else:
        hour += (hour + 1) % 2
    return base.replace(hour=hour, minute=minute)

def format_event(name: str, now: datetime, target: datetime) -> str:
    remaining = target - now
    return f"Next {name}:
🕒 {target.strftime('%I:%M %p')} ({remaining.seconds // 60} min left)"

def get_event_info(name: str, offset: timezone) -> str:
    now = datetime.now(offset)
    if name == "grandma":
        t = get_next_event(now, 5, even=True)
        emoji = "👵"
    elif name == "geyser":
        t = get_next_event(now, 35, even=False)
        emoji = "🌋"
    elif name == "turtle":
        t = get_next_event(now, 20, even=True)
        emoji = "🌿"
    else:
        return "Unknown event."
    return format_event(f"{emoji} {name.title()}", now, t)

# --- Telegram Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = Session()
    user = session.get(User, update.effective_user.id)
    if user:
        await update.message.reply_text("Welcome back!", reply_markup=main_menu_kb())
    else:
        await update.message.reply_text("Choose your timezone:", reply_markup=timezone_kb())
    session.close()

async def timezone_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "tz_mm":
        offset = DEFAULT_OFFSET
        session = Session()
        user = session.get(User, query.from_user.id)
        if user:
            user.tz_offset = offset
        else:
            user = User(id=query.from_user.id, tz_offset=offset)
            session.add(user)
        session.commit()
        session.close()
        await query.edit_message_text("Timezone set to Myanmar!", reply_markup=main_menu_kb())

async def manual_tz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    offset = update.message.text.strip()
    if len(offset) == 5 and (offset.startswith("+") or offset.startswith("-")):
        session = Session()
        user = session.get(User, update.effective_user.id)
        if user:
            user.tz_offset = offset
        else:
            user = User(id=update.effective_user.id, tz_offset=offset)
            session.add(user)
        session.commit()
        session.close()
        await update.message.reply_text("Timezone updated!", reply_markup=main_menu_kb())
    else:
        await update.message.reply_text("Invalid format. Use format like +0630 or -0400")

async def wax_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("Choose an event:", reply_markup=wax_kb())

async def event_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    event = query.data
    offset = get_user_offset(query.from_user.id)
    text = get_event_info(event, offset)
    await query.edit_message_text(text, reply_markup=wax_kb())

async def back_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("Main menu:", reply_markup=main_menu_kb())

# --- Register Handlers ---
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CallbackQueryHandler(timezone_button, pattern="^tz_"))
telegram_app.add_handler(CallbackQueryHandler(wax_handler, pattern="^wax$"))
telegram_app.add_handler(CallbackQueryHandler(back_handler, pattern="^back$"))
telegram_app.add_handler(CallbackQueryHandler(event_handler, pattern="^(grandma|geyser|turtle)$"))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manual_tz))

# --- FastAPI Telegram Webhook ---
@app.post("/webhook")
async def telegram_webhook(req: Request):
    data = await req.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return {"ok": True}

@app.get("/")
def root():
    return {"status": "ok"}
