import os
import logging
import asyncio
from fastapi import FastAPI, Request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    CallbackContext
)
from datetime import datetime, timedelta, time

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN")
WEBHOOK_PATH = "/webhook"
PORT = int(os.getenv("PORT", "10000"))

app = FastAPI()
application = ApplicationBuilder().token(BOT_TOKEN).build()

# Timezone utilities
def convert_to_local(utc_dt, offset_minutes):
    return utc_dt + timedelta(minutes=offset_minutes)

def format_12hr(dt):
    return dt.strftime("%I:%M %p")

def time_until(dt):
    now = datetime.utcnow()
    remaining = dt - now
    if remaining.total_seconds() < 0:
        return "Already passed"
    hours, remainder = divmod(remaining.total_seconds(), 3600)
    minutes = remainder // 60
    return f"{int(hours)}h {int(minutes)}m"

# Wax event logic
def next_event_time(event_type, offset_minutes):
    now_utc = datetime.utcnow()
    hour = now_utc.hour
    minute = now_utc.minute

    # Define offsets for each event
    if event_type == "grandma":
        event_minute = 5
        next_hour = hour + 1 if hour % 2 != 0 or (hour % 2 == 0 and minute >= 5) else hour
    elif event_type == "geyser":
        event_minute = 35
        next_hour = hour + 1 if hour % 2 == 0 or (hour % 2 != 0 and minute >= 35) else hour
    elif event_type == "turtle":
        event_minute = 20
        next_hour = hour + 2 if hour % 2 != 0 or (hour % 2 == 0 and minute >= 20) else hour
    else:
        return None, None

    next_utc = datetime.combine(now_utc.date(), time(next_hour % 24, event_minute))
    if next_utc <= now_utc:
        next_utc += timedelta(hours=2)

    local_dt = convert_to_local(next_utc, offset_minutes)
    return local_dt, time_until(next_utc)

# Bot Handlers
async def start(update: Update, context: CallbackContext):
    if "utc_offset" not in context.user_data:
        await update.message.reply_text(
            "Welcome! 🌟\nPlease set your timezone first using `/tz +0600` or `/tz -0430`"
        )
        return

    buttons = [
        [InlineKeyboardButton("Wax 🕯️", callback_data="menu_wax")],
        [InlineKeyboardButton("Quests", callback_data="menu_1")],
        [InlineKeyboardButton("Shops and Spirits", callback_data="menu_2")],
        [InlineKeyboardButton("Reset", callback_data="menu_3")],
        [InlineKeyboardButton("Concert and Shows", callback_data="menu_4")],
        [InlineKeyboardButton("Fifth Anniversary Events", callback_data="menu_5")],
        [InlineKeyboardButton("Shards 🔮", callback_data="menu_6")],
    ]
    await update.message.reply_text("Main Menu:", reply_markup=InlineKeyboardMarkup(buttons))

async def set_timezone(update: Update, context: CallbackContext):
    try:
        if len(context.args) != 1:
            await update.message.reply_text("Usage: /tz +0600 or /tz -0430")
            return
        tz_str = context.args[0]
        sign = 1 if tz_str.startswith("+") else -1
        hours = int(tz_str[1:3])
        minutes = int(tz_str[3:5])
        offset = sign * (hours * 60 + minutes)
        context.user_data["utc_offset"] = offset
        await update.message.reply_text(f"Time zone offset set to {offset} minutes.\nNow type /start again.")
    except Exception:
        await update.message.reply_text("Invalid timezone format. Use like /tz +0630")

async def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if "utc_offset" not in context.user_data:
        await query.edit_message_text("Please set your timezone using /tz before continuing.")
        return

    if data == "menu_wax":
        buttons = [
            [InlineKeyboardButton("👵 Grandma", callback_data="wax_grandma")],
            [InlineKeyboardButton("🌋 Geyser", callback_data="wax_geyser")],
            [InlineKeyboardButton("🐢 Turtle", callback_data="wax_turtle")],
        ]
        await query.edit_message_text("Choose an event:", reply_markup=InlineKeyboardMarkup(buttons))

    elif data.startswith("wax_"):
        event_type = data.split("_")[1]
        offset = context.user_data.get("utc_offset", 0)
        local_time, remaining = next_event_time(event_type, offset)
        if local_time:
            emoji = {"grandma": "👵", "geyser": "🌋", "turtle": "🐢"}[event_type]
            text = (
                f"{emoji} *Next {event_type.capitalize()} Event*\n"
                f"🕒 Time: {format_12hr(local_time)}\n"
                f"⏳ Starts in: {remaining}"
            )
            await query.edit_message_text(text, parse_mode="Markdown")
        else:
            await query.edit_message_text("Could not calculate event time.")

    else:
        await query.edit_message_text(f"You selected option {data}")

# Register Handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("tz", set_timezone))
application.add_handler(CallbackQueryHandler(button_handler))

# FastAPI Webhook Setup
async def process_updates():
    while True:
        update = await application.update_queue.get()
        try:
            await application.process_update(update)
        except Exception as e:
            logging.error(f"Update error: {e}")

@app.on_event("startup")
async def on_startup():
    await application.initialize()
    await application.start()
    asyncio.create_task(process_updates())
    webhook_url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}{WEBHOOK_PATH}"
    await application.bot.set_webhook(webhook_url)
    logging.info(f"Webhook set to {webhook_url}")

@app.on_event("shutdown")
async def on_shutdown():
    await application.stop()
    await application.shutdown()

@app.post(WEBHOOK_PATH)
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.update_queue.put(update)
    return {"ok": True}

@app.get("/")
async def root():
    return {"message": "Bot is running"}

# Local Run
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
