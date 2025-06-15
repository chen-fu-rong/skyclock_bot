import os
import asyncio
import logging
from datetime import datetime, timedelta

import psycopg2
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler,
    ContextTypes, MessageHandler, filters
)

# --- Configs ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_URL = os.getenv("DATABASE_URL")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.getenv("PORT", "10000"))
DEFAULT_TZ_OFFSET = "+06:30"

# --- Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- FastAPI ---
app = FastAPI()

# --- Telegram Bot ---
application = Application.builder().token(BOT_TOKEN).build()

# --- Database Setup ---
def init_db():
    with psycopg2.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    tz_offset TEXT
                )
            """)
            conn.commit()

def set_tz_offset(user_id, offset):
    with psycopg2.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO users (user_id, tz_offset)
                VALUES (%s, %s)
                ON CONFLICT (user_id) DO UPDATE SET tz_offset = EXCLUDED.tz_offset
            """, (user_id, offset))
            conn.commit()

def get_tz_offset(user_id):
    with psycopg2.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT tz_offset FROM users WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            return row[0] if row else DEFAULT_TZ_OFFSET

# --- Time Helpers ---
def get_local_time(offset_str):
    sign = 1 if offset_str[0] == '+' else -1
    hours, minutes = map(int, offset_str[1:].split(':'))
    return datetime.utcnow() + timedelta(hours=sign * hours, minutes=sign * minutes)

def get_next_event_time(now, base_minute):
    hour, minute = now.hour, now.minute
    if base_minute == 5:  # Grandma
        next_hour = hour if hour % 2 == 0 and minute < 5 else (hour + 1 if hour % 2 == 0 else hour + (2 - hour % 2))
    elif base_minute == 20:  # Turtle
        next_hour = hour if hour % 2 == 0 and minute < 20 else (hour + 1 if hour % 2 == 0 else hour + (2 - hour % 2))
    elif base_minute == 35:  # Geyser
        next_hour = hour if hour % 2 == 1 and minute < 35 else (hour + 1 if hour % 2 == 1 else hour + (2 - (hour + 1) % 2))
    else:
        return now
    next_event = now.replace(hour=next_hour % 24, minute=base_minute, second=0, microsecond=0)
    if next_event <= now:
        next_event += timedelta(hours=2)
    return next_event

def format_event(name: str, event_time: datetime, now: datetime) -> str:
    time_left = str(event_time - now).split('.')[0]
    return f"Next {name} ✨\n{event_time.strftime('%I:%M %p')} ({time_left} left)"

# --- Telegram Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🇲🇲 Myanmar Time (+06:30)", callback_data='set_myanmar')],
    ]
    await update.message.reply_text("Please send your timezone offset (e.g. `+06:30` or `-05:00`), or choose:", reply_markup=InlineKeyboardMarkup(keyboard))

async def set_myanmar_timezone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    set_tz_offset(user_id, "+06:30")
    await query.answer("Timezone set to Myanmar Time")
    await show_wax_menu(query)

async def handle_timezone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    offset = update.message.text.strip()
    if not offset.startswith(('+', '-')) or ':' not in offset:
        await update.message.reply_text("Invalid format. Please use +06:30 or -05:00")
        return
    set_tz_offset(user_id, offset)
    await update.message.reply_text("Timezone saved! Use /wax to check events.")

async def wax(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_wax_menu(update.message)

async def show_wax_menu(target):
    keyboard = [
        [InlineKeyboardButton("👵 Grandma", callback_data='wax_grandma')],
        [InlineKeyboardButton("💨 Geyser", callback_data='wax_geyser')],
        [InlineKeyboardButton("🐢 Turtle", callback_data='wax_turtle')]
    ]
    await target.reply_text("Choose a Wax Event:", reply_markup=InlineKeyboardMarkup(keyboard))

async def wax_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    offset = get_tz_offset(user_id)
    now = get_local_time(offset)

    if query.data == 'wax_grandma':
        event_time = get_next_event_time(now, 5)
        label = "Grandma"
    elif query.data == 'wax_geyser':
        event_time = get_next_event_time(now, 35)
        label = "Geyser"
    elif query.data == 'wax_turtle':
        event_time = get_next_event_time(now, 20)
        label = "Turtle"
    else:
        await query.edit_message_text("Unknown event.")
        return

    text = format_event(label, event_time, now)
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("⏰ Notify Me", callback_data=f'notify_{label.lower()}')],
        [InlineKeyboardButton("⬅ Back", callback_data='wax_back')]
    ]))

async def wax_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_wax_menu(update.callback_query)

# --- FastAPI Webhook ---
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.update_queue.put(update)
    return JSONResponse(content={"status": "ok"})

# --- Register Handlers ---
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("wax", wax))
application.add_handler(CallbackQueryHandler(set_myanmar_timezone, pattern="^set_myanmar$"))
application.add_handler(CallbackQueryHandler(wax_button, pattern="^wax_"))
application.add_handler(CallbackQueryHandler(wax_back, pattern="^wax_back$"))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_timezone))

# --- Init DB and Run App ---
if __name__ == "__main__":
    init_db()
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=WEBHOOK_URL
    )
