import asyncio
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters, ConversationHandler
)

TOKEN = "YOUR_BOT_TOKEN"

# States for ConversationHandler
WAITING_MINUTES = 1

# User notification prefs: {chat_id: {"event": event_name, "minutes_before": int}}
user_notifications = {}

# Your events and their timing rules
def next_event_time(event_name: str) -> datetime:
    now = datetime.now()
    hour = now.hour
    minute = now.minute

    if event_name == "geyser":
        # Odd hour + 35 minutes
        next_hour = hour if hour % 2 == 1 and minute < 35 else (hour + 1) | 1
        dt = now.replace(hour=next_hour % 24, minute=35, second=0, microsecond=0)
        if dt <= now:
            dt += timedelta(hours=2)
        return dt

    elif event_name == "grandma":
        # Even hour + 5 minutes
        next_hour = hour if hour % 2 == 0 and minute < 5 else (hour + 1) & ~1
        dt = now.replace(hour=next_hour % 24, minute=5, second=0, microsecond=0)
        if dt <= now:
            dt += timedelta(hours=2)
        return dt

    elif event_name == "turtle":
        # Even hour + 20 minutes
        next_hour = hour if hour % 2 == 0 and minute < 20 else (hour + 1) & ~1
        dt = now.replace(hour=next_hour % 24, minute=20, second=0, microsecond=0)
        if dt <= now:
            dt += timedelta(hours=2)
        return dt

    else:
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Geyser", callback_data="event_geyser")],
        [InlineKeyboardButton("Grandma", callback_data="event_grandma")],
        [InlineKeyboardButton("Turtle", callback_data="event_turtle")],
    ]
    await update.message.reply_text("Hello! Select an event:", reply_markup=InlineKeyboardMarkup(keyboard))

async def event_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    event = query.data.replace("event_", "")

    next_time = next_event_time(event)
    if not next_time:
        await query.edit_message_text("No info for this event.")
        return

    now = datetime.now()
    diff = next_time - now
    minutes_left = int(diff.total_seconds() // 60)

    keyboard = [[InlineKeyboardButton("Notify me", callback_data=f"notify_{event}")]]
    await query.edit_message_text(
        text=f"Event: {event.capitalize()}\nStarts in: {minutes_left} minutes.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def notify_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    event = query.data.replace("notify_", "")

    context.user_data["notify_event"] = event
    await query.edit_message_text(
        f"How many minutes before the {event} event do you want to be notified?\nSend me a number."
    )

    return WAITING_MINUTES

async def received_minutes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    chat_id = update.message.chat_id
    event = context.user_data.get("notify_event")

    if not event:
        await update.message.reply_text("Something went wrong. Please try /start again.")
        return ConversationHandler.END

    if not text.isdigit() or int(text) <= 0:
        await update.message.reply_text("Please send a positive number.")
        return WAITING_MINUTES

    minutes_before = int(text)
    user_notifications[chat_id] = {"event": event, "minutes_before": minutes_before}

    await update.message.reply_text(
        f"Got it! I'll notify you {minutes_before} minutes before the {event} event."
    )

    return ConversationHandler.END

async def notify_users_periodically(app):
    while True:
        now = datetime.now()
        for chat_id, pref in list(user_notifications.items()):
            event = pref["event"]
            notify_before = pref["minutes_before"]

            event_time = next_event_time(event)
            if not event_time:
                continue

            notify_time = event_time - timedelta(minutes=notify_before)

            # If current time is within 1 minute of notify time, send notification and remove
            if notify_time <= now < notify_time + timedelta(minutes=1):
                try:
                    await app.bot.send_message(chat_id=chat_id, text=f"⏰ Reminder: {event.capitalize()} event starting soon!")
                except Exception as e:
                    print(f"Failed to send notification to {chat_id}: {e}")
                # Remove after notifying once, or comment this line if you want repeated notifications
                del user_notifications[chat_id]

        await asyncio.sleep(30)  # check every 30 seconds

async def on_startup(app):
    app.create_task(notify_users_periodically(app))

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(notify_button, pattern="^notify_")],
        states={
            WAITING_MINUTES: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_minutes)]
        },
        fallbacks=[],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(event_button, pattern="^event_"))
    app.add_handler(conv_handler)

    app.post_init = on_startup  # Start periodic notifier after startup

    app.run_polling()

if __name__ == "__main__":
    main()
