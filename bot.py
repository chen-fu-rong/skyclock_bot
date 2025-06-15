import os
import asyncio
import psycopg2
from fastapi import FastAPI, Request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)
from datetime import datetime, timedelta

# === CONFIGURATION ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # https://skyclock-bot.onrender.com/webhook

# === DATABASE ===
conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()
cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id BIGINT PRIMARY KEY,
        tz_offset TEXT
    );
""")
conn.commit()

def set_tz_offset(user_id, offset):
    cur.execute("""
        INSERT INTO users (user_id, tz_offset)
        VALUES (%s, %s)
        ON CONFLICT (user_id)
        DO UPDATE SET tz_offset = EXCLUDED.tz_offset;
    """, (user_id, offset))
    conn.commit()

def get_tz_offset(user_id):
    cur.execute("SELECT tz_offset FROM users WHERE user_id = %s;", (user_id,))
    row = cur.fetchone()
    return row[0] if row else "+00:00"

# === FASTAPI APP ===
app = FastAPI()

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return {"ok": True}

# === TELEGRAM BOT ===
application = Application.builder().token(BOT_TOKEN).build()

# === COMMAND HANDLERS ===
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
    set_tz_offset(user_id, "+06:30")
    await update.callback_query.edit_message_text("✅ Timezone set to Myanmar Time (+06:30).")
    await show_main_menu(update, context)

async def enter_manual_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("📥 Please type your timezone offset manually (e.g. `+06:30`).")

async def handle_timezone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    offset = update.message.text.strip()
    if not offset.startswith(("+", "-")) or ":" not in offset:
        await update.message.reply_text("❌ Invalid format. Use format like `+06:30` or `-05:00`.")
        return
    set_tz_offset(user_id, offset)
    await update.message.reply_text(f"✅ Timezone set to UTC{offset}")
    await show_main_menu(update, context)

# === MAIN MENU ===
async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🕯️ Wax", callback_data='wax')]]
    if update.callback_query:
        await update.callback_query.message.reply_text("Main Menu:", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text("Main Menu:", reply_markup=InlineKeyboardMarkup(keyboard))

# === WAX MENU ===
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

# === EVENT TIME HELPERS ===
def get_next_event_time(event: str, user_offset: str):
    now = datetime.utcnow()
    hour = now.hour

    if event == "grandma":
        # Even hours + 5 mins (e.g., 0:05, 2:05, 4:05…)
        next_hour = hour + (0 if hour % 2 == 0 and now.minute < 5 else 1 if hour % 2 == 1 else 2)
        minute = 5
    elif event == "geyser":
        # Odd hours + 35 mins (e.g., 1:35, 3:35, 5:35…)
        if hour % 2 == 1 and now.minute < 35:
            next_hour = hour
        else:
            next_hour = hour + (1 if hour % 2 == 0 else 2)
        minute = 35
    elif event == "turtle":
        # Every 4 hours starting from 0:20 (e.g., 0:20, 4:20, 8:20…)
        base_hours = [0, 4, 8, 12, 16, 20]
        future_times = [
            now.replace(hour=h, minute=20, second=0, microsecond=0)
            for h in base_hours if now < now.replace(hour=h, minute=20, second=0, microsecond=0)
        ]
        if future_times:
            next_time = future_times[0]
        else:
            next_time = now.replace(hour=0, minute=20, second=0, microsecond=0) + timedelta(days=1)
    else:
        return "Unknown event"

    if event != "turtle":
        next_time = now.replace(hour=next_hour % 24, minute=minute, second=0, microsecond=0)
        if next_time <= now:
            next_time += timedelta(hours=2)

    # Convert to user's local time
    sign = 1 if user_offset.startswith('+') else -1
    h, m = map(int, user_offset[1:].split(":"))
    offset_delta = timedelta(hours=sign * h, minutes=sign * m)
    local_time = next_time + offset_delta

    # Time remaining
    remaining = int((next_time - now).total_seconds() // 60)
    return f"{local_time.strftime('%H:%M')} (in {remaining} mins)"


# === EVENT CALLBACKS ===
async def handle_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    tz_offset = get_tz_offset(user_id)
    event = update.callback_query.data

    event_map = {
        "grandma": "👵 Grandma",
        "geyser": "🌋 Geyser",
        "turtle": "🐢 Turtle"
    }

    if event not in event_map:
        return

    time_str = get_next_event_time(event, tz_offset)
    keyboard = [
        [InlineKeyboardButton("🔔 Notify Me", callback_data=f'notify_{event}')],
        [InlineKeyboardButton("⬅️ Back", callback_data='wax')]
    ]
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        f"{event_map[event]} next appears at: {time_str}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# === PLACEHOLDER NOTIFY CALLBACK ===
async def handle_notify_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("Notification feature coming soon!")

# === HANDLERS ===
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_timezone))

application.add_handler(CallbackQueryHandler(set_myanmar_timezone, pattern="^set_myanmar$"))
application.add_handler(CallbackQueryHandler(enter_manual_callback, pattern="^enter_manual$"))
application.add_handler(CallbackQueryHandler(show_wax_menu, pattern="^wax$"))
application.add_handler(CallbackQueryHandler(back_to_main, pattern="^back_to_main$"))
application.add_handler(CallbackQueryHandler(handle_event, pattern="^(grandma|geyser|turtle)$"))
application.add_handler(CallbackQueryHandler(handle_notify_callback, pattern="^notify_.*$"))

# === STARTUP ===
async def main():
    await application.initialize()
    await application.start()
    await application.bot.set_webhook(WEBHOOK_URL)
    print("✅ Bot started with webhook set.")

if __name__ == "__main__":
    import nest_asyncio
    import uvicorn
    nest_asyncio.apply()
    asyncio.run(main())
    uvicorn.run(app, host="0.0.0.0", port=10000)
