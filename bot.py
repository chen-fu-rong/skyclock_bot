from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler

user_data = {}
scheduler = BackgroundScheduler()
scheduler.start()

# Event time generators
def get_today_event_times(pattern):
    now = datetime.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    times = []

    for hour in range(24):
        if pattern == "geyser" and hour % 2 == 1:
            times.append(today.replace(hour=hour, minute=35))
        elif pattern == "grandma" and hour % 2 == 0:
            times.append(today.replace(hour=hour, minute=5))
        elif pattern == "turtle" and hour % 2 == 0:
            times.append(today.replace(hour=hour, minute=20))
    return [t for t in times if t > now]

# /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    name = user.first_name
    user_data[user.id] = {"name": name}

    keyboard = [[InlineKeyboardButton("Events", callback_data="events")]]
    await update.message.reply_text(f"Hi {name}! Please choose an event.", reply_markup=InlineKeyboardMarkup(keyboard))

# Events menu
async def events_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("Geyser", callback_data="event_geyser")],
        [InlineKeyboardButton("Grandma", callback_data="event_grandma")],
        [InlineKeyboardButton("Turtle", callback_data="event_turtle")],
        [InlineKeyboardButton("Dreams Skater", callback_data="event_dreams")]
    ]
    await query.edit_message_text("Choose an event:", reply_markup=InlineKeyboardMarkup(keyboard))

# Show event info and Notify button
async def handle_event_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    name = user_data.get(user_id, {}).get("name", "User")

    event_type = query.data.replace("event_", "")
    if event_type == "dreams":
        await query.edit_message_text(f"{name}, Dreams Skater has no notifications yet.")
        return

    events = get_today_event_times(event_type)
    next_event = events[0]
    mins = int((next_event - datetime.now()).total_seconds() // 60)

    keyboard = [[InlineKeyboardButton("Notify", callback_data=f"notify_{event_type}")]]
    await query.edit_message_text(
        f"{name}, next {event_type.title()} event is at {next_event.strftime('%H:%M')}.\n"
        f"That's in {mins} minutes.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# Show event times when Notify is clicked
async def notify_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    event_type = query.data.replace("notify_", "")
    context.user_data["notify_type"] = event_type

    buttons = []
    for t in get_today_event_times(event_type):
        time_str = t.strftime("%H:%M")
        callback_data = f"choose_{event_type}_{t.strftime('%H%M')}"
        buttons.append([InlineKeyboardButton(time_str, callback_data=callback_data)])

    await query.edit_message_text(
        f"Select a {event_type.title()} event time:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# Handle event time selection
async def time_selection_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    data = query.data.replace("choose_", "")  # e.g., geyser_1335
    event_type, timestr = data.split("_")
    event_time = datetime.now().replace(hour=int(timestr[:2]), minute=int(timestr[2:]), second=0, microsecond=0)
    if event_time < datetime.now():
        event_time += timedelta(days=1)

    user_data[user_id]["selected_event_time"] = event_time
    context.user_data["awaiting_notify_minutes"] = True

    await query.edit_message_text(
        f"How many minutes before {event_time.strftime('%H:%M')} should I notify you?"
    )

# Receive user's minutes and schedule
async def receive_notify_minutes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.user_data.get("awaiting_notify_minutes"):
        return

    try:
        mins = int(update.message.text)
        event_time = user_data[user_id]["selected_event_time"]
        name = user_data[user_id]["name"]

        notify_time = event_time - timedelta(minutes=mins)
        scheduler.add_job(
            send_notification,
            trigger="date",
            run_date=notify_time,
            args=[context.bot, user_id, name, event_time.strftime('%H:%M')],
            id=f"notify_{user_id}_{event_time.strftime('%H%M')}",
            replace_existing=True
        )

        await update.message.reply_text(f"✅ I’ll notify you {mins} minutes before the event at {event_time.strftime('%H:%M')}.")
        context.user_data["awaiting_notify_minutes"] = False

    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number.")

# Send notification
async def send_notification(bot, user_id, name, event_time_str):
    await bot.send_message(
        chat_id=user_id,
        text=f"🔔 Hey {name}, this is your reminder: the event is at {event_time_str}!"
    )

# Main app
if __name__ == "__main__":
   import os
app = ApplicationBuilder().token(os.getenv("BOT_TOKEN")).build()


    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(events_menu, pattern="^events$"))
    app.add_handler(CallbackQueryHandler(handle_event_choice, pattern="^event_"))
    app.add_handler(CallbackQueryHandler(notify_handler, pattern="^notify_"))
    app.add_handler(CallbackQueryHandler(time_selection_handler, pattern="^choose_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_notify_minutes))

    print("Bot is running...")
    app.run_polling()
