import os
import logging
import asyncpg
from fastapi import FastAPI
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

# Lifespan handler for startup and shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    global db_pool
    # Startup: Initialize database connection
    try:
        await init_db()
        logger.info("Database pool initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

    # Initialize Telegram bot
    global telegram_app
    telegram_app = (
        Application.builder()
        .token(os.getenv("TELEGRAM_BOT_TOKEN"))
        .build()
    )
    await telegram_app.initialize()
    await telegram_app.start()
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

# Initialize database connection pool
async def init_db():
    global db_pool
    DATABASE_URL = os.getenv("DATABASE_URL")
    logger.info(f"DATABASE_URL: {DATABASE_URL}")
    if not DATABASE_URL:
        logger.error("DATABASE_URL environment variable is not set")
        raise ValueError("DATABASE_URL environment variable is not set")
    
    try:
        db_pool = await asyncpg.create_pool(
            DATABASE_URL,
            ssl="require",  # Enforce SSL for Supabase
            min_size=1,
            max_size=10,
        )
        logger.info("Database pool created successfully")
    except asyncpg.InvalidPasswordError:
        logger.error("Invalid database password")
        raise
    except asyncpg.ConnectionFailureError:
        logger.error("Failed to connect to database")
        raise
    except Exception as e:
        logger.error(f"Unexpected error during database initialization: {e}")
        raise

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
    await store_user(user.id, user.username)
    await update.message.reply_text("Welcome to SkyClock Bot! Use /help to see commands.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Available commands:\n/start - Start the bot\n/help - Show this message")

# FastAPI webhook endpoint
@app.post("/webhook")
async def webhook(update: Update):
    await telegram_app.process_update(update)
    return JSONResponse(content={"status": "ok"})

# Main function to set up handlers and start the bot
async def main():
    # Add command handlers
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("help", help_command))

if __name__ == "__main__":
    import uvicorn
    # Run main to set up handlers
    import asyncio
    asyncio.run(main())
    # Start FastAPI server
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))