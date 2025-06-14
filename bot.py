import os import asyncio import logging from datetime import datetime, timedelta

from fastapi import FastAPI, Request from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update from telegram.constants import ParseMode from telegram.ext import (Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters) from apscheduler.schedulers.asyncio import AsyncIOScheduler import pytz import asyncpg

BOT_TOKEN = os.getenv("BOT_TOKEN") DATABASE_URL = os.getenv("DATABASE_URL") PORT = int(os.getenv("PORT", "10000"))

logging.basicConfig(level=logging.INFO)

DB Setup

db_pool = None

async def init_db(): global db_pool db_pool = await asyncpg.create_pool(DATABASE_URL) async with db_pool.acquire() as conn: await conn.execute(""" CREATE TABLE IF NOT EXISTS users ( user_id BIGINT PRIMARY KEY, timezone TEXT ); """) await conn.execute(""" CREATE TABLE IF NOT EXISTS reminders ( id SERIAL PRIMARY KEY, user_id BIGINT, event TEXT, event_time TEXT, minutes_before INTEGER, timezone TEXT, job_id TEXT UNIQUE ); """)

async def get_user(user_id): async with db_pool.acquire() as conn: return await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)

async def add_user(user_id, timezone): async with db_pool.acquire() as conn: await conn.execute(""" INSERT INTO users (user_id, timezone) VALUES ($1, $2) ON CONFLICT (user_id) DO UPDATE SET timezone = EXCLUDED.timezone """, user_id, timezone)

FastAPI + Telegram

app = FastAPI() telegram_app = Application.builder().token(BOT_TOKEN).build() scheduler = AsyncIOScheduler()

Event times (12-hr format)

EVENT_TIMES = { "grandma": ["02:05 AM", "04:05 AM", "06:05 AM", "08:05 AM", "10:05 AM", "12:05 PM", "02:05 PM", "04:05 PM", "06:05 PM", "08:05 PM", "10:05 PM", "12:05 AM"], "geyser":  ["01:35 AM", "03:35 AM", "05:35 AM", "07:35 AM", "09:35 AM", "11:35 AM", "01:35 PM", "03:35 PM", "05:35 PM", "07:35 PM", "09:35 PM", "11:35 PM"], "turtle":  ["02:20 AM", "04:20 AM", "06:20 AM", "08:20 AM", "10:20 AM", "12:20 PM", "02:20 PM", "04:20 PM", "06:20 PM", "08:20 PM", "10:20 PM", "12:20 AM"] }

Keyboards

def main_menu_keyboard(): return InlineKeyboardMarkup([ [ InlineKeyboardButton("\ud83d\udce6 Wax", callback_data="wax"), InlineKeyboardButton("\ud83e\udde9 Shards", callback_data="shards") ] ])

def wax_keyboard(): return InlineKeyboardMarkup([ [InlineKeyboardButton("\ud83d\udc75 Grandma", callback_data="wax_grandma")], [InlineKeyboardButton("\ud83c\udf0b Geyser", callback_data="wax_geyser")], [InlineKeyboardButton("\ud83d\udc22 Turtle", callback_data="wax_turtle")], [InlineKeyboardButton("\u2b05\ufe0f Back", callback_data="back_main")] ])

def wax_event_keyboard(event_type: str): return InlineKeyboardMarkup([ [InlineKeyboardButton("\ud83d\udd14 Notify Me", callback_data=f"notify_{event_type}")], [InlineKeyboardButton("\ud83d\udd15 Turn Off Notification", callback_data=f"cancel_notify_{event_type}")], [InlineKeyboardButton("\u2b05\ufe0f Back", callback_data="wax")] ])

Handlers

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE): user_id = update.effective_user.id user = await get_user(user_id)

if user is None:
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("\ud83c\uddf2\ud83c\uddf2 Myanmar", callback_data="tz_Myanmar")]
    ])
    await update.message.reply_text("\ud83d\udc4b Welcome! Please choose your timezone:", reply_markup=keyboard)
else:
    await update.message.reply_text("\ud83d\udc4b What do you want to check?", reply_markup=main_menu_keyboard())

async def timezone_selection(update: Update, context: ContextTypes.DEFAULT_TYPE): query = update.callback_query await query.answer() user_id = query.from_user.id tz = "Asia/Yangon" if query.data == "tz_Myanmar" else None

if tz:
    await add_user(user_id, tz)
    await query.edit_message_text("\u2705 Timezone set! Use /start to continue.")
else:
    await query.edit_message_text("\u274c Unsupported timezone.")

async def handle_wax(update: Update, context: ContextTypes.DEFAULT_TYPE): query = update.callback_query await query.answer() await query.edit_message_text("Choose a Wax event:", reply_markup=wax_keyboard())

async def wax_event_handler(update: Update, context: ContextTypes.DEFAULT_TYPE): query = update.callback_query await query.answer() event = query.data.split("_")[1] times = EVENT_TIMES.get(event, []) formatted = "\n".join(f"\u2022 {t}" for t in times) await query.edit_message_text( f"\ud83d\udcc5 Next {event.title()} times today:\n{formatted}\n\n\ud83d\udd14 Want a reminder?", reply_markup=wax_event_keyboard(event) )

async def notify_handler(update: Update, context: ContextTypes.DEFAULT_TYPE): query = update.callback_query await query.answer() event = query.data.split("_")[1] times = EVENT_TIMES.get(event, []) context.user_data['event_to_notify'] = event text = "\n".join(f"\u2022 {t}" for t in times) await query.edit_message_text(f"Please reply with the event time you want a reminder for:\n{text}")

async def cancel_notification_handler(update: Update, context: ContextTypes.DEFAULT_TYPE): query = update.callback_query await query.answer() user_id = query.from_user.id event_type = query.data.replace("cancel_notify_", "") async with db_pool.acquire() as conn: rows = await conn.fetch("SELECT job_id FROM reminders WHERE user_id = $1 AND event = $2", user_id, event_type) for row in rows: scheduler.remove_job(row['job_id']) await conn.execute("DELETE FROM reminders WHERE user_id = $1 AND event = $2", user_id, event_type) await query.edit_message_text(f"\ud83d\udd15 Notifications for {event_type.title()} turned off.", reply_markup=wax_event_keyboard(event_type))

async def schedule_reminder(user_id, event, event_time_str, minutes_before, timezone_str): tz = pytz.timezone(timezone_str) now = datetime.now(tz) event_dt = datetime.strptime(event_time_str, "%I:%M %p").replace(year=now.year, month=now.month, day=now.day) event_dt = tz.localize(event_dt) if event_dt < now: event_dt += timedelta(days=1) reminder_time = event_dt - timedelta(minutes=minutes_before) job_id = f"{user_id}{event}{event_time_str.replace(':', '')}"

async def send_reminder():
    await telegram_app.bot.send_message(chat_id=user_id, text=f"\ud83d\udd14 Reminder: {event.title()} is at {event_time_str}!")

scheduler.add_job(send_reminder, 'date', run_date=reminder_time, id=job_id)

async with db_pool.acquire() as conn:
    await conn.execute("""
        INSERT INTO reminders (user_id, event, event_time, minutes_before, timezone, job_id)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (job_id) DO NOTHING
    """, user_id, event, event_time_str, minutes_before, timezone_str, job_id)

async def load_reminders(): async with db_pool.acquire() as conn: rows = await conn.fetch("SELECT * FROM reminders") for row in rows: await schedule_reminder(row['user_id'], row['event'], row['event_time'], row['minutes_before'], row['timezone'])

async def handle_reply(update: Update, context: ContextTypes.DEFAULT_TYPE): user_id = update.effective_user.id event = context.user_data.get('event_to_notify') event_time = update.message.text.strip() user = await get_user(user_id) if not user or event not in EVENT_TIMES or event_time not in EVENT_TIMES[event]: await update.message.reply_text("\u274c Invalid time. Try again.") return await update.message.reply_text("How many minutes before the event would you like to be reminded?") context.user_data['event_time'] = event_time context.user_data['stage'] = 'awaiting_minutes'

async def handle_minutes_reply(update: Update, context: ContextTypes.DEFAULT_TYPE): user_id = update.effective_user.id try: minutes = int(update.message.text.strip()) except: await update.message.reply_text("\u274c Please enter a valid number.") return event = context.user_data.get('event_to_notify') event_time = context.user_data.get('event_time') user = await get_user(user_id) await schedule_reminder(user_id, event, event_time, minutes, user['timezone']) await update.message.reply_text(f"\u2705 Reminder set for {event.title()} at {event_time}, {minutes} minutes before.") context.user_data.clear()

async def list_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE): user_id = update.effective_user.id async with db_pool.acquire() as conn: rows = await conn.fetch("SELECT id, event, event_time, minutes_before FROM reminders WHERE user_id = $1", user_id) if not rows: await update.message.reply_text("\ud83d\udcc3 You have no scheduled reminders.") return for row in rows: text = ( f"\ud83d\udd14 <b>{row['event'].title()}</b>\n" f"\ud83d\udd52 Event Time: <b>{row['event_time']}</b>\n" f"\u23f1 Notify: <b>{row['minutes_before']} mins before</b>" ) keyboard = InlineKeyboardMarkup([ [InlineKeyboardButton("\u274c Cancel", callback_data=f"cancel_one_{row['id']}")] ]) await update.message.reply_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)

async def cancel_one_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE): query = update.callback_query await query.answer() reminder_id = int(query.data.replace("cancel_one_", "")) async with db_pool.acquire() as conn: row = await conn.fetchrow("SELECT job_id FROM reminders WHERE id = $1", reminder_id) if row: scheduler.remove_job(row['job_id']) await conn.execute("DELETE FROM reminders WHERE id = $1", reminder_id) await query.edit_message_text("\u274c Reminder canceled.") else: await query.edit_message_text("\u26a0\ufe0f Reminder not found.")

Handlers registration

telegram_app.add_handler(CommandHandler("start", start)) telegram_app.add_handler(CommandHandler("reminders", list_reminders)) telegram_app.add_handler(CallbackQueryHandler(timezone_selection, pattern="^tz_")) telegram_app.add_handler(CallbackQueryHandler(handle_wax, pattern="^wax$")) telegram_app.add_handler(CallbackQueryHandler(wax_event_handler, pattern="^wax_(grandma|geyser|turtle)$")) telegram_app.add_handler(CallbackQueryHandler(notify_handler, pattern="^notify_")) telegram_app.add_handler(CallbackQueryHandler(cancel_notification_handler, pattern="^cancel_notify_")) telegram_app.add_handler(CallbackQueryHandler(cancel_one_reminder, pattern="^cancel_one_")) telegram_app.add_handler(MessageHandler(filters.TEXT & filters.TEXT, lambda u, c: handle_minutes_reply(u, c) if c.user_data.get('stage') == 'awaiting_minutes' else handle_reply(u, c)))

FastAPI events

@app.on_event("startup") async def on_startup(): await init_db() await telegram_app.initialize() await telegram_app.start() scheduler.start() await load_reminders()

@app.on_event("shutdown") async def on_shutdown(): await telegram_app.stop() await telegram_app.shutdown() await db_pool.close()

@app.post("/webhook") async def telegram_webhook(req: Request): data = await req.json() update = Update.de_json(data, telegram_app.bot) await telegram_app.process_update(update) return {"status": "ok"}

@app.get("/") async def root(): return {"status": "running"}

if name == "main": import uvicorn uvicorn.run("bot:app", host="0.0.0.0", port=PORT)

