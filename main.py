import os
import re
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager

import pytz
import uvicorn
from fastapi import FastAPI, Request, HTTPException
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)
from psycopg_pool import AsyncConnectionPool

# === CONFIGURATION ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
IS_RENDER = "RENDER" in os.environ
PORT = int(os.getenv("PORT", 10000))

# === LOGGING SETUP ===
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# === DATABASE POOL SETUP ===
pool = AsyncConnectionPool(
    conninfo=DATABASE_URL,
    min_size=1,
    max_size=5,
    open=False
)

# === FASTAPI LIFESPAN CONTEXT ===
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await pool.open()
    await pool.wait()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    tz_offset TEXT NOT NULL DEFAULT '+00:00',
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE TABLE IF NOT EXISTS notifications (
                    user_id BIGINT REFERENCES users(user_id),
                    event TEXT,
                    last_notified TIMESTAMPTZ,
                    PRIMARY KEY (user_id, event)
                );
                CREATE INDEX IF NOT EXISTS idx_user_id ON users(user_id);
            """)
    logger.info("✅ Database initialized")
    yield
    # Shutdown
    await pool.close()

app = FastAPI(lifespan=lifespan)

# === DATABASE OPERATIONS ===
async def set_tz_offset(user_id: int, offset: str):
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                INSERT INTO users (user_id, tz_offset)
                VALUES (%s, %s)
                ON CONFLICT (user_id)
                DO UPDATE SET tz_offset = EXCLUDED.tz_offset;
            """, (user_id, offset))

async def get_tz_offset(user_id: int) -> str:
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT tz_offset FROM users WHERE user_id = %s;",
                (user_id,)
            )
            row = await cur.fetchone()
            return row[0] if row else "+00:00"

async def set_notification(user_id: int, event: str):
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                INSERT INTO notifications (user_id, event)
                VALUES (%s, %s)
                ON CONFLICT (user_id, event) DO NOTHING;
            """, (user_id, event))

# === EVENT TIME CALCULATION FUNCTIONS ===
def next_occurrence(base: datetime, minute: int, hour_parity: str) -> datetime:
    candidate = base.replace(minute=minute, second=0, microsecond=0)
    if candidate <= base:
        candidate += timedelta(hours=1)
    while (hour_parity == "even" and candidate.hour % 2 != 0) or \
          (hour_parity == "odd" and candidate.hour % 2 == 0):
        candidate += timedelta(hours=1)
    return candidate

async def get_next_event_time(event: str, user_offset: str) -> str:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if event == "grandma":
        next_time = next_occurrence(now, 5, "even")
    elif event == "geyser":
        next_time = next_occurrence(now, 35, "odd")
    elif event == "turtle":
        next_time = next_occurrence(now, 20, "even")
    else:
        return "Unknown event"

    sign = 1 if user_offset.startswith('+') else -1
    h, m = map(int, user_offset[1:].split(":"))
    offset_delta = timedelta(hours=sign * h, minutes=sign * m)
    local_time = next_time + offset_delta

    formatted_local_time = local_time.strftime("%I:%M %p").lstrip("0")
    remaining = int((next_time - now).total_seconds() // 60)
    return f"{formatted_local_time} (in {remaining} mins)"

# === TELEGRAM BOT INITIALIZATION ===
application = Application.builder().token(BOT_TOKEN).build()

# === BOT COMMANDS AND CALLBACKS ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🇲🇲 Myanmar Time (+06:30)", callback_data='set_myanmar')],
        [InlineKeyboardButton("✍️ Enter Manually", callback_data='enter_manual')]
    ]
    await update.message.reply_text(
        "Please choose your timezone or enter it manually (e.g. `+06:30`, `-05:00`):",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def set_myanmar_timezone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    user_id = update.effective_user.id
    await set_tz_offset(user_id, "+06:30")
    await update.callback_query.edit_message_text("✅ Timezone set to Myanmar Time (+06:30).")
    await show_main_menu(update, context)

async def enter_manual_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("📥 Please type your timezone offset manually (e.g. `+06:30`).")

async def handle_timezone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    offset = update.message.text.strip()
    if not re.match(r"^[+-](0[0-9]|1[0-3]):[0-5][0-9]$", offset):
        await update.message.reply_text("❌ Invalid format. Use format like `+06:30` or `-05:00`.")
        return
    await set_tz_offset(user_id, offset)
    await update.message.reply_text(f"✅ Timezone set to UTC{offset}")
    await show_main_menu(update, context)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🕯️ Wax", callback_data='wax')]]
    if update.callback_query:
        await update.callback_query.message.reply_text("Main Menu:", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text("Main Menu:", reply_markup=InlineKeyboardMarkup(keyboard))

async def show_wax_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("👵 Grandma", callback_data='grandma')],
        [InlineKeyboardButton("🌋 Geyser", callback_data='geyser')],
        [InlineKeyboardButton("🐢 Turtle", callback_data='turtle')],
        [InlineKeyboardButton("⬅️ Back", callback_data='back_to_main')]
    ]
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("Choose an event:", reply_markup=InlineKeyboardMarkup(keyboard))

async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await show_main_menu(update, context)

async def handle_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    tz_offset = await get_tz_offset(user_id)
    event = update.callback_query.data
    event_map = {
        "grandma": "👵 Grandma",
        "geyser": "🌋 Geyser",
        "turtle": "🐢 Turtle"
    }
    time_str = await get_next_event_time(event, tz_offset)
    keyboard = [
        [InlineKeyboardButton("🔔 Notify Me", callback_data=f'notify_{event}')],
        [InlineKeyboardButton("⬅️ Back", callback_data='wax')]
    ]
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        f"{event_map[event]} next appears at: {time_str}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_notify_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    event = update.callback_query.data.split('_')[1]
    await set_notification(user_id, event)
    await update.callback_query.answer("🔔 You'll get notified 5 minutes before the event!")

# === SCHEDULED EVENT CHECKING ===
async def check_scheduled_events(application: Application):
    logger.info("Checking scheduled events...")
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT user_id, event FROM notifications;")
            notifications = await cur.fetchall()
            for user_id, event in notifications:
                tz_offset = await get_tz_offset(user_id)
                event_time = await get_next_event_time(event, tz_offset)
                try:
                    await application.bot.send_message(
                        chat_id=user_id,
                        text=f"⏰ Reminder: {event.capitalize()} starts soon! ({event_time})"
                    )
                except Exception as e:
                    logger.error(f"Notification failed for {user_id}: {e}")

# === FASTAPI ROUTES ===
@app.get("/")
async def root():
    return {"status": "SkyClock Bot is running."}

@app.get("/health")
async def health_check():
    return {
        "status": "OK",
        "database": "connected" if pool.check() else "disconnected",
        "time": datetime.now(timezone.utc).isoformat()
    }

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    try:
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
    except Exception as e:
        logger.error(f"Failed to process update: {e}")
    return {"ok": True}

# === ADD HANDLERS ===
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_timezone))
application.add_handler(CallbackQueryHandler(set_myanmar_timezone, pattern="^set_myanmar$"))
application.add_handler(CallbackQueryHandler(enter_manual_callback, pattern="^enter_manual$"))
application.add_handler(CallbackQueryHandler(show_wax_menu, pattern="^wax$"))
application.add_handler(CallbackQueryHandler(back_to_main, pattern="^back_to_main$"))
application.add_handler(CallbackQueryHandler(handle_event, pattern="^(grandma|geyser|turtle)$"))
application.add_handler(CallbackQueryHandler(handle_notify_callback, pattern="^notify_.*$"))

# === RUN SCHEDULED JOB IN LOCAL MODE ===
if not IS_RENDER:
    job_queue = application.job_queue
    job_queue.run_repeating(lambda ctx: asyncio.create_task(check_scheduled_events(application)), interval=60, first=10)

# === ON STARTUP HOOK ===
@app.on_event("startup")
async def startup_event():
    logger.info("Starting up and setting webhook...")
    if IS_RENDER and WEBHOOK_URL:
        await application.bot.set_webhook(WEBHOOK_URL)
        logger.info(f"Webhook set to {WEBHOOK_URL}")

# === ON SHUTDOWN HOOK ===
@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down, closing database pool...")
    await pool.close()

# === MAIN ENTRY POINT ===
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, log_level="info")
