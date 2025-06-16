import os
import asyncio
import re
import logging
import pytz
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, Request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)
from psycopg_pool import AsyncConnectionPool
from contextlib import asynccontextmanager
import uvicorn

# === ✅ CONFIGURATION ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
IS_RENDER = "RENDER" in os.environ
PORT = int(os.environ.get("PORT", 10000))

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# === ✅ DATABASE SETUP ===
pool = AsyncConnectionPool(
    conninfo=DATABASE_URL,
    min_size=1,
    max_size=5,
    open=False
)

@asynccontextmanager
async def lifespan(app: FastAPI):
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
            """)
    logger.info("✅ Database initialized")
    yield
    await pool.close()

app = FastAPI(lifespan=lifespan)

# === ✅ DATABASE UTILS ===
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
            await cur.execute("SELECT tz_offset FROM users WHERE user_id = %s;", (user_id,))
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

# === ✅ EVENT TIME CALCULATION ===
def next_occurrence(base: datetime, minute: int, hour_parity: str) -> datetime:
    candidate = base.replace(minute=minute, second=0, microsecond=0)
    if candidate <= base:
        candidate += timedelta(hours=1)
    while (hour_parity == "even" and candidate.hour % 2 != 0) or \
          (hour_parity == "odd" and candidate.hour % 2 == 0):
        candidate += timedelta(hours=1)
    return candidate

def to_12hr(dt: datetime) -> str:
    return dt.strftime("%I:%M %p").lstrip("0")

async def get_next_event_time(event: str, user_offset: str) -> str:
    now = datetime.utcnow()
    if event == "grandma":
        event_time = next_occurrence(now, 5, "even")
    elif event == "geyser":
        event_time = next_occurrence(now, 35, "odd")
    elif event == "turtle":
        event_time = next_occurrence(now, 20, "even")
    else:
        return "Unknown event"

    sign = 1 if user_offset.startswith('+') else -1
    h, m = map(int, user_offset[1:].split(":"))
    offset = timedelta(hours=sign*h, minutes=sign*m)
    local_time = event_time + offset
    mins_left = int((event_time - now).total_seconds() // 60)
    return f"{to_12hr(local_time)} (in {mins_left} mins)"

# === ✅ WEBHOOK ENDPOINT ===
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    asyncio.create_task(process_update(data))
    return {"ok": True}

@app.get("/health")
async def health():
    return {"status": "OK", "db": pool.check(), "time": datetime.utcnow().isoformat()}

async def process_update(data: dict):
    try:
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
    except Exception as e:
        logger.error(f"Failed to process update: {e}")

# === ✅ BOT HANDLERS ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("\ud83c\udf1f Myanmar Time (+06:30)", callback_data='set_myanmar')],
        [InlineKeyboardButton("\u270d\ufe0f Enter Manually", callback_data='enter_manual')]
    ]
    await update.message.reply_text(
        "Please choose your timezone or enter manually (e.g. `+06:30`, `-05:00`):",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def set_myanmar_timezone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await set_tz_offset(update.effective_user.id, "+06:30")
    await update.callback_query.edit_message_text("✅ Timezone set to Myanmar Time (+06:30).")
    await show_main_menu(update, context)

async def enter_manual_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("\ud83d\udcc5 Please enter your timezone offset manually (e.g. `+06:30`).")

async def handle_timezone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    offset = update.message.text.strip()
    if not re.match(r"^[+-](0[0-9]|1[0-3]):[0-5][0-9]$", offset):
        await update.message.reply_text("❌ Invalid format. Use format like `+06:30`.")
        return
    await set_tz_offset(update.effective_user.id, offset)
    await update.message.reply_text(f"✅ Timezone set to UTC{offset}")
    await show_main_menu(update, context)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("\ud83d\udd27 Wax", callback_data='wax')]]
    if update.callback_query:
        await update.callback_query.message.reply_text("Main Menu:", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text("Main Menu:", reply_markup=InlineKeyboardMarkup(keyboard))

async def show_wax_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("\ud83d\udc75 Grandma", callback_data='grandma')],
        [InlineKeyboardButton("\ud83c\udf0b Geyser", callback_data='geyser')],
        [InlineKeyboardButton("\ud83d\udc22 Turtle", callback_data='turtle')],
        [InlineKeyboardButton("\u2b05\ufe0f Back", callback_data='back_to_main')]
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
    event_map = {"grandma": "\ud83d\udc75 Grandma", "geyser": "\ud83c\udf0b Geyser", "turtle": "\ud83d\udc22 Turtle"}
    time_str = await get_next_event_time(event, tz_offset)
    keyboard = [
        [InlineKeyboardButton("\ud83d\udd14 Notify Me", callback_data=f'notify_{event}')],
        [InlineKeyboardButton("\u2b05\ufe0f Back", callback_data='wax')]
    ]
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(f"{event_map[event]} next appears at: {time_str}", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_notify_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    event = update.callback_query.data.split('_')[1]
    await set_notification(user_id, event)
    await update.callback_query.answer("\ud83d\udd14 You'll be notified 5 mins before!")

async def check_scheduled_events(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Checking events for notifications...")
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT user_id, event FROM notifications;")
            for user_id, event in await cur.fetchall():
                tz = await get_tz_offset(user_id)
                msg = await get_next_event_time(event, tz)
                try:
                    await context.bot.send_message(user_id, f"⏰ Reminder: {event.capitalize()} starts soon! ({msg})")
                except Exception as e:
                    logger.error(f"Failed to notify {user_id}: {e}")

# === ✅ INITIALIZE ===
async def initialize_bot(app: Application):
    if IS_RENDER:
        await app.bot.set_webhook(WEBHOOK_URL)
        logger.info("Webhook set")
    else:
        await app.updater.start_polling()
        logger.info("Started polling")

application = Application.builder().token(BOT_TOKEN).post_init(initialize_bot).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_timezone))
application.add_handler(CallbackQueryHandler(set_myanmar_timezone, pattern="^set_myanmar$"))
application.add_handler(CallbackQueryHandler(enter_manual_callback, pattern="^enter_manual$"))
application.add_handler(CallbackQueryHandler(show_wax_menu, pattern="^wax$"))
application.add_handler(CallbackQueryHandler(back_to_main, pattern="^back_to_main$"))
application.add_handler(CallbackQueryHandler(handle_event, pattern="^(grandma|geyser|turtle)$"))
application.add_handler(CallbackQueryHandler(handle_notify_callback, pattern="^notify_.*$"))

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False)
