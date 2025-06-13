import os
import logging
import asyncio
from fastapi import FastAPI, Request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    CallbackContext,
)
from datetime import datetime, timedelta, time
import pytz

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN") or "YOUR_BOT_TOKEN"
WEBHOOK_PATH = "/webhook"
PORT = int(os.getenv("PORT", "10000"))

app = FastAPI()
application = ApplicationBuilder().token(BOT_TOKEN).build()

# -------------------------------
# 🌍 Timezone & Shard Logic
# -------------------------------

def get_shard_day_offset(utc_dt):
    # Shard days start at 00:00 UTC
    return utc_dt.date()

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
    shard_times = []

    for t in base_times:
        utc_dt = datetime.combine(target_date.date(), t)
        shard_times.append(utc_dt)

    return {
        "color": color,
        "locations": locations,
        "reward": reward,
        "times_utc": shard_times
    }

def convert_to_local(utc_dt, offset_minutes):
    return utc_dt + timedelta(minutes=offset_minutes)

def format_shard_message(day_label, shard_data, offset_minutes):
    times_local = [convert_to_local(t, offset_minutes).strftime("%H:%M") for t in shard_data["times_utc"]]
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

# -------------------------------
# 🤖 Bot Handlers
# -------------------------------

async def start(update: Update, context: CallbackContext):
    buttons = [
        [InlineKeyboardButton(text="Wax", callback_data="menu_0")],
        [InlineKeyboardButton(text="Quests", callback_data="menu_1")],
        [InlineKeyboardButton(text="Shops and Spirits", callback_data="menu_2")],
        [InlineKeyboardButton(text="Reset", callback_data="menu_3")],
        [InlineKeyboardButton(text="Concert and Shows", callback_data="menu_4")],
        [InlineKeyboardButton(text="Fifth Anniversary Events", callback_data="menu_5")],
        [InlineKeyboardButton(text="Shards", callback_data="menu_6")],
    ]
    menu_markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text("Welcome! 🌟", reply_markup=menu_markup)

async def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    query_data = query.data

    if query_data.startswith("menu_"):
        index = int(query_data.split("_")[1])

        if index == 6:  # Shards
            try:
                offset_minutes = context.user_data.get("utc_offset", 0)

                now_utc = datetime.utcnow()
                today = now_utc
                tomorrow = now_utc + timedelta(days=1)

                today_data = calculate_shard_info(today)
                tomorrow_data = calculate_shard_info(tomorrow)

                msg = (
                    format_shard_message("Today", today_data, offset_minutes) + "\n\n" +
                    format_shard_message("Tomorrow", tomorrow_data, offset_minutes)
                )

                await query.edit_message_text(msg, parse_mode="Markdown")
            except Exception as e:
                logging.error(f"Error calculating shards: {e}")
                await query.edit_message_text("Failed to calculate shard data.")
        else:
            await query.edit_message_text(f"You selected option {index}")

# -------------------------------
# 🕓 Timezone Setup (optional via command)
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
    except Exception as e:
        await update.message.reply_text("Invalid timezone format. Use like /tz +0630")

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
            logging.error(f"Error while processing update: {e}")

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
    logging.info(f"Received update: {data}")
    update = Update.de_json(data, application.bot)
    await application.update_queue.put(update)
    return {"ok": True}

@app.get("/")
async def root():
    return {"message": "Bot is running"}

# -------------------------------
# ▶️ Local Run
# -------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
