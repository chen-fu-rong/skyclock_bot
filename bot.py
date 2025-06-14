import os
import logging
import asyncio
from datetime import datetime, timedelta
from fastapi import FastAPI, Request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (Application, CommandHandler, CallbackQueryHandler,
                          ContextTypes, MessageHandler, filters)
import asyncpg

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot")

# ENV vars
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
WEBHOOK_URL = os.getenv("WEBHOOK_URL") or "https://skyclock-bot.onrender.com/webhook"
PORT = int(os.getenv("PORT", 10000))

# FastAPI app
app = FastAPI()

# Global vars
application = None
pool = None

# Event Times
EVENTS = {
    "Grandma": {"minute": 5, "hour_mod": 2, "emoji": "👵"},
    "Geyser": {"minute": 35, "hour_mod": 2, "offset": 1, "emoji": "🪨"},
    "Turtle": {"minute": 20, "hour_mod": 2, "emoji": "🐢"},
}

# Helpers
def get_next_event_time(event, now):
    info = EVENTS[event]
    hour_mod = info.get("hour_mod", 2)
    offset = info.get("offset", 0)
    minute = info["minute"]

    hour = now.hour + offset
    next_hour = hour + (hour_mod - hour % hour_mod)
    next_time = now.replace(hour=next_hour % 24, minute=minute, second=0, microsecond=0)
    if next_time <= now:
        next_time += timedelta(hours=hour_mod)
    return next_time

async def get_user_timezone(user_id):
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT timezone FROM users WHERE user_id = $1", user_id)
        return row["timezone"] if row else None

async def set_user_timezone(user_id, tz):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (user_id, timezone)
            VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE SET timezone = $2
        """, user_id, tz)

# Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send me your timezone offset (e.g. +0630, -0400)")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    tz = update.message.text.strip()
    if len(tz) in [5, 6] and (tz.startswith("+") or tz.startswith("-")):
        await set_user_timezone(user_id, tz)
        await update.message.reply_text("Timezone set! Click /wax to see event times.")
    else:
        await update.message.reply_text("Invalid format. Use like +0630 or -0400")

async def wax(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(f"{v['emoji']} {k}", callback_data=f"event:{k}")]
                for k, v in EVENTS.items()]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Choose an event:", reply_markup=reply_markup)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("event:"):
        event = data.split(":")[1]
        user_id = query.from_user.id
        tz = await get_user_timezone(user_id) or "+0000"
        now = datetime.utcnow()

        sign = 1 if tz.startswith('+') else -1
        offset_h = int(tz[1:3])
        offset_m = int(tz[3:])
        offset = timedelta(hours=offset_h, minutes=offset_m) * sign
        local_now = now + offset
        next_event = get_next_event_time(event, local_now)

        remaining = next_event - local_now
        minutes = int(remaining.total_seconds() // 60)
        hours = minutes // 60
        minutes %= 60
        info = EVENTS[event]

        text = (f"Next {info['emoji']} {event} event: {next_event.strftime('%H:%M')}\n"
                f"Time remaining: {hours}h {minutes}m")

        await query.edit_message_text(text)

# Reminder loop (disabled in free tier hosting)
async def reminder_loop():
    while True:
        await asyncio.sleep(60)
        # add reminder logic here if needed

# Webhook route
@app.post("/webhook")
async def webhook_handler(request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return {"ok": True}

# Startup
@app.on_event("startup")
async def startup():
    global application, pool
    logging.info("Starting server on port: %s", PORT)

    if not BOT_TOKEN:
        logging.error("TELEGRAM_BOT_TOKEN not set")
        return

    logging.info("Starting Telegram bot...")
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("wax", wax))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    await application.bot.set_webhook(WEBHOOK_URL)

    if DATABASE_URL:
        pool = await asyncpg.create_pool(DATABASE_URL)
    else:
        logging.warning("DATABASE_URL not set")

    asyncio.create_task(application.start())
    asyncio.create_task(reminder_loop())

# Run
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("bot:app", host="0.0.0.0", port=PORT, reload=False)
