import os
import logging
import asyncio
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN") or "YOUR_BOT_TOKEN"
WEBHOOK_PATH = "/webhook"
PORT = int(os.getenv("PORT", "10000"))

app = FastAPI()

application = ApplicationBuilder().token(BOT_TOKEN).build()

# Chat ID storage helpers omitted for brevity...

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Hello {update.effective_user.first_name}, welcome!")

application.add_handler(CommandHandler("start", start))

# Background task to process updates in the queue
async def process_updates():
    while True:
        update = await application.update_queue.get()
        try:
            await application.process_update(update)
        except Exception as e:
            logging.error(f"Error while processing update: {e}")

@app.on_event("startup")
async def startup_event():
    # Start the background update processor task
    asyncio.create_task(process_updates())

@app.post(WEBHOOK_PATH)
async def webhook(request: Request):
    data = await request.json()
    logging.info(f"Received update: {data}")
    update = Update.de_json(data, application.bot)
    # Put the update in the application queue for processing by background task
    await application.update_queue.put(update)
    return {"ok": True}

@app.get("/")
async def root():
    return {"message": "Bot is running"}

if __name__ == "__main__":
    import uvicorn
    # Setup webhook on startup (optional)
    async def main():
        webhook_url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}{WEBHOOK_PATH}"
        await application.bot.set_webhook(webhook_url)
        config = uvicorn.Config(app, host="0.0.0.0", port=PORT, log_level="info")
        server = uvicorn.Server(config)
        await server.serve()

    asyncio.run(main())
