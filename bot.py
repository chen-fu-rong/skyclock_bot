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
import asyncpg

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_PATH = "/webhook"
PORT = int(os.getenv("PORT", "10000"))
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(",")))
DATABASE_URL = os.getenv("DATABASE_URL")

app = FastAPI()
application = ApplicationBuilder().token(BOT_TOKEN).build()

# -------------------------------
# 🌍 Database
# -------------------------------

db_pool = None

async def init_db():
    global db_pool
    print("DATABASE_URL:", DATABASE_URL)
    db_pool = await asyncpg.create_pool(DATABASE_URL)
    async with db_pool.acquire() as conn:
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            timezone_offset INTEGER
        )
        """)

async def set_user_timezone(user_id: int, offset: int):
    async with db_pool.acquire() as conn:
        await conn.execute("""
        INSERT INTO users (user_id, timezone_offset)
        VALUES ($1, $2)
        ON CONFLICT (user_id) DO UPDATE SET timezone_offset = $2
        """, user_id, offset)

async def get_user_timezone(user_id: int) -> int:
    async with db_pool.acquire() as conn:
        result = await conn.fetchval("SELECT timezone_offset FROM users WHERE user_id=$1", user_id)
        return result if result is not None else 0

# -------------------------------
# 🧭 Event Time Logic
# -------------------------------

def convert_to_local(utc_dt, offset_minutes):
    return utc_dt + timedelta(minutes=offset_minutes)

def format_12h(dt: datetime):
    return dt.strftime("%I:%M %p").lstrip("0")

def next_event_time(event_name: str, now: datetime) -> datetime:
    hour_offsets = {
        "Grandma": (0, 5),
        "Geyser": (1, 35),
        "Turtle": (2, 20),
    }
    if event_name not in hour_offsets:
        return now
    base_hour, minute = hour_offsets[event_name]
    for i in range(0, 48):  # check next 2 days
        check_hour = (i + base_hour) % 24
        check_day = now + timedelta(hours=i)
        candidate = datetime.combine(check_day.date(), time(check_hour, minute))
        if candidate > now:
            return candidate
    return now

def format_time_until(future: datetime, now: datetime) -> str:
    delta = future - now
    hours, remainder = divmod(delta.total_seconds(), 3600)
    minutes = remainder // 60
    return f"{int(hours)}h {int(minutes)}m"

# -------------------------------
# 🤖 Bot Handlers
# -------------------------------

async def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    offset = await get_user_timezone(user_id)
    if offset == 0:
        await update.message.reply_text("Please set your timezone offset using /tz. Example: `/tz +0630`", parse_mode="Markdown")
    else:
        await show_main_menu(update, context)

async def show_main_menu(update: Update, context: CallbackContext):
    buttons = [
        [InlineKeyboardButton("Wax 🕯️", callback_data="wax")],
        [InlineKeyboardButton("Shards 🔮", callback_data="menu_shards")],
    ]
    markup = InlineKeyboardMarkup(buttons)
    if update.message:
        await update.message.reply_text("🌟 Choose an option:", reply_markup=markup)
    else:
        await update.callback_query.edit_message_text("🌟 Choose an option:", reply_markup=markup)

async def set_timezone(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    try:
        if len(context.args) != 1:
            await update.message.reply_text("Usage: /tz +0600 or /tz -0430")
            return

        tz_str = context.args[0]
        sign = 1 if tz_str.startswith("+") else -1
        hours = int(tz_str[1:3])
        minutes = int(tz_str[3:5])
        offset = sign * (hours * 60 + minutes)

        await set_user_timezone(user_id, offset)
        await update.message.reply_text("✅ Timezone set successfully!")
        await show_main_menu(update, context)
    except Exception:
        await update.message.reply_text("Invalid format. Use like /tz +0630")

async def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()
    data = query.data

    offset = await get_user_timezone(user_id)
    now = datetime.utcnow()
    local_now = convert_to_local(now, offset)

    if data == "wax":
        buttons = [
            [InlineKeyboardButton("👵 Grandma", callback_data="wax_grandma")],
            [InlineKeyboardButton("🌋 Geyser", callback_data="wax_geyser")],
            [InlineKeyboardButton("🐢 Turtle", callback_data="wax_turtle")],
        ]
        await query.edit_message_text("🕯️ Choose a wax event:", reply_markup=InlineKeyboardMarkup(buttons))
    elif data.startswith("wax_"):
        event_name = data.split("_")[1].capitalize()
        next_time = convert_to_local(next_event_time(event_name, now), offset)
        until = format_time_until(next_time, local_now)
        await query.edit_message_text(
            f"{event_emoji(event_name)} *{event_name}*\nNext at: *{format_12h(next_time)}*\nStarts in: *{until}*",
            parse_mode="Markdown"
        )
    elif data == "menu_shards":
        today_data = calculate_shard_info(now)
        tomorrow_data = calculate_shard_info(now + timedelta(days=1))
        msg = (
            format_shard_message("Today", today_data, offset) + "\n\n" +
            format_shard_message("Tomorrow", tomorrow_data, offset)
        )
        await query.edit_message_text(msg, parse_mode="Markdown")

# -------------------------------
# 🔮 Shard Predictions
# -------------------------------

def calculate_shard_info(target_date: datetime):
    day = target_date.weekday()
    is_even = day % 2 == 0
    color = "Red" if is_even else "Black"
    locations = ["Sanctuary", "Vault"] if is_even else ["Forest", "Brook"]
    base_times = [time(2, 0), time(10, 0), time(18, 0)]
    shard_times = [datetime.combine(target_date.date(), t) for t in base_times]
    return {"color": color, "locations": locations, "reward": "4 wax", "times_utc": shard_times}

def format_shard_message(day_label, shard_data, offset_minutes):
    times_local = [convert_to_local(t, offset_minutes) for t in shard_data["times_utc"]]
    return (
        f"🔮 *{day_label}'s Shard Prediction*\n"
        f"Color: {shard_data['color']} Shard\n"
        f"Locations: {', '.join(shard_data['locations'])}\n"
        f"Reward: {shard_data['reward']}\n"
        f"Times:\n"
        f"• First Shard: {format_12h(times_local[0])}\n"
        f"• Second Shard: {format_12h(times_local[1])}\n"
        f"• Last Shard: {format_12h(times_local[2])}"
    )

def event_emoji(name: str):
    return {
        "Grandma": "👵",
        "Geyser": "🌋",
        "Turtle": "🐢"
    }.get(name, "")

# -------------------------------
# 📬 Broadcast Command
# -------------------------------

async def broadcast(update: Update, context: CallbackContext):
    if update.effective_user.id not in ADMIN_IDS:
        return await update.message.reply_text("❌ You are not authorized.")
    if not context.args:
        return await update.message.reply_text("Usage: /broadcast <message>")
    msg = " ".join(context.args)
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id FROM users")
        for row in rows:
            try:
                await application.bot.send_message(row["user_id"], msg)
            except Exception as e:
                logging.warning(f"Failed to send to {row['user_id']}: {e}")
    await update.message.reply_text("✅ Broadcast sent.")

# -------------------------------
# 🧩 Register Handlers
# -------------------------------

application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("tz", set_timezone))
application.add_handler(CommandHandler("broadcast", broadcast))
application.add_handler(CallbackQueryHandler(button_handler))

# -------------------------------
# ⚙️ FastAPI Webhook Setup
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
    await init_db()
    await application.initialize()
    await application.start()
    asyncio.create_task(process_updates())
    webhook_url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}{WEBHOOK_PATH}"
    await application.bot.set_webhook(webhook_url)
    logging.info(f"Webhook set: {webhook_url}")

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

# -------------------------------
# ▶️ Local Run
# -------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
