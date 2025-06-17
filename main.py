import os
import re
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager

import pytz
from fastapi import FastAPI, Request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)
from psycopg_pool import AsyncConnectionPool

# === CONFIGURATION ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_IDS", "").split(",") if id.strip()]
IS_RENDER = "RENDER" in os.environ
PORT = int(os.getenv("PORT", 10000))

# === LOGGING SETUP ===
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# === CONSTANTS ===
MYANMAR_OFFSET = timedelta(hours=6, minutes=30)  # UTC+6:30
EVENT_TIMES = {
    "grandma": {"minute": 5, "hour_parity": "even"},
    "geyser": {"minute": 35, "hour_parity": "odd"},
    "turtle": {"minute": 20, "hour_parity": "even"}
}

# === DATABASE POOL SETUP ===
pool = AsyncConnectionPool(
    conninfo=DATABASE_URL,
    min_size=1,
    max_size=5,
    open=False
)

# Create application instance
application = None  # Will be initialized later

# === FASTAPI LIFESPAN CONTEXT ===
@asynccontextmanager
async def lifespan(app: FastAPI):
    global application
    
    # Initialize bot application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers to application
    await add_handlers(application)
    
    # Startup
    await pool.open()
    await pool.wait()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    tz_offset TEXT NOT NULL DEFAULT '+00:00',
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE TABLE IF NOT EXISTS notifications (
                    user_id BIGINT REFERENCES users(user_id),
                    event TEXT,
                    last_notified TIMESTAMPTZ,
                    PRIMARY KEY (user_id, event)
                );
                CREATE INDEX IF NOT EXISTS idx_user_id ON users(user_id);
            """)
    logger.info("✅ Database initialized")
    
    # Initialize and start bot application
    await application.initialize()
    await application.start()
    
    # Set webhook for production
    if IS_RENDER and WEBHOOK_URL:
        try:
            await application.bot.set_webhook(WEBHOOK_URL)
            logger.info(f"✅ Webhook set to {WEBHOOK_URL}")
        except Exception as e:
            logger.error(f"❌ Failed to set webhook: {e}")
    else:
        logger.info("🚫 Webhook not set (running in development mode)")
    
    # Start job queue for local development
    if not IS_RENDER and application.job_queue:
        application.job_queue.run_repeating(
            check_scheduled_events,
            interval=60,
            first=10
        )
        logger.info("⏰ Started local job scheduler")
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down application...")
    if IS_RENDER and WEBHOOK_URL:
        try:
            await application.bot.delete_webhook()
            logger.info("✅ Webhook deleted")
        except Exception as e:
            logger.error(f"❌ Failed to delete webhook: {e}")
    await application.stop()
    await application.shutdown()
    await pool.close()
    logger.info("✅ Application shut down")

app = FastAPI(lifespan=lifespan)

# === DATABASE OPERATIONS ===
async def set_tz_offset(user_id: int, offset: str):
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                INSERT INTO users (user_id, tz_offset)
                VALUES (%s, %s)
                ON CONFLICT (user_id)
                DO UPDATE SET tz_offset = EXCLUDED.tz_offset;
            """, (user_id, offset))

async def get_tz_offset(user_id: int) -> str:
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT tz_offset FROM users WHERE user_id = %s;",
                (user_id,)
            )
            row = await cur.fetchone()
            return row[0] if row else "+00:00"

async def set_notification(user_id: int, event: str):
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                INSERT INTO notifications (user_id, event)
                VALUES (%s, %s)
                ON CONFLICT (user_id, event) DO NOTHING;
            """, (user_id, event))

async def get_all_user_ids():
    """Get all user IDs from the database"""
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT user_id FROM users;")
            rows = await cur.fetchall()
            return [row[0] for row in rows]

# === SKY TIME UTILITIES ===
def get_sky_time() -> datetime:
    """Get current Sky time (UTC)"""
    return datetime.utcnow().replace(tzinfo=timezone.utc)

def to_myanmar_time(utc_time: datetime) -> datetime:
    """Convert UTC time to Myanmar time (UTC+6:30)"""
    return utc_time + MYANMAR_OFFSET

def format_12h(dt: datetime) -> str:
    """Format datetime to 12-hour without leading zero"""
    return dt.strftime("%I:%M %p").lstrip("0")

def next_occurrence(base: datetime, minute: int, hour_parity: str) -> datetime:
    """Calculate next occurrence with parity constraint"""
    candidate = base.replace(minute=minute, second=0, microsecond=0)
    if candidate <= base:
        candidate += timedelta(hours=1)
    
    # Adjust for parity
    while (hour_parity == "even" and candidate.hour % 2 != 0) or \
          (hour_parity == "odd" and candidate.hour % 2 == 0):
        candidate += timedelta(hours=1)
    
    return candidate

def get_next_event_time(event: str) -> tuple:
    """Returns (utc_time, myanmar_time, remaining_minutes)"""
    now_utc = get_sky_time()
    config = EVENT_TIMES[event]
    
    # Calculate next occurrence in UTC
    next_utc = next_occurrence(now_utc, config["minute"], config["hour_parity"])
    
    # Convert to Myanmar time
    next_myanmar = to_myanmar_time(next_utc)
    
    # Calculate remaining minutes
    remaining_minutes = int((next_utc - now_utc).total_seconds() // 60)
    
    return next_utc, next_myanmar, remaining_minutes

# === ADMIN FEATURES ===
async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin menu"""
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Access denied. You are not an admin.")
        return
        
    keyboard = [
        [InlineKeyboardButton("📢 Broadcast to All", callback_data='broadcast_all')],
        [InlineKeyboardButton("✉️ Message to User", callback_data='message_user')],
        [InlineKeyboardButton("⬅️ Back to Main", callback_data='back_to_main')]
    ]
    await update.message.reply_text(
        "Admin Menu:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /admin command"""
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Access denied. You are not an admin.")
        return
        
    await admin_menu(update, context)

async def start_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Initiate broadcast process"""
    if update.effective_user.id not in ADMIN_IDS:
        await update.callback_query.answer("❌ Access denied")
        return
        
    await update.callback_query.answer()
    context.user_data["action"] = "broadcast"
    await update.callback_query.edit_message_text(
        "📝 Please enter the message you want to broadcast to all users:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data='cancel_action')]])
    )

async def start_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Initiate message to specific user"""
    if update.effective_user.id not in ADMIN_IDS:
        await update.callback_query.answer("❌ Access denied")
        return
        
    await update.callback_query.answer()
    context.user_data["action"] = "user_message"
    await update.callback_query.edit_message_text(
        "📝 Please enter the user ID followed by the message:\nExample: 123456789 Hello!",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data='cancel_action')]])
    )

async def handle_admin_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process admin text input"""
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Access denied. You are not an admin.")
        return
        
    action = context.user_data.get("action")
    text = update.message.text.strip()
    
    if not action:
        await update.message.reply_text("❌ No action in progress. Use /admin to start.")
        return
        
    if action == "broadcast":
        # Broadcast to all users
        user_ids = await get_all_user_ids()
        success = 0
        failed = 0
        
        for user_id in user_ids:
            try:
                await application.bot.send_message(
                    chat_id=user_id,
                    text=f"📢 <b>Broadcast from Admin:</b>\n\n{text}",
                    parse_mode="HTML"
                )
                success += 1
            except Exception:
                failed += 1
            await asyncio.sleep(0.1)  # Rate limiting
        
        await update.message.reply_text(
            f"✅ Broadcast completed!\n"
            f"• Success: {success} users\n"
            f"• Failed: {failed} users"
        )
        del context.user_data["action"]
        
    elif action == "user_message":
        # Message to specific user
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            await update.message.reply_text("❌ Invalid format. Please use: user_id message")
            return
            
        try:
            user_id = int(parts[0])
            message = parts[1]
            
            await application.bot.send_message(
                chat_id=user_id,
                text=f"✉️ <b>Message from Admin:</b>\n\n{message}",
                parse_mode="HTML"
            )
            await update.message.reply_text(f"✅ Message sent to user {user_id}")
        except ValueError:
            await update.message.reply_text("❌ Invalid user ID. Must be a number.")
        except Exception as e:
            await update.message.reply_text(f"❌ Failed to send message: {e}")
        finally:
            del context.user_data["action"]
            
async def cancel_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel current admin action"""
    if "action" in context.user_data:
        del context.user_data["action"]
    await update.callback_query.answer("Action cancelled")
    await admin_menu(update, context)

# === BOT COMMANDS AND CALLBACKS ===
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
    await set_tz_offset(user_id, "+06:30")
    await update.callback_query.edit_message_text("✅ Timezone set to Myanmar Time (+06:30).")
    await show_main_menu(update, context)

async def enter_manual_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("📥 Please type your timezone offset manually (e.g. `+06:30`).")

async def handle_timezone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    offset = update.message.text.strip()
    if not re.match(r"^[+-](0[0-9]|1[0-3]):[0-5][0-9]$", offset):
        await update.message.reply_text("❌ Invalid format. Use format like `+06:30` or `-05:00`.")
        return
    await set_tz_offset(user_id, offset)
    await update.message.reply_text(f"✅ Timezone set to UTC{offset}")
    await show_main_menu(update, context)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🕰️ Sky Clock", callback_data='sky_clock')],
        [InlineKeyboardButton("🕯️ Wax Events", callback_data='wax')]
    ]
    
    # Add admin menu button for admins
    if update.effective_user.id in ADMIN_IDS:
        keyboard.append([InlineKeyboardButton("👑 Admin Panel", callback_data='admin_menu')])
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            "Main Menu:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text(
            "Main Menu:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def show_sky_clock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sky_time = get_sky_time()
    myanmar_time = to_myanmar_time(sky_time)
    
    message = (
        "⏰ <b>Current Sky Time</b>\n"
        f"🌐 <b>UTC:</b> {sky_time.strftime('%H:%M')}\n"
        f"🇲🇲 <b>Myanmar:</b> {format_12h(myanmar_time)}\n\n"
        "Sky Time is based on UTC. All events follow this clock."
    )
    
    keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data='back_to_main')]]
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

async def show_wax_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Grandma 👵", callback_data='grandma')],
        [InlineKeyboardButton("Geyser 🌋", callback_data='geyser')],
        [InlineKeyboardButton("Turtle 🐢", callback_data='turtle')],
        [InlineKeyboardButton("⬅️ Back", callback_data='back_to_main')]
    ]
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        "Choose a wax event:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await show_main_menu(update, context)

async def handle_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    event = update.callback_query.data
    event_names = {
        "grandma": "Grandma 👵",
        "geyser": "Geyser 🌋",
        "turtle": "Turtle 🐢"
    }
    
    # Get event times in UTC and Myanmar time
    _, next_myanmar, remaining_minutes = get_next_event_time(event)
    
    # Format the message
    message = (
        f"<b>{event_names[event]}</b>\n"
        f"🕒 <b>Myanmar Time:</b> {format_12h(next_myanmar)}\n"
        f"⏱️ <b>Starts in:</b> {remaining_minutes} minutes\n\n"
        "Click 🔔 to get notified 5 minutes before the event!"
    )
    
    keyboard = [
        [InlineKeyboardButton("🔔 Notify Me", callback_data=f'notify_{event}')],
        [InlineKeyboardButton("⬅️ Back", callback_data='wax')]
    ]
    
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

async def handle_notify_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    event = update.callback_query.data.split('_')[1]
    await set_notification(user_id, event)
    await update.callback_query.answer("🔔 You'll get notified 5 minutes before the event!")

# === SCHEDULED EVENT CHECKING ===
async def check_scheduled_events(context: ContextTypes.DEFAULT_TYPE):
    logger.info("⏳ Checking scheduled events...")
    now_utc = get_sky_time()
    notify_before = timedelta(minutes=5)

    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT user_id, event FROM notifications;")
            notifications = await cur.fetchall()
            
            for user_id, event in notifications:
                next_utc, next_myanmar, _ = get_next_event_time(event)
                
                # Check if it's time to notify (5 minutes before event)
                if next_utc - notify_before <= now_utc < next_utc:
                    try:
                        # Calculate remaining minutes
                        remaining = int((next_utc - now_utc).total_seconds() // 60)
                        
                        await context.bot.send_message(
                            chat_id=user_id,
                            text=(
                                f"⏰ <b>Reminder: {event.capitalize()} starts soon!</b>\n"
                                f"🕒 <b>Myanmar Time:</b> {format_12h(next_myanmar)}\n"
                                f"⏱️ <b>Starting in:</b> {remaining} minutes"
                            ),
                            parse_mode="HTML"
                        )
                        logger.info(f"✅ Notification sent to {user_id} for {event}")
                    except Exception as e:
                        logger.error(f"❌ Notification failed for {user_id}: {e}")

# === ADD HANDLERS FUNCTION ===
async def add_handlers(app: Application):
    """Register all handlers with the application"""
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", handle_admin_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_timezone))
    app.add_handler(CallbackQueryHandler(set_myanmar_timezone, pattern="^set_myanmar$"))
    app.add_handler(CallbackQueryHandler(enter_manual_callback, pattern="^enter_manual$"))
    app.add_handler(CallbackQueryHandler(show_sky_clock, pattern="^sky_clock$"))
    app.add_handler(CallbackQueryHandler(show_wax_menu, pattern="^wax$"))
    app.add_handler(CallbackQueryHandler(back_to_main, pattern="^back_to_main$"))
    app.add_handler(CallbackQueryHandler(admin_menu, pattern="^admin_menu$"))
    app.add_handler(CallbackQueryHandler(start_broadcast, pattern="^broadcast_all$"))
    app.add_handler(CallbackQueryHandler(start_user_message, pattern="^message_user$"))
    app.add_handler(CallbackQueryHandler(cancel_action, pattern="^cancel_action$"))
    app.add_handler(CallbackQueryHandler(handle_event, pattern="^(grandma|geyser|turtle)$"))
    app.add_handler(CallbackQueryHandler(handle_notify_callback, pattern="^notify_.*$"))
    logger.info("✅ All handlers registered")

# === FASTAPI ROUTES ===
@app.get("/")
async def root():
    return {"status": "SkyClock Bot is running."}

@app.get("/health")
async def health_check():
    return {
        "status": "OK",
        "database": "connected" if pool.check() else "disconnected",
        "time": datetime.now(timezone.utc).isoformat()
    }

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    try:
        logger.info(f"📩 Received webhook update")
        if application is None:
            logger.error("Application not initialized yet")
            return {"ok": False}
            
        update = Update.de_json(data, application.bot)
        logger.info(f"🔄 Processing update ID: {update.update_id}")
        await application.process_update(update)
        logger.info(f"✅ Processed update ID: {update.update_id}")
    except Exception as e:
        logger.error(f"❌ Failed to process update: {e}", exc_info=True)
    return {"ok": True}

# === MAIN ENTRY POINT ===
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")