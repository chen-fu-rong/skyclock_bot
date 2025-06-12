import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from fastapi import FastAPI, Request
import uvicorn
import asyncio

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN") or "YOUR_BOT_TOKEN"
ADMIN_ID = int(os.getenv("ADMIN_ID") or "123456789")
WEBHOOK_PATH = "/webhook"
PORT = int(os.getenv("PORT", "10000"))

app = FastAPI()

telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()

chat_ids_file = "chat_ids.txt"

def load_chat_ids():
    try:
        with open(chat_ids_file, "r") as f:
            return set(int(line.strip()) for line in f if line.strip().isdigit())
    except FileNotFoundError:
        return set()

def save_chat_ids(chat_ids):
    with open(chat_ids_file, "w") as f:
        for cid in chat_ids:
            f.write(f"{cid}\n")

user_chat_ids = load_chat_ids()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_chat_ids.add(chat_id)
    save_chat_ids(user_chat_ids)
    name = update.effective_user.full_name or update.effective_user.username or "there"
    await update.message.reply_text(f"Hi {name}! You're now subscribed for updates.")
    logging.info(f"User {chat_id} started the bot.")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Unauthorized.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /broadcast <message>")
        return

    message = " ".join(context.args)
    success, fail = 0, 0

    for cid in user_chat_ids.copy():
        try:
            await context.bot.send_message(chat_id=cid, text=message)
            success += 1
        except Exception as e:
            logging.warning(f"Failed to send message to {cid}: {e}")
            fail += 1

    await update.message.reply_text(f"✅ Sent to {success} users, ❌ Failed: {fail}")

telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CommandHandler("broadcast", broadcast))

@app.on_event("startup")
async def startup_event():
    # Start background task to process the telegram update queue
    asyncio.create_task(telegram_app.start())
    asyncio.create_task(telegram_app.updater.start_polling())  # Optional: for polling fallback

@app.on_event("shutdown")
async def shutdown_event():
    await telegram_app.stop()

@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    data = await request.json()
    logging.info(f"Received update: {data}")
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.update_queue.put(update)
    return {"ok": True}

@app.get("/")
async def root():
    return {"message": "SkyClock Bot is running!"}

if __name__ == "__main__":
    import sys
    import uvicorn

    webhook_url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}{WEBHOOK_PATH}"
    logging.info(f"Setting webhook: {webhook_url}")

    async def main():
        await telegram_app.bot.set_webhook(webhook_url)
        config = uvicorn.Config(app, host="0.0.0.0", port=PORT, log_level="info")
        server = uvicorn.Server(config)
        await server.serve()

    asyncio.run(main())
