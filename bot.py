import os
import json
import asyncio
import logging
from datetime import datetime, timedelta

import pytz
import psycopg2
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          ContextTypes, MessageHandler, filters)

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Telegram Bot Token
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Timezone offset fallback
DEFAULT_TZ_OFFSET = "+06:30"

# PostgreSQL connection (for Render)
DB_URL = os.getenv("DATABASE_URL")

# FastAPI app
app = FastAPI()

# Init bot
application = Application.builder().token(BOT_TOKEN).build()

# Create table if not exists
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

# Get timezone offset for user
def get_tz_offset(user_id):
    with psycopg2.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT tz_offset FROM users WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            return row[0] if row else DEFAULT_TZ_OFFSET

# Save timezone offset
def set_tz_offset(user_id, offset):
    with psycopg2.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO users (user_id, tz_offset)
                VALUES (%s, %s)
                ON CONFLICT (user_id) DO UPDATE SET tz_offset = EXCLUDED.tz_offset
            """, (user_id, offset))
            conn.commit()

# Time helpers
def get_local_time(offset_str):
    sign = 1 if offset_str[0] == '+' else -1
    hours, minutes = map(int, offset_str[1:].split(':'))
    return datetime.utcnow() + timedelta(hours=sign*hours, minutes=sign*minutes)

def get_next_event_time(base_minute):
    now = datetime.utcnow()
    next_time = now.replace(second=0, microsecond=0)
    next_time += timedelta(minutes=1)  # ensure future
    next_time = next_time.replace(minute=base_minute)
    if next_time < now:
        next_time += timedelta(hours=2)
    else:
        hour_mod = next_time.hour % 2
        if base_minute == 5 and hour_mod != 0:
            next_time += timedelta(hours=1)
        elif base_minute in [20, 35] and hour_mod != 1:
            next_time += timedelta(hours=1)
    return next_time

def format_event(name: str, event_time: datetime, now: datetime) -> str:
    time_left = str(event_time - now).split('.')[0]
    return (
        f"Next {name} \u2728\n"
        f"{event_time.strftime('%I:%M %p')} ({time_left} left)"
    )

# Command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Please send your timezone offset (e.g. +06:30 or -05:00)")

async def handle_timezone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    offset = update.message.text.strip()
    if not offset.startswith(('+', '-')) or ':' not in offset:
        await update.message.reply_text("Invalid format. Please send in format +06:30 or -05:00")
        return
    set_tz_offset(user_id, offset)
    await update.message.reply_text("Timezone saved! Use /wax to check events.")

async def wax(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("\U0001F475 Grandma", callback_data='wax_grandma')],
        [InlineKeyboardButton("\U0001F4A8 Geyser", callback_data='wax_geyser')],
        [InlineKeyboardButton("\U0001F422 Turtle", callback_data='wax_turtle')]
    ]
    await update.message.reply_text("Choose a Wax Event:", reply_markup=InlineKeyboardMarkup(keyboard))

async def wax_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    offset = get_tz_offset(user_id)
    now = get_local_time(offset)

    if query.data == 'wax_grandma':
        event_time = get_next_event_time(5)
        label = "Grandma"
    elif query.data == 'wax_geyser':
        event_time = get_next_event_time(35)
        label = "Geyser"
    elif query.data == 'wax_turtle':
        event_time = get_next_event_time(20)
        label = "Turtle"
    else:
        await query.edit_message_text("Unknown event.")
        return

    local_event_time = event_time + (now - datetime.utcnow())
    text = format_event(label, local_event_time, now)
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("\u23F0 Notify Me", callback_data=f'notify_{label.lower()}')],
        [InlineKeyboardButton("\u2B05 Back", callback_data='wax_back')]
    ]))

async def wax_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await wax(update, context)

# FastAPI webhook endpoint
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.update_queue.put(update)
    return JSONResponse(content={"status": "ok"})

# Register handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("wax", wax))
application.add_handler(CallbackQueryHandler(wax_button, pattern="^wax_"))
application.add_handler(CallbackQueryHandler(wax_back, pattern="^wax_back"))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_timezone))

# Init DB and run
if __name__ == "__main__":
    init_db()
    application.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 10000)),
        webhook_url=os.environ.get("WEBHOOK_URL")
    )