import os
import logging
import asyncpg
import asyncio
from urllib.parse import urlparse
from fastapi import FastAPI, Request
from contextlib import asynccontextmanager
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)
from fastapi.responses import JSONResponse

# Set up logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI()

# Global database pool
db_pool = None

# Global Telegram application
telegram_app = None

# Lifespan handler for startup and shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    global db_pool, telegram_app
    # Startup: Initialize database connection
    try:
        await init_db()
        logger.info("Database pool initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

    # Initialize Telegram bot
    telegram_app = (
        Application.builder()
        .token(os.getenv("TELEGRAM_BOT_TOKEN"))
        .build()
    )
    await telegram_app.initialize()
    await telegram_app.start()
    # Add command handlers during startup
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("help", help_command))
    logger.info("Telegram bot initialized")

    yield

    # Shutdown: Clean up resources
    if db_pool:
        await db_pool.close()
        logger.info("Database pool closed")
    if telegram_app:
        await telegram_app.stop()
        await telegram_app.shutdown()
        logger.info("Telegram bot stopped")

app.router.lifespan_context = lifespan

# Initialize database connection pool with retries
async def init_db():
    global db_pool
    DATABASE_URL = os.getenv("DATABASE_URL")
    if not DATABASE_URL:
        logger.error("DATABASE_URL environment variable is not set")
        raise ValueError("DATABASE_URL environment variable is not set")
    
    retries = 3
    for attempt in range(retries):
        try:
            # Parse the URL for explicit parameter passing
            parsed = urlparse(DATABASE_URL)
            db_pool = await asyncpg.create_pool(
                host=parsed.hostname,
                port=parsed.port,
                user=parsed.username,
                password=parsed.password,
                database=parsed.path.lstrip('/'),
                ssl="require",
                min_size=1,
                max_size=10,
                timeout=120  # Increased timeout to 120 seconds
            )
            logger.info("Database pool created successfully")
            return
        except asyncpg.exceptions.ConnectionFailureError as e:
            logger.error(f"Attempt {attempt + 1} - Connection failure: {e}")
        except asyncpg.exceptions.TimeoutError as e:
            logger.error(f"Attempt {attempt + 1} - Connection timed out: {e}")
        except Exception as e:
            logger.error(f"Attempt {attempt + 1} - Unexpected error: {e}")
        
        if attempt < retries - 1:
            await asyncio.sleep(5)  # Wait 5 seconds before retrying
        else:
            raise Exception("Failed to initialize database after multiple attempts")

# Example database query (modify as needed)
async def store_user(user_id: int, username: str):
    async with db_pool.acquire() as connection:
        await connection.execute(
            """
            INSERT INTO users (user_id, username)
            VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE
            SET username = $2
            """,
            user_id,
            username,
        )

# Telegram command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await store_user(user.id, user.username or f"user_{user.id}")
    await update.message.reply_text("Welcome to SkyClock Bot! Use /help to see commands.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Available commands:\n/start - Start the bot\n/help - Show this message")

# FastAPI webhook endpoint
@app.post("/webhook")
async def webhook(request: Request):
    global telegram_app
    try:
        # Get raw JSON body
        json_data = await request.json()
        # Convert to Telegram Update object
        update = Update.de_json(json_data, telegram_app.bot)
        if update:
            await telegram_app.process_update(update)
        return JSONResponse(content={"status": "ok"})
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return JSONResponse(content={"status": "error"}, status_code=500)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)