import os
import asyncio
from main import pool, check_scheduled_events
from telegram.ext import Application

async def main():
    app = Application.builder().token(os.getenv("BOT_TOKEN")).build()
    await app.initialize()
    await check_scheduled_events(app)

if __name__ == "__main__":
    asyncio.run(main())