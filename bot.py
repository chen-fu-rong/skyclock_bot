import os
import logging
import asyncio
from fastapi import FastAPI, Request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    CallbackContext,
)
from datetime import datetime, timedelta, time

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN") or "YOUR_BOT_TOKEN"
WEBHOOK_PATH = "/webhook"
PORT = int(os.getenv("PORT", "10000"))

app = FastAPI()
application = ApplicationBuilder().token(BOT_TOKEN).build()

# -------------------------------
# 🌍 Timezone & Shard Logic
# -------------------------------

def calculate_shard_info(target_date: datetime):
    day = target_date.weekday()
    is_even = day % 2 == 0

    if is_even:
        color = "Red"
        locations = ["Sanctuary", "Vault"]
    else:
        color = "Black"
        locations = ["Forest", "Brook"]

    reward = "4 wax"
    base_times = [time(2, 0), time(10, 0), time(18, 0)]
    shard_times = [datetime.combine(target_date.date(), t) for t in base_times]

    return {
        "color": color,
        "locations": locations,
        "reward": reward,
        "times_utc": shard_times
    }

def convert_to_local(utc_dt, offset_minutes):
    return utc_dt + timedelta(minutes=offset_minutes)

def format_shard_message(day_label, shard_data, offset_minutes):
    times_local = [convert_to_local(t, offset_minutes).strftime("%I:%M %p") for t in shard_data["times_utc"]]
    return (
        f"🔮 *{day_label}'s Shard Prediction*\n"
        f"Color: {shard_data['color']} Shard\n"
        f"Locations: {', '.join(shard_data['locations'])}\n"
        f"Reward: {shard_data['reward']}\n"
        f"Times:\n"
        f"• First Shard: {times_local[0]}\n"
        f"• Second Shard: {times_local[1]}\n"
        f"• Last Shard: {times_local[2]}"
    )

def get_next_event(event_name: str, now: datetime):
    hour = now.hour
    minute = now.minute
    today = now.date()

    if event_name == "grandma":
        emoji = "👵"
        base_minutes = [h * 60 + 5 for h in range(0, 24, 2)]
    elif event_name == "geyser":
        emoji = "🌋"
        base_minutes = [h * 60 + 35 for h in range(1, 24, 2)]
    elif event_name == "turtle":
        emoji = "🐢"
        base_minutes = [h * 60 + 20 for h in range(0, 24, 2)]
    else:
        return None, None

    now_minutes = hour * 60 + minute

    for base_min in base_minutes:
        if base_min > now_minutes:
            event_hour = base_min // 60
            event_minute = base_min % 60
            event_time = datetime.combine(today, time(event_hour, event_minute))
            return event_time, emoji

    # next day
    base_min = base_minutes[0]
    event_hour = base_min // 60
    event_minute = base_min % 60
    event_time = datetime.combine(today + timedelta(days=1), time(event_hour, event_minute))
    return event_time, emoji

# -------------------------------
# 🤖 Bot Handlers
# -------------------------------

async def start(update: Update, context: CallbackContext):
    await update.message.reply_text("Welcome! 🌟\nPlease set your time zone using `/tz +0600` or `/tz -0430`")
    
    buttons = [
        [InlineKeyboardButton(text="Wax", callback_data="menu_wax")],
        [InlineKeyboardButton(text="Quests", callback_data="menu_1")],
        [InlineKeyboardButton(text="Shops and Spirits", callback_data="menu_2")],
        [InlineKeyboardButton(text="Reset", callback_data="menu_3")],
        [InlineKeyboardButton(text="Concert and Shows", callback_data="menu_4")],
        [InlineKeyboardButton(text="Fifth Anniversary Events", callback_data="menu_5")],
        [InlineKeyboardButton(text="Shards", callback_data="menu_6")],
    ]
    await update.message.reply_text("Main Menu:", reply_markup=InlineKeyboardMarkup(buttons))

async def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "menu_6":
        offset_minutes = context.user_data.get("utc_offset", 0)
        now = datetime.utcnow()
        today_data = calculate_shard_info(now)
        tomorrow_data = calculate_shard_info(now + timedelta(days=1))

        msg = (
            format_shard_message("Today", today_data, offset_minutes) + "\n\n" +
            format_shard_message("Tomorrow", tomorrow_data, offset_minutes)
        )
        await query.edit_message_text(msg, parse_mode="Markdown")

    elif data == "menu_wax":
        buttons = [
            [InlineKeyboardButton("👵 Grandma", callback_data="wax_grandma")],
            [InlineKeyboardButton("🌋 Geyser", callback_data="wax_geyser")],
            [InlineKeyboardButton("🐢 Turtle", callback_data="wax_turtle")],
        ]
        await query.edit_message_text("Choose an event:", reply_markup=InlineKeyboardMarkup(buttons))

    elif data.startswith("wax_"):
        event = data.split("_")[1]
        offset = context.user_data.get("utc_offset", 0)
        now = datetime.utcnow() + timedelta(minutes=offset)
        event_time, emoji = get_next_event(event, now)
        time_remaining = event_time - now

        hours, remainder = divmod(time_remaining.seconds, 3600)
        minutes = remainder // 60
        time_str = event_time.strftime("%I:%M %p")

        await query.edit_message_text(
            f"{emoji} Next {event.title()} event is at *{time_str}*\n⏳ Starts in {hours}h {minutes}m",
            parse_mode="Markdown"
        )
    else:
        await query.edit_message_text(f"You selected: {data}")

# -------------------------------
# 🕓 Timezone Setup
# -------------------------------

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
        await update.message.reply_text(f"Time zone offset set to {offset} minutes.")
    except:
        await update.message.reply_text("Invalid format. Use /tz +0630 or /tz -0800")

# -------------------------------
# 📌 Register Handlers
# -------------------------------

application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("tz", set_timezone))
application.add_handler(CallbackQueryHandler(button_handler))

# -------------------------------
# ⚙️ Webhook / FastAPI Setup
# -------------------------------

async def process_updates():
    while True:
        update = await application.update_queue.get()
        try:
            await application.process_update(update)
        except Exception as e:
            logging.error(f"Update processing error: {e}")

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
