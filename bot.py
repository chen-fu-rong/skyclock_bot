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
    MessageHandler,
    filters,
)
from datetime import datetime, timedelta, time

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN") or "YOUR_BOT_TOKEN"
WEBHOOK_PATH = "/webhook"
PORT = int(os.getenv("PORT", "10000"))

app = FastAPI()
application = ApplicationBuilder().token(BOT_TOKEN).build()

# -------------------------------
# Wax event schedules (24h times)
GRANDMA_TIMES = [time(h, 5) for h in range(0, 24, 2)]    # even hours + 5 min
TURTLE_TIMES = [time(h, 20) for h in range(0, 24, 2)]    # even hours + 20 min
GEYSER_TIMES = [time(h, 35) for h in range(1, 24, 2)]    # odd hours + 35 min
DREAMS_SKATER_TIMES = [time(11, 0), time(14, 0), time(18, 0)]  # fixed times, no notify

EVENTS = {
    "Grandma": GRANDMA_TIMES,
    "Turtle": TURTLE_TIMES,
    "Geyser": GEYSER_TIMES,
    "Dreams Skater": DREAMS_SKATER_TIMES,
}

# In-memory notifications: {user_id: [(event_name, notify_time, event_time), ...]}
user_notifications = {}

# -------------------------------
# Utilities

def format_time(t: time) -> str:
    return t.strftime("%H:%M")

def get_next_event_time(now: datetime, event_times: list[time]) -> datetime:
    today = now.date()
    for t in event_times:
        dt = datetime.combine(today, t)
        if dt > now:
            return dt
    # If none left today, next event tomorrow first time
    return datetime.combine(today + timedelta(days=1), event_times[0])

def seconds_to_hms(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}h {m}m {s}s"
    elif m > 0:
        return f"{m}m {s}s"
    else:
        return f"{s}s"

def build_day_schedule_text(now: datetime, event_times: list[time]) -> str:
    lines = []
    today = now.date()
    for t in event_times:
        dt = datetime.combine(today, t)
        if dt < now:
            # Strikethrough past events (Markdown)
            lines.append(f"~~{format_time(t)}~~")
        else:
            lines.append(format_time(t))
    return "\n".join(lines)

def escape_markdown(text: str) -> str:
    # Minimal escape for MarkdownV2 in Telegram
    replace_chars = r"_*[]()~`>#+-=|{}.!"
    for ch in replace_chars:
        text = text.replace(ch, "\\" + ch)
    return text

# -------------------------------
# Bot Handlers

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
    if update.message:
        await update.message.reply_text("Welcome! 🌟", reply_markup=menu_markup)
    elif update.callback_query:
        await update.callback_query.edit_message_text("Welcome! 🌟", reply_markup=menu_markup)

async def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    query_data = query.data

    if query_data.startswith("menu_"):
        index = int(query_data.split("_")[1])

        # === Wax menu ===
        if index == 0:
            buttons = [
                [InlineKeyboardButton(event, callback_data=f"wax_event_{event.lower().replace(' ', '_')}")]
                for event in EVENTS.keys()
            ]
            buttons.append([InlineKeyboardButton("Back", callback_data="back_to_main")])
            await query.edit_message_text("Select an event:", reply_markup=InlineKeyboardMarkup(buttons))
            return

        # === Shards menu (existing) ===
        if index == 6:
            try:
                offset_minutes = context.user_data.get("utc_offset", 0)
                now_utc = datetime.utcnow()
                today = now_utc
                tomorrow = now_utc + timedelta(days=1)

                # Use your existing calculate_shard_info() and format_shard_message() here if needed
                # For brevity, just send a placeholder here:
                await query.edit_message_text("Shard logic here (already implemented).")
            except Exception as e:
                logging.error(f"Error calculating shards: {e}")
                await query.edit_message_text("Failed to calculate shard data.")
            return

        # Other menus
        await query.edit_message_text(f"You selected option {index}")
        return

    # === Wax event selected ===
    if query_data.startswith("wax_event_"):
        event_key = query_data[len("wax_event_") :]
        event_name = None
        for k in EVENTS.keys():
            if k.lower().replace(" ", "_") == event_key:
                event_name = k
                break
        if not event_name:
            await query.edit_message_text("Unknown event.")
            return

        event_times = EVENTS[event_name]
        now = datetime.now()
        next_event_dt = get_next_event_time(now, event_times)
        delta = next_event_dt - now
        delta_str = seconds_to_hms(int(delta.total_seconds()))
        schedule_text = build_day_schedule_text(now, event_times)
        # Escape underscores for MarkdownV2
        safe_event_name = escape_markdown(event_name)
        safe_schedule_text = escape_markdown(schedule_text)

        text = (
            f"*{safe_event_name} Event*\n"
            f"Next event: `{next_event_dt.strftime('%Y-%m-%d %H:%M')}`\n"
            f"Time left: {delta_str}\n\n"
            f"Today's schedule:\n{safe_schedule_text}"
        )

        buttons = [
            [InlineKeyboardButton("Notify Me", callback_data=f"notify_{event_key}")],
            [InlineKeyboardButton("Back", callback_data="menu_0")],
        ]

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="MarkdownV2",
        )
        return

    # === Notify Me button clicked ===
    if query_data.startswith("notify_") and not query_data.startswith("notify_time_"):
        event_key = query_data[len("notify_") :]
        event_name = None
        for k in EVENTS.keys():
            if k.lower().replace(" ", "_") == event_key:
                event_name = k
                break
        if not event_name:
            await query.edit_message_text("Unknown event.")
            return

        event_times = EVENTS[event_name]
        buttons = [
            [InlineKeyboardButton(format_time(t), callback_data=f"notify_time_{event_key}_{format_time(t)}")]
            for t in event_times
        ]
        buttons.append([InlineKeyboardButton("Back", callback_data=f"wax_event_{event_key}")])

        await query.edit_message_text(
            f"Select the event time you want to be notified about for *{escape_markdown(event_name)}*:",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="MarkdownV2",
        )
        return

    # === Notify time selected: ask user how many minutes before ===
    if query_data.startswith("notify_time_"):
        parts = query_data.split("_")
        if len(parts) < 4:
            await query.edit_message_text("Invalid data.")
            return
        event_key = parts[2]
        event_time_str = parts[3]

        # Save in user_data to await next message
        context.user_data["notify_event_key"] = event_key
        context.user_data["notify_event_time"] = event_time_str

        await query.edit_message_text(
            f"How many minutes before {event_time_str} do you want to be notified? (Send a number)"
        )
        return

    # === Back buttons ===
    if query_data == "back_to_main":
                # Back to main menu
        await show_main_menu(update, context)
        return

# Helper function to show main menu (called from several places)
async def show_main_menu(update: Update, context: CallbackContext):
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
    if update.callback_query:
        await update.callback_query.edit_message_text("Welcome! 🌟", reply_markup=menu_markup)
    elif update.message:
        await update.message.reply_text("Welcome! 🌟", reply_markup=menu_markup)

# Handle user messages (expecting number input for notify minutes)
async def message_handler(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    text = update.message.text.strip()

    if "notify_event_key" in context.user_data and "notify_event_time" in context.user_data:
        # Expecting number of minutes before
        try:
            minutes_before = int(text)
            if minutes_before < 0:
                raise ValueError()

            event_key = context.user_data["notify_event_key"]
            event_time_str = context.user_data["notify_event_time"]

            # Convert event_time_str to datetime today or tomorrow based on now
            now = datetime.now()
            event_time_obj = datetime.strptime(event_time_str, "%H:%M").time()
            event_dt = datetime.combine(now.date(), event_time_obj)
            if event_dt < now:
                event_dt += timedelta(days=1)

            notify_time = event_dt - timedelta(minutes=minutes_before)
            if notify_time < now:
                await update.message.reply_text("Notification time already passed. Choose a smaller minutes value.")
                return

            # Save notification
            user_notifications.setdefault(user_id, []).append((event_key, notify_time, event_dt))

            await update.message.reply_text(
                f"Notification set for event '{event_key.replace('_', ' ').title()}' at {event_time_str}, "
                f"{minutes_before} minutes before."
            )
            # Clear waiting state
            context.user_data.pop("notify_event_key")
            context.user_data.pop("notify_event_time")

            # Optionally show main menu again
            await show_main_menu(update, context)

        except ValueError:
            await update.message.reply_text("Please send a valid positive number for minutes.")
    else:
        await update.message.reply_text("Send /start to begin.")

# Background task to check notifications every 10 seconds
async def notification_checker():
    while True:
        now = datetime.now()
        to_remove = []
        for user_id, notifs in user_notifications.items():
            for idx, (event_key, notify_time, event_dt) in enumerate(notifs):
                if notify_time <= now:
                    try:
                        chat_id = user_id
                        text = (
                            f"⏰ Reminder: Event *{event_key.replace('_', ' ').title()}* is at "
                            f"{event_dt.strftime('%H:%M')}.\n"
                            f"Get ready!"
                        )
                        await application.bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
                    except Exception as e:
                        logging.error(f"Failed to send notification to {user_id}: {e}")
                    to_remove.append((user_id, idx))
        # Remove sent notifications
        for user_id, idx in sorted(to_remove, key=lambda x: x[1], reverse=True):
            if user_id in user_notifications and idx < len(user_notifications[user_id]):
                user_notifications[user_id].pop(idx)
        await asyncio.sleep(10)

# -------------------------------
# Your shard & timezone logic here (keep from your original code)
# -------------------------------

# Reuse calculate_shard_info(), format_shard_message(), set_timezone(), etc.
# Register those handlers below

# -------------------------------
# Register Handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("tz", set_timezone))
application.add_handler(CallbackQueryHandler(button_handler))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

# -------------------------------
# FastAPI webhook & startup/shutdown

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
    asyncio.create_task(notification_checker())  # Start background notifier task
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
# Run locally
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
