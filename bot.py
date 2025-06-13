import os
import logging
import asyncpg
import asyncio
from urllib.parse import urlparse
from fastapi import FastAPI, Request
from contextlib import asynccontextmanager
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from fastapi.responses import JSONResponse

# Set up logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI()

# Global variables
db_pool = None
telegram_app = None

# Lifespan handler for startup and shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    global db_pool, telegram_app
    # Startup: Initialize Telegram bot and start database connection in background
    telegram_app = (
        Application.builder()
        .token(os.getenv("TELEGRAM_BOT_TOKEN"))
        .build()
    )
    await telegram_app.initialize()
    await telegram_app.start()
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("help", help_command))
    logger.info("Telegram bot initialized")

    # Start database initialization in background
    asyncio.create_task(init_db_background())

    yield

    # Shutdown
    if db_pool:
        await db_pool.close()
        logger.info("Database pool closed")
    if telegram_app:
        await telegram_app.stop()
        await telegram_app.shutdown()
        logger.info("Telegram bot stopped")

app.router.lifespan_context = lifespan

# Initialize database connection pool in the background
async def init_db_background():
    global db_pool
    DATABASE_URL = os.getenv("DATABASE_URL")
    logger.info(f"DATABASE_URL: {DATABASE_URL}")
    if not DATABASE_URL:
        logger.error("DATABASE_URL environment variable is not set")
        return
    
    retries = 5
    for attempt in range(retries):
        try:
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
                command_timeout=120,  # Increased timeout for queries
                server_settings={'connect_timeout': '120'}  # Increased connect timeout
            )
            logger.info("Database pool created successfully")
            return
        except asyncpg.exceptions.ConnectionFailureError as e:
            logger.error(f"Attempt {attempt + 1} - Connection failure: {e}")
        except asyncio.TimeoutError as e:
            logger.error(f"Attempt {attempt + 1} - Connection timed out: {e}")
        except Exception as e:
            logger.error(f"Attempt {attempt + 1} - Unexpected error: {e}")
        
        if attempt < retries - 1:
            await asyncio.sleep(10)  # Wait 10 seconds before retrying
        else:
            logger.error("Failed to initialize database after multiple attempts")

# Example database query (modify as needed)
async def store_user(user_id: int, username: str):
    if not db_pool:
        logger.error("Database pool not initialized")
        return
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
        json_data = await request.json()
        update = Update.de_json(json_data, telegram_app.bot)
        if update:
            await telegram_app.process_update(update)
        return JSONResponse(content={"status": "ok"})
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return JSONResponse(content={"status": "error"}, status_code=500)

# Health check endpoint for Render
@app.get("/health")
async def health():
    return {"status": "ok", "database_connected": bool(db_pool)}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 10000))
    logger.info(f"Binding to port: {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)