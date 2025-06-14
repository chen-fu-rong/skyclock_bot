import os
import logging
from datetime import datetime, timedelta
from fastapi import FastAPI, Request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters
import uvicorn

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI()
PORT = int(os.getenv("PORT", "10000"))
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Dummy DB (replace with real database code)
user_timezones = {}  # user_id: offset
user_reminders = []  # list of (user_id, event, notify_time)

# Helper functions
def get_next_event_time(event: str, tz_offset_minutes: int) -> datetime:
    now = datetime.utcnow() + timedelta(minutes=tz_offset_minutes)
    hour = now.hour
    minute = now.minute
    next_time = now.replace(second=0, microsecond=0)

    if event == "geyser":
        if hour % 2 == 0:
            hour += 1
        next_time = next_time.replace(hour=hour, minute=35)
        if next_time <= now:
            next_time += timedelta(hours=2)

    elif event == "grandma":
        if hour % 2 != 0:
            hour += 1
        next_time = next_time.replace(hour=hour, minute=5)
        if next_time <= now:
            next_time += timedelta(hours=2)

    elif event == "turtle":
        if hour % 2 != 0:
            hour += 1
        next_time = next_time.replace(hour=hour, minute=20)
        if next_time <= now:
            next_time += timedelta(hours=2)

    return next_time

async def get_user_timezone(user_id: int) -> int:
    return user_timezones.get(user_id, 390)  # default to UTC+6:30

# Telegram handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome! Please send your timezone offset in minutes (e.g. 390 for UTC+6:30)")

async def handle_offset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        offset = int(update.message.text.strip())
        user_timezones[update.effective_user.id] = offset
        await update.message.reply_text(f"Timezone set to UTC+{offset/60:.2f} hours.")
    except ValueError:
        await update.message.reply_text("Please send a valid number.")

async def wax(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("\U0001F6C1 Geyser", callback_data="event_geyser")],
        [InlineKeyboardButton("\U0001F56F Grandma", callback_data="event_grandma")],
        [InlineKeyboardButton("\U0001F422 Turtle", callback_data="event_turtle")]
    ]
    await update.message.reply_text("Choose an event:", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_event_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    event = query.data.split("_")[1]

    offset = await get_user_timezone(user_id)
    next_time = get_next_event_time(event, offset)
    remaining = next_time - (datetime.utcnow() + timedelta(minutes=offset))
    mins = int(remaining.total_seconds() // 60)

    keyboard = [[InlineKeyboardButton("\U0001F514 Notify me", callback_data=f"notify_{event}")]]
    await query.edit_message_text(
        text=f"Next {event.title()} Event: {next_time.strftime('%H:%M')} ({mins} minutes left)",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_notify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    event = query.data.split("_")[1]
    context.user_data["event_to_notify"] = event
    await query.edit_message_text("How many minutes before the event should I notify you? (Enter a number)")

async def handle_notify_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    event = context.user_data.get("event_to_notify")
    if not event:
        return
    try:
        minutes_before = int(update.message.text.strip())
        offset = await get_user_timezone(user_id)
        event_time = get_next_event_time(event, offset)
        notify_time = event_time - timedelta(minutes=minutes_before)
        user_reminders.append((user_id, event, notify_time))
        await update.message.reply_text(f"Okay, I'll remind you {minutes_before} minutes before the {event.title()} event.")
    except ValueError:
        await update.message.reply_text("Please send a valid number.")

# Background task for reminders
async def reminder_loop(app: Application):
    while True:
        now = datetime.utcnow()
        to_notify = [r for r in user_reminders if r[2] <= now]
        for user_id, event, _ in to_notify:
            try:
                await app.bot.send_message(chat_id=user_id, text=f"Reminder: {event.title()} event is coming soon!")
            except Exception as e:
                logger.error(f"Failed to send reminder: {e}")
            user_reminders.remove((user_id, event, _))
        await asyncio.sleep(60)

# App startup
@app.on_event("startup")
async def on_startup():
    logger.info("Starting Telegram bot...")
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("wax", wax))
    application.add_handler(CallbackQueryHandler(handle_event_query, pattern="^event_"))
    application.add_handler(CallbackQueryHandler(handle_notify, pattern="^notify_"))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_notify_input))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex(r'^[-\d]+$'), handle_offset))

    import asyncio
    asyncio.create_task(reminder_loop(application))

    await application.initialize()
    await application.start()
    logger.info("Telegram bot started.")

@app.get("/")
async def root():
    return {"status": "ok"}

if __name__ == "__main__":
    logger.info(f"Starting server on port: {PORT}")
    uvicorn.run("bot:app", host="0.0.0.0", port=PORT, reload=False)
