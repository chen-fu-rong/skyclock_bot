import os
import logging
import asyncio
from datetime import datetime, time, timedelta
from fastapi import FastAPI, Request
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
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

# ---------------------------
# Event schedule times (24h format)
GRANDMA_TIMES = [time(h, 5) for h in range(0, 24, 2)]  # even hours + 5 min
TURTLE_TIMES = [time(h, 20) for h in range(0, 24, 2)]  # even hours + 20 min
GEYSER_TIMES = [time(h, 35) for h in range(1, 24, 2)]  # odd hours + 35 min
DREAMS_SKATER_TIMES = [time(11, 0), time(14, 0), time(18, 0)]  # fixed times

EVENTS = {
    "Grandma": GRANDMA_TIMES,
    "Turtle": TURTLE_TIMES,
    "Geyser": GEYSER_TIMES,
    "Dreams Skater": DREAMS_SKATER_TIMES,
}

# In-memory notification storage: {user_id: [(event_name, notify_time, event_time), ...]}
user_notifications = {}

# ---------------------------
# Utils

def format_time(t: time) -> str:
    return t.strftime("%H:%M")

def get_next_event_time(now: datetime, event_times: list[time]) -> datetime:
    today = now.date()
    for t in event_times:
        dt = datetime.combine(today, t)
        if dt > now:
            return dt
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
            lines.append(f"~~{format_time(t)}~~")  # strikethrough past events
        else:
            lines.append(format_time(t))
    return "\n".join(lines)

# ---------------------------
# Handlers

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text(
            "Welcome! 🌟\nChoose a button below.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Wax", callback_data="wax")]])
        )
    elif update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            "Welcome! 🌟\nChoose a button below.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Wax", callback_data="wax")]])
        )

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
        f"**{event_name} Event**\n"
        f"Next event: {next_event_dt.strftime('%Y-%m-%d %H:%M')}\n"
        f"Time left: {delta_str}\n\n"
        f"Today's schedule:\n{schedule_text}"
    )

    buttons = [
        [InlineKeyboardButton("Notify Me", callback_data=f"notify_{event_key}")],
        [InlineKeyboardButton("Back", callback_data="wax")],
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="MarkdownV2")

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
        f"Select the event time you want to be notified about for **{event_name}**:",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="MarkdownV2"
    )

async def notify_time_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data  # format: notify_time_<event_key>_<HH:MM>
    parts = data.split("_")
    event_key = parts[2]
    event_time_str = parts[3]

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

        hh, mm = map(int, event_time_str.split(":"))
        event_time_obj = time(hh, mm)
        now = datetime.now()
        today = now.date()
        event_dt = datetime.combine(today, event_time_obj)
        if event_dt < now:
            event_dt += timedelta(days=1)
        notify_dt = event_dt - timedelta(minutes=minutes_before)
        if notify_dt < now:
            await update.message.reply_text("Notification time already passed for this event. Try again.")
            return

        user_notifications.setdefault(user_id, []).append((event_name, notify_dt, event_dt))
        await update.message.reply_text(
            f"Notification set for {event_name} at {event_time_str} "
            f"{minutes_before} minutes before (at {notify_dt.strftime('%Y-%m-%d %H:%M:%S')})"
        )
    else:
        await update.message.reply_text("Send /start to begin.")

async def back_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "back_to_main":
        buttons = [[InlineKeyboardButton("Wax", callback_data="wax")]]
        await query.edit_message_text("Welcome! 🌟\nChoose a button below.", reply_markup=InlineKeyboardMarkup(buttons))
    elif query.data == "wax":
        buttons = [
            [InlineKeyboardButton(event, callback_data=f"wax_event_{event.lower().replace(' ', '_')}")]
            for event in EVENTS.keys()
        ]
        buttons.append([InlineKeyboardButton("Back", callback_data="back_to_main")])
        await query.edit_message_text("Select an event:", reply_markup=InlineKeyboardMarkup(buttons))
    elif query.data == "back":
        # From Notify Me screen, go back to wax_event menu
        # We don't get event_key from data here, so just send main wax menu
        buttons = [
            [InlineKeyboardButton(event, callback_data=f"wax_event_{event.lower().replace(' ', '_')}")]
            for event in EVENTS.keys()
        ]
        buttons.append([InlineKeyboardButton("Back", callback_data="back_to_main")])
        await query.edit_message_text("Select an event:", reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await query.edit_message_text("Back button pressed but no handler for this state.")

# ---------------------------
# Notification checker background task

async def notification_checker():
    while True:
        now = datetime.now()
        to_remove = []
        for user_id, notif_list in user_notifications.items():
            for notif in notif_list:
                event_name, notify_time, event_time = notif
                if notify_time <= now:
                    try:
                        await application.bot.send_message(
                            chat_id=user_id,
                            text=(
                                f"🔔 Reminder: {event_name} event at {event_time.strftime('%H:%M')} is coming soon!"
                            ),
                        )
                    except Exception as e:
                        logging.error(f"Failed to send notification to {user_id}: {e}")
                    to_remove.append((user_id, notif))
        for user_id, notif in to_remove:
            if user_id in user_notifications and notif in user_notifications[user_id]:
                user_notifications[user_id].remove(notif)
                if not user_notifications[user_id]:
                    del user_notifications[user_id]
        await asyncio.sleep(30)

# ---------------------------
# FastAPI webhook endpoint

@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    json_update = await request.json()
    update = Update.de_json(json_update, application.bot)
    await application.update_queue.put(update)
    return {"ok": True}

# ---------------------------
# Register handlers

application.add_handler(CommandHandler("start", start))
application.add_handler(CallbackQueryHandler(wax_handler, pattern="^wax$"))
application.add_handler(CallbackQueryHandler(wax_event_handler, pattern="^wax_event_"))
application.add_handler(CallbackQueryHandler(notify_handler, pattern="^notify_"))
application.add_handler(CallbackQueryHandler(notify_time_handler, pattern="^notify_time_"))
application.add_handler(CallbackQueryHandler(back_handler, pattern="^(back_to_main|wax|back)$"))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# ---------------------------
# Startup event to run background task

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(notification_checker())

# ---------------------------
# Main runner

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
