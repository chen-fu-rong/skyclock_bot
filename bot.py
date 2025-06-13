import os
import json
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

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN") or "YOUR_BOT_TOKEN"
WEBHOOK_PATH = "/webhook"
PORT = int(os.getenv("PORT", "10000"))
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(",")))

USER_DB = "users.json"
def save_user_id(user_id):
    try:
        with open(USER_DB, "r") as f:
            users = json.load(f)
    except FileNotFoundError:
        users = []

    if user_id not in users:
        users.append(user_id)
        with open(USER_DB, "w") as f:
            json.dump(users, f)

def load_users():
    try:
        with open(USER_DB, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return []

app = FastAPI()
application = ApplicationBuilder().token(BOT_TOKEN).build()

# -------------------------------
# 🌍 Timezone & Shard Logic
# -------------------------------

def calculate_shard_info(target_date: datetime):
    day = target_date.weekday()
    is_even = day % 2 == 0
    color = "Red" if is_even else "Black"
    locations = ["Sanctuary", "Vault"] if is_even else ["Forest", "Brook"]
    reward = "4 wax"
    base_times = [time(2, 0), time(10, 0), time(18, 0)]
    shard_times = [datetime.combine(target_date.date(), t) for t in base_times]
    return {"color": color, "locations": locations, "reward": reward, "times_utc": shard_times}

def convert_to_local(utc_dt, offset_minutes):
    return utc_dt + timedelta(minutes=offset_minutes)

def to_12hr(dt: datetime):
    return dt.strftime("%I:%M %p")

def format_shard_message(day_label, shard_data, offset_minutes):
    times_local = [to_12hr(convert_to_local(t, offset_minutes)) for t in shard_data["times_utc"]]
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
    user_id = update.effective_user.id
    save_user_id(user_id)
    await update.message.reply_text("🌍 Please send your timezone offset (e.g. `/tz +0600`)", parse_mode="Markdown")

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
        await update.message.reply_text("✅ Timezone set!")

        # Show main menu after timezone set
        buttons = [
            [InlineKeyboardButton(text="Wax", callback_data="menu_0")],
            [InlineKeyboardButton(text="Shards", callback_data="menu_1")],
        ]
        menu_markup = InlineKeyboardMarkup(buttons)
        await update.message.reply_text("🌟 Main Menu", reply_markup=menu_markup)

    except Exception:
        await update.message.reply_text("Invalid timezone format. Use like /tz +0630")

async def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    query_data = query.data
    offset = context.user_data.get("utc_offset", 0)

    if query_data == "menu_0":  # Wax
        buttons = [
            [InlineKeyboardButton("👵 Grandma", callback_data="wax_grandma")],
            [InlineKeyboardButton("🌋 Geyser", callback_data="wax_geyser")],
            [InlineKeyboardButton("🐢 Turtle", callback_data="wax_turtle")]
        ]
        await query.edit_message_text("Select an event:", reply_markup=InlineKeyboardMarkup(buttons))

    elif query_data == "menu_1":  # Shards
        now_utc = datetime.utcnow()
        today_data = calculate_shard_info(now_utc)
        tomorrow_data = calculate_shard_info(now_utc + timedelta(days=1))

        msg = (
            format_shard_message("Today", today_data, offset) + "\n\n" +
            format_shard_message("Tomorrow", tomorrow_data, offset)
        )
        await query.edit_message_text(msg, parse_mode="Markdown")

    elif query_data.startswith("wax_"):
        now = datetime.utcnow() + timedelta(minutes=offset)
        hour = now.hour
        minute = now.minute

        if query_data == "wax_grandma":
            next_time = datetime.combine(now.date(), time((hour + 2) // 2 * 2, 5))
            emoji = "👵"
            label = "Grandma"
        elif query_data == "wax_geyser":
            next_time = datetime.combine(now.date(), time(((hour + 1) // 2 * 2) + 1, 35))
            emoji = "🌋"
            label = "Geyser"
        elif query_data == "wax_turtle":
            next_time = datetime.combine(now.date(), time((hour + 2) // 2 * 2, 20))
            emoji = "🐢"
            label = "Turtle"

        if next_time < now:
            next_time += timedelta(hours=2)

        diff = next_time - now
        msg = (
            f"{emoji} *Next {label} Event*\n"
            f"🕒 Starts at: {to_12hr(next_time)}\n"
            f"⏳ In: {str(diff).split('.')[0]}"
        )
        await query.edit_message_text(msg, parse_mode="Markdown")

# -------------------------------
# 📨 Broadcast
# -------------------------------

async def broadcast(update: Update, context: CallbackContext):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Unauthorized.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /broadcast Your message here")
        return

    message = " ".join(context.args)
    users = load_users()
    success = 0
    failed = 0

    for user_id in users:
        try:
            await context.bot.send_message(chat_id=user_id, text=message)
            success += 1
        except Exception as e:
            logging.warning(f"Failed to send to {user_id}: {e}")
            failed += 1

    await update.message.reply_text(f"✅ Sent to {success}, ❌ Failed: {failed}")

# -------------------------------
# 🔧 Setup Handlers
# -------------------------------

application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("tz", set_timezone))
application.add_handler(CommandHandler("broadcast", broadcast))
application.add_handler(CallbackQueryHandler(button_handler))

# -------------------------------
# 🚀 FastAPI + Webhook
# -------------------------------

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
