import os
import asyncio
import logging
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (Application, CommandHandler, CallbackQueryHandler,
                          ContextTypes, MessageHandler, filters)

from database import add_user, get_user_timezone, update_user_timezone, save_notification, get_due_notifications
from utils import parse_timezone_offset, format_event_time, get_next_event_time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # e.g. https://yourdomain.com/webhook
PORT = int(os.getenv("PORT", 10000))

telegram_app = Application.builder().token(BOT_TOKEN).build()

@telegram_app.command_handler()
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    add_user(user_id)
    user_tz = get_user_timezone(user_id)

    if user_tz:
        await show_main_menu(update, context)
    else:
        buttons = [
            [InlineKeyboardButton("🇲🇲 Myanmar", callback_data="tz:Asia/Yangon")],
        ]
        await update.message.reply_text(
            "Welcome! Please choose your timezone or type it manually (e.g. UTC+6:30):",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🕯 Wax", callback_data="wax")]]
    await update.message.reply_text("Choose an option:", reply_markup=InlineKeyboardMarkup(keyboard))

@telegram_app.callback_query_handler()
async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data.startswith("tz:"):
        tz = query.data.split(":")[1]
        update_user_timezone(user_id, tz)
        await query.edit_message_text("✅ Timezone set successfully!")
        await show_main_menu(update, context)

    elif query.data == "wax":
        keyboard = [
            [InlineKeyboardButton("👵 Grandma", callback_data="wax:grandma")],
            [InlineKeyboardButton("🐢 Turtle", callback_data="wax:turtle")],
            [InlineKeyboardButton("🌋 Geyser", callback_data="wax:geyser")],
            [InlineKeyboardButton("🔙 Back", callback_data="back:main")],
        ]
        await query.edit_message_text("Choose wax event:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data.startswith("wax:"):
        event = query.data.split(":")[1]
        tz = get_user_timezone(user_id) or "Asia/Yangon"
        next_time = get_next_event_time(event, tz)
        now = datetime.now(parse_timezone_offset(tz))
        diff = next_time - now
        keyboard = [
            [InlineKeyboardButton("🔔 Notify Me", callback_data=f"notify:{event}")],
            [InlineKeyboardButton("🔙 Back", callback_data="wax")],
        ]
        await query.edit_message_text(
            f"Next {event.capitalize()} is at {format_event_time(next_time)}\n⏳ Time left: {str(diff).split('.')[0]}",
            reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data.startswith("notify:"):
        event = query.data.split(":")[1]
        keyboard = [
            [InlineKeyboardButton("1 min before", callback_data=f"setnotify:{event}:1")],
            [InlineKeyboardButton("5 min before", callback_data=f"setnotify:{event}:5")],
            [InlineKeyboardButton("10 min before", callback_data=f"setnotify:{event}:10")],
            [InlineKeyboardButton("🔙 Back", callback_data=f"wax:{event}")],
        ]
        await query.edit_message_text("How many minutes before should I notify you?", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data.startswith("setnotify:"):
        _, event, minutes = query.data.split(":")
        tz = get_user_timezone(user_id) or "Asia/Yangon"
        next_time = get_next_event_time(event, tz)
        notify_time = next_time - timedelta(minutes=int(minutes))
        save_notification(user_id, event, notify_time)
        await query.edit_message_text(f"🔔 Got it! I will remind you {minutes} minutes before {event}.")

    elif query.data == "back:main":
        await show_main_menu(update, context)

@telegram_app.message_handler(filters.TEXT & (~filters.COMMAND))
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    tz = parse_timezone_offset(text)
    if tz:
        update_user_timezone(user_id, tz.zone)
        await update.message.reply_text("✅ Timezone set successfully!")
        await show_main_menu(update, context)
    else:
        await update.message.reply_text("❌ Invalid timezone. Please try again (e.g. UTC+6:30)")

# === FastAPI app ===

@asynccontextmanager
async def lifespan(app: FastAPI):
    await telegram_app.initialize()
    await telegram_app.start()
    yield
    await telegram_app.stop()

app = FastAPI(lifespan=lifespan)

@app.post("/webhook")
async def webhook(request: Request):
    update = Update.de_json(await request.json(), telegram_app.bot)
    await telegram_app.process_update(update)
    return {"ok": True}

@app.get("/")
def root():
    return {"message": "SkyClock Bot is live!"}
