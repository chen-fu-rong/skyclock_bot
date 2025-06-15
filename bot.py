import os
import logging
from datetime import datetime, timedelta, time as dt_time

from fastapi import FastAPI, Request
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (Application, CallbackContext, CallbackQueryHandler,
                          CommandHandler, ContextTypes, MessageHandler, filters)
from zoneinfo import ZoneInfo
import pytz
import asyncpg
import re

BOT_TOKEN = os.getenv("BOT_TOKEN") or "YOUR_BOT_TOKEN"
DATABASE_URL = os.getenv("DATABASE_URL") or "YOUR_DATABASE_URL"
WEBHOOK_URL = os.getenv("WEBHOOK_URL") or "YOUR_WEBHOOK_URL"
WEBHOOK_PATH = "/webhook"
PORT = int(os.getenv("PORT", 10000))

default_offset = "+0630"
TIMEZONE_MAP = {
    "Myanmar 🇲🇲 (MMT +06:30)": "+0630",
    "Other (manual input)": "manual"
}

logging.basicConfig(level=logging.INFO)

app = FastAPI()
bot_app = Application.builder().token(BOT_TOKEN).build()

user_timezones = {}  # fallback for in-memory use

# DB functions
async def init_db():
    bot_app.db = await asyncpg.connect(DATABASE_URL)
    await bot_app.db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            timezone TEXT
        )
    """)

async def set_timezone(user_id: int, offset: str):
    await bot_app.db.execute("""
        INSERT INTO users (user_id, timezone)
        VALUES ($1, $2)
        ON CONFLICT (user_id)
        DO UPDATE SET timezone = $2
    """, user_id, offset)

async def get_timezone(user_id: int) -> str:
    row = await bot_app.db.fetchrow("SELECT timezone FROM users WHERE user_id=$1", user_id)
    return row["timezone"] if row else default_offset

# --- Time Helpers ---
def get_now(offset):
    sign = 1 if offset.startswith('+') else -1
    hours = int(offset[1:3])
    minutes = int(offset[3:])
    return datetime.utcnow() + timedelta(hours=sign * hours, minutes=sign * minutes)

def next_event_time(event_minutes: int, offset: str, even_hour: bool = True):
    now = get_now(offset)
    hour = now.hour
    base = hour + 1 if now.minute >= event_minutes else hour
    if even_hour:
        base = base + (base % 2)  # make even
    else:
        base = base + (1 - base % 2)  # make odd
    next_time = now.replace(hour=base % 24, minute=event_minutes, second=0, microsecond=0)
    if next_time < now:
        next_time += timedelta(hours=2)
    return next_time

def format_event(name: str, time: datetime):
    now = time - timedelta(hours=0)
    delta = time - now
    hours, remainder = divmod(int(delta.total_seconds()), 3600)
    minutes = remainder // 60
    return (
        f"Next {name}:
"
        f"{time.strftime('%I:%M %p')} ({hours}h {minutes}m left)"
    )

# --- UI Keyboards ---
def main_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Wax 🌟", callback_data="wax")]
    ])

def timezone_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(k, callback_data=f"tz:{v}") for k, v in TIMEZONE_MAP.items()]
    ])

def wax_kb():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🍷 Grandma", callback_data="grandma"),
            InlineKeyboardButton("🍊 Geyser", callback_data="geyser"),
            InlineKeyboardButton("🌿 Turtle", callback_data="turtle")
        ],
        [InlineKeyboardButton("⬅️ Back", callback_data="back")]
    ])

# --- Handlers ---
async def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    offset = await get_timezone(user_id)
    if not offset:
        await update.message.reply_text(
            "Please choose your timezone:", reply_markup=timezone_kb()
        )
    else:
        await update.message.reply_text(
            "Main Menu:", reply_markup=main_menu_kb()
        )

async def timezone_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    choice = query.data.split(":")[1]

    if choice == "manual":
        await query.edit_message_text("Send your timezone offset in +HHMM or -HHMM format:")
        context.user_data["awaiting_manual"] = True
    else:
        await set_timezone(user_id, choice)
        await query.edit_message_text("Timezone set!", reply_markup=main_menu_kb())

async def manual_timezone_input(update: Update, context: CallbackContext):
    if context.user_data.get("awaiting_manual"):
        match = re.match(r"^[+-]\d{4}$", update.message.text.strip())
        if match:
            offset = update.message.text.strip()
            await set_timezone(update.effective_user.id, offset)
            await update.message.reply_text("Timezone set!", reply_markup=main_menu_kb())
            context.user_data["awaiting_manual"] = False
        else:
            await update.message.reply_text("Invalid format. Use +HHMM or -HHMM")

async def wax_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Choose an event:", reply_markup=wax_kb())

async def event_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    offset = await get_timezone(user_id)

    if query.data == "grandma":
        time = next_event_time(5, offset, even_hour=True)
        msg = format_event("Grandma", time)
    elif query.data == "geyser":
        time = next_event_time(35, offset, even_hour=False)
        msg = format_event("Geyser", time)
    elif query.data == "turtle":
        time = next_event_time(20, offset, even_hour=True)
        msg = format_event("Turtle", time)
    elif query.data == "back":
        await query.edit_message_text("Main Menu:", reply_markup=main_menu_kb())
        return
    else:
        msg = "Unknown event."

    await query.edit_message_text(msg, reply_markup=wax_kb())

# --- FastAPI integration ---
@app.on_event("startup")
async def on_startup():
    await init_db()
    await bot_app.bot.set_webhook(f"{WEBHOOK_URL}{WEBHOOK_PATH}")

@app.post(WEBHOOK_PATH)
async def telegram_webhook(req: Request):
    data = await req.json()
    update = Update.de_json(data, bot_app.bot)
    await bot_app.process_update(update)
    return "ok"

# --- Register Handlers ---
bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(CallbackQueryHandler(timezone_handler, pattern=r"tz:"))
bot_app.add_handler(CallbackQueryHandler(wax_handler, pattern="wax"))
bot_app.add_handler(CallbackQueryHandler(event_handler, pattern="^(grandma|geyser|turtle|back)$"))
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manual_timezone_input))
