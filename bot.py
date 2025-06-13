import os
import logging
import asyncio
from datetime import datetime, timedelta, time
from fastapi import FastAPI, Request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN") or "YOUR_BOT_TOKEN"
WEBHOOK_PATH = "/webhook"
PORT = int(os.getenv("PORT", "10000"))

app = FastAPI()
application = ApplicationBuilder().token(BOT_TOKEN).build()

# --- Event schedule times ---
GRANDMA_TIMES = [time(h, 5) for h in range(0, 24, 2)]
TURTLE_TIMES = [time(h, 20) for h in range(0, 24, 2)]
GEYSER_TIMES = [time(h, 35) for h in range(1, 24, 2)]
DREAMS_SKATER_TIMES = [time(11, 0), time(14, 0), time(18, 0)]

EVENTS = {
    "Grandma": GRANDMA_TIMES,
    "Turtle": TURTLE_TIMES,
    "Geyser": GEYSER_TIMES,
    "Dreams Skater": DREAMS_SKATER_TIMES,
}

user_notifications = {}  # {user_id: [(event_name, notify_dt, event_dt), ...]}

# --- Utility functions ---

def format_time(t: time) -> str:
    return t.strftime("%H:%M")

def get_next_event_time(now: datetime, event_times: list[time]) -> datetime:
    today = now.date()
    for t in event_times:
        dt = datetime.combine(today, t)
        if dt > now:
            return dt
    # Next day first event
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
            lines.append(f"~~{format_time(t)}~~")  # markdown strikethrough
        else:
            lines.append(format_time(t))
    return "\n".join(lines)

# --- Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [[InlineKeyboardButton("Wax", callback_data="wax")]]
    await update.message.reply_text("Welcome! 🌟 Choose an option:", reply_markup=InlineKeyboardMarkup(buttons))

async def wax_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    buttons = [[InlineKeyboardButton(event, callback_data=f"wax_event_{event.lower().replace(' ', '_')}")] for event in EVENTS]
    buttons.append([InlineKeyboardButton("Back", callback_data="back_to_main")])
    await query.edit_message_text("Select an event:", reply_markup=InlineKeyboardMarkup(buttons))

async def wax_event_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    event_key = query.data[len("wax_event_"):]
    event_name = next((k for k in EVENTS if k.lower().replace(' ', '_') == event_key), None)
    if not event_name:
        await query.edit_message_text("Unknown event.")
        return

    now = datetime.now()
    event_times = EVENTS[event_name]
    next_event = get_next_event_time(now, event_times)
    delta = next_event - now
    delta_str = seconds_to_hms(int(delta.total_seconds()))
    schedule = build_day_schedule_text(now, event_times)

    text = (
        f"**{event_name} Event**\n"
        f"Next event: {next_event.strftime('%Y-%m-%d %H:%M')}\n"
        f"Time left: {delta_str}\n\n"
        f"Today's schedule:\n{schedule}"
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
    event_name = next((k for k in EVENTS if k.lower().replace(' ', '_') == event_key), None)
    if not event_name:
        await query.edit_message_text("Unknown event.")
        return

    event_times = EVENTS[event_name]
    buttons = [[InlineKeyboardButton(format_time(t), callback_data=f"notify_time_{event_key}_{format_time(t)}")] for t in event_times]
    buttons.append([InlineKeyboardButton("Back", callback_data=f"wax_event_{event_key}")])

    await query.edit_message_text(
        f"Select the event time for **{event_name}** to notify:",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown"
    )

async def notify_time_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data.split("_")  # format: notify_time_<event_key>_<HH:MM>
    if len(data) < 4:
        await query.edit_message_text("Invalid data.")
        return
    event_key = data[2]
    event_time_str = data[3]

    context.user_data["notify_event_key"] = event_key
    context.user_data["notify_event_time"] = event_time_str

    await query.edit_message_text(f"How many minutes before {event_time_str} do you want to be notified? (Send a number)")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "notify_event_key" in context.user_data and "notify_event_time" in context.user_data:
        try:
            minutes_before = int(update.message.text)
            if minutes_before < 0 or minutes_before > 1440:
                raise ValueError()
        except ValueError:
            await update.message.reply_text("Please enter a valid number of minutes between 0 and 1440.")
            return

        event_key = context.user_data.pop("notify_event_key")
        event_time_str = context.user_data.pop("notify_event_time")

        event_name = next((k for k in EVENTS if k.lower().replace(' ', '_') == event_key), None)
        if not event_name:
            await update.message.reply_text("Error: event not found.")
            return

        hh, mm = map(int, event_time_str.split(":"))
        event_time_obj = time(hh, mm)
        now = datetime.now()
        event_dt = datetime.combine(now.date(), event_time_obj)
        if event_dt < now:
            event_dt += timedelta(days=1)

        notify_dt = event_dt - timedelta(minutes=minutes_before)
        if notify_dt < now:
            await update.message.reply_text("Notification time has already passed for this event time.")
            return

        user_notifications.setdefault(update.message.from_user.id, []).append((event_name, notify_dt, event_dt))
        await update.message.reply_text(
            f"Notification set for {event_name} at {event_time_str} "
            f"{minutes_before} minutes before (at {notify_dt.strftime('%Y-%m-%d %H:%M:%S')})."
        )
    else:
        await update.message.reply_text("Send /start to begin.")

async def back_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "back_to_main":
        buttons = [[InlineKeyboardButton("Wax", callback_data="wax")]]
        await query.edit_message_text("Welcome! 🌟 Choose an option:", reply_markup=InlineKeyboardMarkup(buttons))
    elif data == "wax":
        buttons = [[InlineKeyboardButton(event, callback_data=f"wax_event_{event.lower().replace(' ', '_')}")] for event in EVENTS]
        buttons.append([InlineKeyboardButton("Back", callback_data="back_to_main")])
        await query.edit_message_text("Select an event:", reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await query.edit_message_text("Back pressed but no handler found.")

# Background task to send notifications
async def notification_checker():
    while True:
        now = datetime.now()
        to_remove = []
        for user_id, notifications in user_notifications.items():
            for notif in notifications:
                event_name, notify_dt, event_dt = notif
                if notify_dt <= now:
                    try:
                        await application.bot.send_message(
                            chat_id=user_id,
                            text=f"🔔 Reminder: {event_name} event at {event_dt.strftime('%H:%M')} is coming soon!"
                        )
                    except Exception as e:
                        logging.error(f"Error sending notification to {user_id}: {e}")
                    to_remove.append((user_id, notif))
        # Remove sent notifications
        for user_id, notif in to_remove:
            if notif in user_notifications.get(user_id, []):
                user_notifications[user_id].remove(notif)

        await asyncio.sleep(30)  # check every 30 seconds

# --- Register handlers ---

application.add_handler(CommandHandler("start", start))
application.add_handler(CallbackQueryHandler(wax_handler, pattern="^wax$"))
application.add_handler(CallbackQueryHandler(wax_event_handler, pattern="^wax_event_"))
application.add_handler(CallbackQueryHandler(notify_handler, pattern="^notify_"))
application.add_handler(CallbackQueryHandler(notify_time_handler, pattern="^notify_time_"))
application.add_handler(CallbackQueryHandler(back_handler, pattern="^back_to_main$|^back$|^wax$"))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# --- Webhook & FastAPI ---

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
    asyncio.create_task(notification_checker())
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

# --- Run locally ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
