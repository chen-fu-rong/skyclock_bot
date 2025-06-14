import os
import asyncio
import logging
from datetime import datetime, timedelta

from fastapi import FastAPI, Request
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler, ContextTypes,
    MessageHandler, filters
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pytz
import asyncpg

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
PORT = int(os.getenv("PORT", "10000"))

logging.basicConfig(level=logging.INFO)

db_pool = None

async def init_db():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL)
    async with db_pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                timezone TEXT
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                event TEXT,
                event_time TEXT,
                minutes_before INTEGER,
                timezone TEXT,
                job_id TEXT UNIQUE
            );
        """)

async def get_user(user_id):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)

async def add_user(user_id, timezone):
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (user_id, timezone)
            VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE SET timezone = EXCLUDED.timezone
        """, user_id, timezone)

app = FastAPI()
telegram_app = Application.builder().token(BOT_TOKEN).build()
scheduler = AsyncIOScheduler()

EVENT_TIMES = {
    "grandma": ["02:05 AM", "04:05 AM", "06:05 AM", "08:05 AM", "10:05 AM", "12:05 PM", "02:05 PM", "04:05 PM", "06:05 PM", "08:05 PM", "10:05 PM", "12:05 AM"],
    "geyser": ["01:35 AM", "03:35 AM", "05:35 AM", "07:35 AM", "09:35 AM", "11:35 AM", "01:35 PM", "03:35 PM", "05:35 PM", "07:35 PM", "09:35 PM", "11:35 PM"],
    "turtle": ["02:20 AM", "04:20 AM", "06:20 AM", "08:20 AM", "10:20 AM", "12:20 PM", "02:20 PM", "04:20 PM", "06:20 PM", "08:20 PM", "10:20 PM", "12:20 AM"]
}

def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 Wax", callback_data="wax")],
        [InlineKeyboardButton("🧪 Shards", callback_data="shards")]
    ])

def wax_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👵 Grandma", callback_data="wax_grandma")],
        [InlineKeyboardButton("🌋 Geyser", callback_data="wax_geyser")],
        [InlineKeyboardButton("🐢 Turtle", callback_data="wax_turtle")],
        [InlineKeyboardButton("⬅️ Back", callback_data="back_main")]
    ])

def wax_event_keyboard(event_type: str, user_timezone: str):
    buttons = []
    times = EVENT_TIMES[event_type]
    for time_str in times:
        buttons.append([InlineKeyboardButton(time_str, callback_data=f"set_time_{event_type}_{time_str}")])
    return InlineKeyboardMarkup(buttons + [[InlineKeyboardButton("⬅️ Back", callback_data="wax")]])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = await get_user(user_id)
    if user is None:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🇲🇲 Myanmar", callback_data="tz_Myanmar")]
        ])
        await update.message.reply_text("👋 Welcome! Please choose your timezone:", reply_markup=keyboard)
    else:
        await update.message.reply_text("👋 What do you want to check?", reply_markup=main_menu_keyboard())

async def timezone_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    tz = "Asia/Yangon" if query.data == "tz_Myanmar" else None
    if tz:
        await add_user(user_id, tz)
        await query.edit_message_text("✅ Timezone set! Use /start to continue.")
    else:
        await query.edit_message_text("❌ Unsupported timezone.")

async def handle_wax(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Choose a Wax event:", reply_markup=wax_keyboard())

def get_next_event(event: str, user_timezone: str):
    tz = pytz.timezone(user_timezone)
    now = datetime.now(tz)
    today = now.date()
    for time_str in EVENT_TIMES[event]:
        dt = datetime.strptime(time_str, "%I:%M %p").replace(year=now.year, month=now.month, day=now.day)
        dt = tz.localize(dt)
        if dt > now:
            return dt, dt - now
    dt = datetime.strptime(EVENT_TIMES[event][0], "%I:%M %p")
    next_dt = tz.localize(datetime.combine(today + timedelta(days=1), dt.time()))
    return next_dt, next_dt - now

async def wax_event_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    event = query.data.split("_")[1]
    user = await get_user(user_id)
    if not user:
        await query.edit_message_text("❗ Please set timezone first using /start.")
        return
    next_time, remaining = get_next_event(event, user["timezone"])
    remaining_str = f"{remaining.seconds // 3600}h {(remaining.seconds % 3600) // 60}m"
    await query.edit_message_text(
        f"📅 Next {event.title()} event: <b>{next_time.strftime('%I:%M %p')}</b> (in {remaining_str})\n\n"
        f"🕒 Select time for reminder:",
        reply_markup=wax_event_keyboard(event, user["timezone"]),
        parse_mode=ParseMode.HTML
    )

async def set_time_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, event, time_str = query.data.split("_", 2)
    context.user_data["event_to_notify"] = event
    context.user_data["event_time"] = time_str
    context.user_data["stage"] = "awaiting_minutes"
    await query.edit_message_text(f"How many minutes before <b>{time_str}</b> would you like to be notified?", parse_mode=ParseMode.HTML)

async def handle_minutes_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        minutes = int(update.message.text.strip())
    except:
        await update.message.reply_text("❌ Please enter a valid number.")
        return
    event = context.user_data.get("event_to_notify")
    event_time = context.user_data.get("event_time")
    user = await get_user(user_id)
    await schedule_reminder(user_id, event, event_time, minutes, user["timezone"])
    await update.message.reply_text(f"✅ Reminder set for {event.title()} at {event_time}, {minutes} minutes before.")
    context.user_data.clear()

async def schedule_reminder(user_id, event, event_time_str, minutes_before, timezone_str):
    tz = pytz.timezone(timezone_str)
    now = datetime.now(tz)
    event_dt = datetime.strptime(event_time_str, "%I:%M %p").replace(year=now.year, month=now.month, day=now.day)
    event_dt = tz.localize(event_dt)
    if event_dt < now:
        event_dt += timedelta(days=1)
    reminder_time = event_dt - timedelta(minutes=minutes_before)
    job_id = f"{user_id}{event}{event_time_str.replace(':', '')}"

    async def send_reminder():
        await telegram_app.bot.send_message(chat_id=user_id, text=f"🔔 Reminder: {event.title()} is at {event_time_str}!")

    scheduler.add_job(send_reminder, 'date', run_date=reminder_time, id=job_id)

    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO reminders (user_id, event, event_time, minutes_before, timezone, job_id)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (job_id) DO NOTHING
        """, user_id, event, event_time_str, minutes_before, timezone_str, job_id)

# Remaining handlers (reminder list, cancel, webhook, etc.) are unchanged

# Register new handler
telegram_app.add_handler(CallbackQueryHandler(set_time_handler, pattern="^set_time_"))
telegram_app.add_handler(MessageHandler(filters.TEXT & filters.TEXT, lambda u, c: handle_minutes_reply(u, c) if c.user_data.get('stage') == 'awaiting_minutes' else None))

