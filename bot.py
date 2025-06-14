import os
import logging
from datetime import datetime, timedelta
import pytz
import asyncpg

from fastapi import FastAPI, Request
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# --- Setup ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
PORT = int(os.getenv("PORT", "10000"))

logging.basicConfig(level=logging.INFO)

app = FastAPI()
telegram_app = Application.builder().token(BOT_TOKEN).build()
scheduler = AsyncIOScheduler()

# --- DB initialization ---
db_pool = None

async def init_db():
    global db_pool
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL not defined!")
    logging.info("Connecting to DB...")
    db_pool = await asyncpg.create_pool(DATABASE_URL)
    async with db_pool.acquire() as c:
        await c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                timezone TEXT
            );
        """)
        await c.execute("""
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
    logging.info("DB setup complete")

async def get_user(user_id):
    async with db_pool.acquire() as c:
        return await c.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)

async def add_user(user_id, timezone):
    async with db_pool.acquire() as c:
        await c.execute("""
           INSERT INTO users(user_id, timezone)
           VALUES($1, $2)
           ON CONFLICT(user_id) DO UPDATE SET timezone = EXCLUDED.timezone
        """, user_id, timezone)

# --- Event times config ---
EVENT_TIMES = {
    "grandma": ["02:05 AM","04:05 AM", "06:05 AM", "08:05 AM", "10:05 AM", "12:05 PM",
                "02:05 PM", "04:05 PM", "06:05 PM", "08:05 PM", "10:05 PM", "12:05 AM"],
    "geyser": ["01:35 AM","03:35 AM","05:35 AM","07:35 AM","09:35 AM","11:35 AM",
               "01:35 PM","03:35 PM","05:35 PM","07:35 PM","09:35 PM","11:35 PM"],
    "turtle": ["02:20 AM","04:20 AM","06:20 AM","08:20 AM","10:20 AM","12:20 PM",
               "02:20 PM","04:20 PM","06:20 PM","08:20 PM","10:20 PM","12:20 AM"]
}

def next_event_info(event, tz_str):
    tz = pytz.timezone(tz_str)
    now = datetime.now(tz)
    for t in EVENT_TIMES[event]:
        dt = datetime.strptime(t, "%I:%M %p").replace(
            year=now.year, month=now.month, day=now.day)
        dt = tz.localize(dt)
        if dt <= now:
            dt += timedelta(days=1)
        if dt > now:
            delta = dt - now
            return dt, f"{delta.seconds//3600}h {(delta.seconds%3600)//60}m"
    # fallback
    return None, None

# --- Keyboards ---
def main_menu_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("📦 Wax", callback_data="wax")]])

def wax_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👵 Grandma", callback_data="wax_grandma")],
        [InlineKeyboardButton("🌋 Geyser", callback_data="wax_geyser")],
        [InlineKeyboardButton("🐢 Turtle", callback_data="wax_turtle")],
    ])

def event_times_kb(event):
    buttons = [[InlineKeyboardButton(t, callback_data=f"choose_{event}_{t}")] for t in EVENT_TIMES[event]]
    buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="wax")])
    return InlineKeyboardMarkup(buttons)

# --- Handlers ---
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = await get_user(update.effective_user.id)
    if not user:
        await update.message.reply_text("⏰ Please set your timezone first.")
    else:
        await update.message.reply_text("Select Wax event:", reply_markup=main_menu_kb())

async def wax_handler(update: Update, ctx):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("Choose an event:", reply_markup=wax_kb())

async def wax_event_handler(update: Update, ctx):
    q = update.callback_query
    await q.answer()
    event = q.data.split("_")[1]
    user = await get_user(q.from_user.id)
    if not user:
        await q.edit_message_text("❗ Set timezone first.")
        return
    dt, rem = next_event_info(event, user["timezone"])
    if not dt:
        await q.edit_message_text("No upcoming time found.")
        return
    logging.info(f"User picks {event}, next at {dt}, in {rem}")
    await q.edit_message_text(
        f"📅 Next {event.title()}: <b>{dt.strftime('%I:%M %p')}</b> in <b>{rem}</b>\nChoose time for reminder:",
        reply_markup=event_times_kb(event),
        parse_mode=ParseMode.HTML
    )

async def choose_time_handler(update: Update, ctx):
    q = update.callback_query
    await q.answer()
    parts = q.data.split("_", 2)
    event, time_str = parts[1], parts[2]
    ctx.user_data["event"] = event
    ctx.user_data["time"] = time_str
    ctx.user_data["state"] = "ask_minutes"
    await q.edit_message_text(f"✅ You chose {time_str}. How many minutes before?")

async def minutes_handler(update: Update, ctx):
    if ctx.user_data.get("state") != "ask_minutes":
        return
    try:
        mins = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Enter a valid number.")
        return
    event, time_str = ctx.user_data["event"], ctx.user_data["time"]
    user = await get_user(update.effective_user.id)
    dt, _ = next_event_info(event, user["timezone"])
    tz = pytz.timezone(user["timezone"])
    target = tz.localize(datetime.strptime(time_str, "%I:%M %p").replace(
        year=dt.year, month=dt.month, day=dt.day
    ))
    job_time = target - timedelta(minutes=mins)
    job_id = f"{update.effective_user.id}_{event}_{time_str}"
    logging.info(f"Scheduling job {job_id} at {job_time}")
    def send_reminder():
        asyncio.create_task(
            telegram_app.bot.send_message(update.effective_user.id, 
                f"🔔 Reminder: {event.title()} @ {time_str}")
        )
    scheduler.add_job(send_reminder, 'date', run_date=job_time, id=job_id)
    async with db_pool.acquire() as c:
        await c.execute("""
            INSERT INTO reminders(user_id, event, event_time, minutes_before, timezone, job_id)
            VALUES($1,$2,$3,$4,$5,$6) ON CONFLICT DO NOTHING
        """, update.effective_user.id, event, time_str, mins, user["timezone"], job_id)
    await update.message.reply_text(f"✅ Reminder set {mins}m before {time_str}")
    ctx.user_data.clear()

# --- Register Handlers ---
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CallbackQueryHandler(wax_handler, pattern="^wax$"))
telegram_app.add_handler(CallbackQueryHandler(wax_event_handler, pattern="^wax_"))
telegram_app.add_handler(CallbackQueryHandler(choose_time_handler, pattern="^choose_"))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, minutes_handler))

# --- FastAPI startup/shutdown ---
@app.on_event("startup")
async def on_startup():
    await init_db()
    scheduler.start()
    await telegram_app.initialize()
    await telegram_app.start()

@app.on_event("shutdown")
async def on_shutdown():
    await telegram_app.stop()
    await telegram_app.shutdown()
    await db_pool.close()

@app.post("/webhook")
async def webhook(req: Request):
    data = await req.json()
    await telegram_app.process_update(Update.de_json(data, telegram_app.bot))
    return {"ok": True}

@app.get("/")
async def root():
    return {"status": "running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
