import os
import asyncio
import logging
from datetime import datetime, timedelta

from fastapi import FastAPI, Request
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          ContextTypes, MessageHandler, filters)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pytz
import asyncpg

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
PORT = int(os.getenv("PORT", "10000"))

logging.basicConfig(level=logging.INFO)

# DB Setup
db_pool = None

async def init_db():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL)
    async with db_pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                timezone TEXT
            )
        """)

async def get_user(user_id):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)

async def add_user(user_id, timezone):
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (user_id, timezone) VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE SET timezone = EXCLUDED.timezone
        """, user_id, timezone)

# FastAPI + Telegram
app = FastAPI()
telegram_app = Application.builder().token(BOT_TOKEN).build()
scheduler = AsyncIOScheduler()

# Main menu keyboard
def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📦 Wax", callback_data="wax"),
            InlineKeyboardButton("🧩 Shards", callback_data="shards")
        ]
    ])

# Wax menu
wax_keyboard = InlineKeyboardMarkup([
    [InlineKeyboardButton("👵 Grandma", callback_data="wax_grandma")],
    [InlineKeyboardButton("🌋 Geyser", callback_data="wax_geyser")],
    [InlineKeyboardButton("🐢 Turtle", callback_data="wax_turtle")],
    [InlineKeyboardButton("⬅️ Back", callback_data="back_main")]
])

# Notify options
notify_keyboard = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("5 mins", callback_data="notify_5"),
        InlineKeyboardButton("10 mins", callback_data="notify_10")
    ],
    [
        InlineKeyboardButton("15 mins", callback_data="notify_15"),
        InlineKeyboardButton("30 mins", callback_data="notify_30")
    ]
])

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name
    user = await get_user(user_id)

    if user is None:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🇲🇲 Myanmar", callback_data="tz_Myanmar")]
        ])
        await update.message.reply_text("👋 Welcome! Please choose your timezone:", reply_markup=keyboard)
    else:
        await update.message.reply_text(f"👋 Hello again {first_name}! What do you want to check?", reply_markup=main_menu_keyboard())

# Handle timezone selection
async def timezone_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data.startswith("tz_"):
        tz = "Asia/Yangon" if query.data == "tz_Myanmar" else None
        if tz:
            await add_user(user_id, tz)
            await query.edit_message_text("✅ Timezone set! Use /start to continue.")
        else:
            await query.edit_message_text("❌ Unsupported timezone.")

# Wax main handler
async def handle_wax(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Choose a Wax event:", reply_markup=wax_keyboard)

# Wax event detail handlers
def event_response(event_name: str, time_str: str):
    return f"📅 Next {event_name}: {time_str}\n⏳ Time left: ...\n\n🔔 Want a reminder?"

def wax_event_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔔 Notify Me", callback_data="notify")],
        [InlineKeyboardButton("⬅️ Back", callback_data="wax")]
    ])

async def wax_event_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "wax_grandma":
        await query.edit_message_text(event_response("Grandma", "Even hours + 5 mins"), reply_markup=wax_event_keyboard())
    elif query.data == "wax_geyser":
        await query.edit_message_text(event_response("Geyser", "Odd hours + 35 mins"), reply_markup=wax_event_keyboard())
    elif query.data == "wax_turtle":
        await query.edit_message_text(event_response("Turtle", "Even hours + 20 mins"), reply_markup=wax_event_keyboard())

# Notify time selection
async def notify_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("⏰ How many minutes before do you want to be reminded?", reply_markup=notify_keyboard)

# Register Handlers
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CallbackQueryHandler(timezone_selection, pattern="^tz_"))
telegram_app.add_handler(CallbackQueryHandler(handle_wax, pattern="^wax$"))
telegram_app.add_handler(CallbackQueryHandler(wax_event_handler, pattern="^wax_(grandma|geyser|turtle)$"))
telegram_app.add_handler(CallbackQueryHandler(notify_handler, pattern="^notify$"))

@app.on_event("startup")
async def on_startup():
    await init_db()
    await telegram_app.initialize()
    await telegram_app.start()
    scheduler.start()

@app.on_event("shutdown")
async def on_shutdown():
    await telegram_app.stop()
    await telegram_app.shutdown()
    await db_pool.close()

@app.post("/webhook")
async def telegram_webhook(req: Request):
    data = await req.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return {"status": "ok"}

@app.get("/")
async def root():
    return {"status": "running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("bot:app", host="0.0.0.0", port=PORT)
