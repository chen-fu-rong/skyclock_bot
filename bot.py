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

# ---------------------------
# Event schedule times (all times in a day, 24h format)
# Grandma (even hours + 5 min)
GRANDMA_TIMES = [time(h, 5) for h in range(0, 24, 2)]

# Turtle (even hours + 20 min)
TURTLE_TIMES = [time(h, 20) for h in range(0, 24, 2)]

# Geyser (odd hours + 35 min)
GEYSER_TIMES = [time(h, 35) for h in range(1, 24, 2)]

# Dreams Skater (no notification)
DREAMS_SKATER_TIMES = [time(11, 0), time(14, 0), time(18, 0)]

EVENTS = {
    "Grandma": GRANDMA_TIMES,
    "Turtle": TURTLE_TIMES,
    "Geyser": GEYSER_TIMES,
    "Dreams Skater": DREAMS_SKATER_TIMES,
}

# In-memory store notifications: {user_id: [(event_name, notify_time, event_time), ...]}
user_notifications = {}

# ---------------------------
# Utilities

def format_time(t: time) -> str:
    # Format time as 12-hour with AM/PM and strip leading zero from hour
    return t.strftime("%I:%M %p").lstrip("0")

def get_next_event_time(now: datetime, event_times: list[time]) -> datetime | None:
    today = now.date()
    # Find first event today after now
    for t in event_times:
        dt = datetime.combine(today, t)
        if dt > now:
            return dt
    # None today, next event tomorrow at first time
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
        formatted = format_time(t)
        if dt < now:
            # Past event - strikethrough with markdown
            lines.append(f"~~{formatted}~~")
        else:
            lines.append(formatted)
    return "\n".join(lines)

# ---------------------------
# Bot Handlers

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "Welcome! 🌟\nChoose a button below."
    buttons = [
        [InlineKeyboardButton("Wax", callback_data="wax")],
        # Add more main menu buttons if needed
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

async def wax_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    buttons = [
        [InlineKeyboardButton(event, callback_data=f"wax_event_{event.lower().replace(' ', '_')}")]
        for event in EVENTS.keys()
    ]
    buttons.append([InlineKeyboardButton("Back", callback_data="back_to_main")])
    await query.edit_message_text("Select an event:", reply_markup=InlineKeyboardMarkup(buttons))

async def wax_event_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    now = datetime.now()  # approximate user local time
    event_key = query.data[len("wax_event_"):]
    event_name = None
    for k in EVENTS.keys():
        if k.lower().replace(' ', '_') == event_key:
            event_name = k
            break
    if not event_name:
        await query.edit_message_text("Unknown event.")
        return

    event_times = EVENTS[event_name]
    next_event_dt = get_next_event_time(now, event_times)
    delta = next_event_dt - now
    delta_str = seconds_to_hms(int(delta.total_seconds()))

    schedule_text = build_day_schedule_text(now, event_times)

    text = (
        f"*{event_name} Event*\n"
        f"Next event: {next_event_dt.strftime('%Y-%m-%d %I:%M %p').lstrip('0')}\n"
        f"Time left: {delta_str}\n\n"
        f"Today's schedule:\n{schedule_text}"
    )

    buttons = [
        [InlineKeyboardButton("Notify Me", callback_data=f"notify_{event_key}")],
        [InlineKeyboardButton("Back", callback_data="wax")],
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")

async def notify_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    event_key = query.data[len("notify_"):]
    event_name = None
    for k in EVENTS.keys():
        if k.lower().replace(' ', '_') == event_key:
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
        f"Select the event time you want to be notified about for *{event_name}*:",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown"
    )

async def notify_time_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data  # format: notify_time_<event_key>_<HH:MM AM/PM>
    parts = data.split("_")
    event_key = parts[2]
    event_time_str = " ".join(parts[3:])  # To include AM/PM

    # Store selected event info for next step input
    context.user_data["notify_event_key"] = event_key
    context.user_data["notify_event_time"] = event_time_str

    await query.edit_message_text(
        f"How many minutes before {event_time_str} do you want to be notified? (Send a number)"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text
    if "notify_event_key" in context.user_data and "notify_event_time" in context.user_data:
        try:
            minutes_before = int(text)
            if minutes_before < 0 or minutes_before > 1440:
                raise ValueError()
        except ValueError:
            await update.message.reply_text("Please enter a valid positive integer number of minutes (0-1440).")
            return

        event_key = context.user_data.pop("notify_event_key")
        event_time_str = context.user_data.pop("notify_event_time")

        event_name = None
        for k in EVENTS.keys():
            if k.lower().replace(' ', '_') == event_key:
                event_name = k
                break
        if not event_name:
            await update.message.reply_text("Error: event not found.")
            return

        # Parse event_time_str from 12-hour format string like "8:35 AM"
        try:
            event_dt_time = datetime.strptime(event_time_str, "%I:%M %p").time()
        except Exception:
            await update.message.reply_text("Error parsing event time.")
            return

        now = datetime.now()
        today = now.date()
        event_dt = datetime.combine(today, event_dt_time)
        if event_dt < now:
            event_dt += timedelta(days=1)

        notify_dt = event_dt - timedelta(minutes=minutes_before)
        if notify_dt < now:
            await update.message.reply_text("Notification time already passed for this event. Try again.")
            return

        # Save notification
        user_notifications.setdefault(user_id, []).append((event_name, notify_dt, event_dt))
        await update.message.reply_text(
            f"Notification set for {event_name} at {format_time(event_dt_time)} "
            f"{minutes_before} minutes before (at {notify_dt.strftime('%Y-%m-%d %I:%M %p').lstrip('0')})"
        )
    else:
        await update.message.reply_text("Send /start to begin.")

# ---------------------------
# Background notification checker

async def notification_checker():
    while True:
        now = datetime.now()
        for user_id, notifs in list(user_notifications.items()):
            to_remove = []
            for i, (event_name, notify_dt, event_dt) in enumerate(notifs):
                if now >= notify_dt:
                    try:
                        await application.bot.send_message(
                            chat_id=user_id,
                            text=f"🔔 Reminder: {event_name} event at {format_time(event_dt.time())} is coming soon!"
                        )
                    except Exception as e:
                        logging.error(f"Error sending notification to {user_id}: {e}")
                    to_remove.append(i)
            # Remove sent notifications
            for i in reversed(to_remove):
                del notifs[i]
            if not notifs:
                del user_notifications[user_id]
        await asyncio.sleep(10)  # check every 10 seconds

# ---------------------------
# CallbackQueryHandler router

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.data == "wax":
        await wax_handler(update, context)
    elif query.data.startswith("wax_event_"):
        await wax_event_handler(update, context)
    elif query.data.startswith("notify_") and not query.data.startswith("notify_time_"):
        await notify_handler(update, context)
    elif query.data.startswith("notify_time_"):
        await notify_time_handler(update, context)
    elif query.data == "back_to_main":
        await start(update, context)
    else:
        await query.answer("Unknown action.")

# ---------------------------
# Register handlers

application.add_handler(CommandHandler("start", start))
application.add_handler(CallbackQueryHandler(callback_handler))
application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

# ---------------------------
# FastAPI webhook integration

async def process_updates():
    while True:
        update = await application.update_queue.get()
        try:
            await application.process_update(update)
        except Exception as e:
            logging.error(f"Error processing update: {e}")

@app.on_event("startup")
async def on_startup():
    await application.initialize()
    await application.start()
    asyncio.create_task(process_updates())
    asyncio.create_task(notification_checker())  # start notifications loop

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

# ---------------------------
# Run local dev server

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
