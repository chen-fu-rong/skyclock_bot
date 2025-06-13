from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from datetime import datetime, timedelta, time
import logging
import os
import asyncio
from fastapi import FastAPI, Request

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN") or "YOUR_BOT_TOKEN"
WEBHOOK_PATH = "/webhook"
PORT = int(os.getenv("PORT", "10000"))

app = FastAPI()
application = ApplicationBuilder().token(BOT_TOKEN).build()

# --- Shard logic & utilities (12hr format now) ---

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

def format_time_12hr(dt):
    return dt.strftime("%I:%M %p").lstrip('0')

def format_shard_message(day_label, shard_data, offset_minutes):
    times_local = [format_time_12hr(convert_to_local(t, offset_minutes)) for t in shard_data["times_utc"]]
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

# --- Command Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [
        [InlineKeyboardButton(text="Wax", callback_data="menu_0")],
        [InlineKeyboardButton(text="Quests", callback_data="menu_1")],
        [InlineKeyboardButton(text="Shops and Spirits", callback_data="menu_2")],
        [InlineKeyboardButton(text="Reset", callback_data="menu_3")],
        [InlineKeyboardButton(text="Concert and Shows", callback_data="menu_4")],
        [InlineKeyboardButton(text="Fifth Anniversary Events", callback_data="menu_5")],
        [InlineKeyboardButton(text="Shards", callback_data="menu_6")],
        [InlineKeyboardButton(text="Set Timezone", callback_data="set_timezone_menu")]
    ]
    menu_markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text("Welcome! 🌟", reply_markup=menu_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    query_data = query.data

    if query_data.startswith("menu_"):
        index = int(query_data.split("_")[1])

        if index == 6:  # Shards
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
        else:
            await query.edit_message_text(f"You selected option {index}")

    elif query_data == "set_timezone_menu":
        # Show timezone options (+14:00 to -12:00 in 30 min increments for simplicity)
        tz_offsets = [
            "+1400", "+1300", "+1200", "+1100", "+1000", "+0930", "+0900", "+0830", "+0800",
            "+0700", "+0600", "+0530", "+0500", "+0430", "+0400", "+0330", "+0300",
            "+0200", "+0100", "+0000",
            "-0100", "-0200", "-0300", "-0330", "-0400", "-0430", "-0500", "-0600",
            "-0700", "-0800", "-0900", "-1000", "-1100", "-1200"
        ]

        buttons = []
        row = []
        for offset in tz_offsets:
            row.append(InlineKeyboardButton(offset, callback_data=f"timezone_{offset}"))
            if len(row) == 4:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        buttons.append([InlineKeyboardButton("Cancel", callback_data="cancel_timezone")])

        await query.edit_message_text(
            "Select your timezone offset from UTC:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    elif query_data.startswith("timezone_"):
        offset_str = query_data.split("_")[1]
        sign = 1 if offset_str.startswith("+") else -1
        hours = int(offset_str[1:3])
        minutes = int(offset_str[3:5])
        offset_minutes = sign * (hours * 60 + minutes)

        context.user_data["utc_offset"] = offset_minutes
        await query.edit_message_text(f"Timezone set to UTC{offset_str}. Your times will be adjusted accordingly.")

    elif query_data == "cancel_timezone":
        await query.edit_message_text("Timezone setting cancelled.")

# --- Webhook and FastAPI setup omitted for brevity (use your existing) ---

application.add_handler(CommandHandler("start", start))
application.add_handler(CallbackQueryHandler(button_handler))

# ... Your FastAPI webhook code remains unchanged

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
