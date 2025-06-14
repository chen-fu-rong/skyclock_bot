import os
import asyncio
from datetime import datetime, timedelta
from fastapi import FastAPI, Request
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler,
    ContextTypes, MessageHandler, filters
)
import pytz
import httpx

BOT_TOKEN = os.getenv("BOT_TOKEN") or "YOUR_BOT_TOKEN"
BASE_URL = os.getenv("BASE_URL") or "https://your-deployment-url.com"

# In-memory DB
user_timezones = {}
notify_settings = {}  # user_id -> {event, minutes_before}

app = FastAPI()
telegram_app = Application.builder().token(BOT_TOKEN).build()

# Event time logic (Myanmar timezone)
MYANMAR_TZ = pytz.timezone("Asia/Yangon")

def get_next_event_time(event):
    now = datetime.now(MYANMAR_TZ)
    hour = now.hour
    minute = now.minute

    if event == "Geyser":
        next_hour = hour + 1 if hour % 2 == 0 else hour
        event_time = now.replace(hour=next_hour, minute=35, second=0, microsecond=0)
    elif event == "Grandma":
        next_hour = hour + 1 if hour % 2 != 0 else hour
        event_time = now.replace(hour=next_hour, minute=5, second=0, microsecond=0)
    elif event == "Turtle":
        next_hour = hour + 1 if hour % 2 != 0 else hour
        event_time = now.replace(hour=next_hour, minute=20, second=0, microsecond=0)
    else:
        return None

    if event_time < now:
        event_time += timedelta(hours=2)
    return event_time

def build_notify_minutes_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("5 minutes before", callback_data="notify_5")],
        [InlineKeyboardButton("10 minutes before", callback_data="notify_10")],
        [InlineKeyboardButton("15 minutes before", callback_data="notify_15")],
        [InlineKeyboardButton("🔙 Back", callback_data="wax_menu")]
    ])

# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🇲🇲 Myanmar", callback_data="set_tz:+6.5")],
    ])
    await update.message.reply_text("Welcome! Please select your timezone:", reply_markup=keyboard)

async def handle_timezone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tz_offset = query.data.split(":")[1]
    user_timezones[query.from_user.id] = float(tz_offset)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔥 Wax", callback_data="wax_menu")]
    ])
    await query.edit_message_text("Timezone saved ✅", reply_markup=keyboard)

async def wax_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("👵 Grandma", callback_data="wax_grandma")],
        [InlineKeyboardButton("🌋 Geyser", callback_data="wax_geyser")],
        [InlineKeyboardButton("🐢 Turtle", callback_data="wax_turtle")],
        [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
    ])
    await query.edit_message_text("Choose an event:", reply_markup=keyboard)

async def wax_event_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    event_map = {
        "wax_grandma": "Grandma",
        "wax_geyser": "Geyser",
        "wax_turtle": "Turtle",
    }
    event = event_map[query.data]
    event_time = get_next_event_time(event)
    user_id = query.from_user.id
    tz_offset = user_timezones.get(user_id, 6.5)
    local_time = event_time + timedelta(hours=tz_offset - 6.5)
    delta = event_time - datetime.now(MYANMAR_TZ)
    minutes, seconds = divmod(int(delta.total_seconds()), 60)
    msg = f"Next {event} event at 🕒 {local_time.strftime('%H:%M')}\nTime left: {minutes} minutes"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⏰ Notify Me", callback_data=f"notify_{event.lower()}")],
        [InlineKeyboardButton("🔙 Back", callback_data="wax_menu")]
    ])
    await query.edit_message_text(msg, reply_markup=keyboard)

async def notify_event_choose_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    event = query.data.split("_")[1].capitalize()
    context.user_data["notify_event"] = event
    await query.edit_message_text(f"How many minutes before {event} should I notify you?", reply_markup=build_notify_minutes_keyboard())

async def notify_event_set(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    minutes = int(query.data.split("_")[1])
    event = context.user_data.get("notify_event")
    notify_settings[query.from_user.id] = {"event": event, "minutes": minutes}
    await query.edit_message_text(f"⏰ Got it! You'll be notified {minutes} minutes before {event} event.", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back", callback_data="wax_menu")]
    ]))

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Main Menu", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("🔥 Wax", callback_data="wax_menu")]
    ]))

# Periodic notifier
async def notifier():
    while True:
        now = datetime.now(MYANMAR_TZ)
        for user_id, setting in notify_settings.items():
            event_time = get_next_event_time(setting["event"])
            delta = event_time - now
            if 0 < delta.total_seconds() <= setting["minutes"] * 60:
                await telegram_app.bot.send_message(
                    chat_id=user_id,
                    text=f"⏰ Reminder: {setting['event']} starts in {setting['minutes']} minutes!"
                )
        await asyncio.sleep(30)

# FastAPI lifespan for startup/shutdown
@app.on_event("startup")
async def on_startup():
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CallbackQueryHandler(handle_timezone, pattern=r"^set_tz"))
    telegram_app.add_handler(CallbackQueryHandler(wax_menu, pattern="^wax_menu$"))
    telegram_app.add_handler(CallbackQueryHandler(wax_event_handler, pattern="^wax_(grandma|geyser|turtle)$"))
    telegram_app.add_handler(CallbackQueryHandler(notify_event_choose_time, pattern=r"^notify_(grandma|geyser|turtle)$"))
    telegram_app.add_handler(CallbackQueryHandler(notify_event_set, pattern=r"^notify_\\d+$"))
    telegram_app.add_handler(CallbackQueryHandler(main_menu, pattern="^main_menu$"))
    await telegram_app.initialize()
    await telegram_app.start()
    asyncio.create_task(notifier())
    await telegram_app.updater.start_webhook(
        webhook_path="/webhook",
        request_kwargs={"timeout": 10},
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 10000)),
        url=f"{BASE_URL}/webhook"
    )

@app.on_event("shutdown")
async def on_shutdown():
    await telegram_app.stop()

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return "ok"

@app.get("/")
async def root():
    return {"message": "SkyClock Bot running"}
