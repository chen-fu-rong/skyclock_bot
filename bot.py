import os
import logging
import json
import asyncio
from fastapi import FastAPI, Request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    CallbackContext,
)

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN") or "YOUR_BOT_TOKEN"
WEBHOOK_PATH = "/webhook"
PORT = int(os.getenv("PORT", "10000"))

app = FastAPI()
application = ApplicationBuilder().token(BOT_TOKEN).build()

# Load shard data from minified.json
with open("minified.json", "r", encoding="utf-8") as f:
    shard_data = json.load(f)

# -------------------------------
# 🔘 Start Command
# -------------------------------
async def start(update: Update, context: CallbackContext):
    buttons = [
        [InlineKeyboardButton(text="Wax", callback_data="menu_0")],
        [InlineKeyboardButton(text="Quests", callback_data="menu_1")],
        [InlineKeyboardButton(text="Shops and Spirits", callback_data="menu_2")],
        [InlineKeyboardButton(text="Reset", callback_data="menu_3")],
        [InlineKeyboardButton(text="Concert and Shows", callback_data="menu_4")],
        [InlineKeyboardButton(text="Fifth Anniversary Events", callback_data="menu_5")],
        [InlineKeyboardButton(text="Shards", callback_data="menu_6")],
    ]
    menu_markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text("Welcome! 🌟", reply_markup=menu_markup)

# -------------------------------
# 🔁 Button Callback Handler
# -------------------------------
async def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("menu_"):
        index = int(query.data.split("_")[1])
        labels = ["Wax", "Quests", "Shops and Spirits", "Reset", "Concert and Shows", "Fifth Anniversary Events", "Shards"]
        label = labels[index]

        if label == "Shards":
            shard_messages = []
            for shard_id, shard in shard_data.get("shards", {}).items():
                msg = f"🧩 Shard ID: {shard_id}\nName: {shard.get('name', 'Unknown')}\nLocation: {shard.get('location', 'Unknown')}"
                shard_messages.append(msg)
            result = "\n\n".join(shard_messages) if shard_messages else "No shard data found."
            await query.edit_message_text(result)
        else:
            await query.edit_message_text(f"You selected: {label}")

# -------------------------------
# 🧩 Register Handlers
# -------------------------------
application.add_handler(CommandHandler("start", start))
application.add_handler(CallbackQueryHandler(button_handler))

# -------------------------------
# 🔄 Background Update Loop
# -------------------------------
async def process_updates():
    while True:
        update = await application.update_queue.get()
        try:
            await application.process_update(update)
        except Exception as e:
            logging.error(f"Error while processing update: {e}")

# -------------------------------
# 🚀 FastAPI Startup / Shutdown
# -------------------------------
@app.on_event("startup")
async def startup_event():
    await application.initialize()
    await application.start()
    asyncio.create_task(process_updates())

    webhook_url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}{WEBHOOK_PATH}"
    await application.bot.set_webhook(webhook_url)
    logging.info(f"Webhook set to {webhook_url}")

@app.on_event("shutdown")
async def shutdown_event():
    await application.stop()
    await application.shutdown()

# -------------------------------
# 📬 Webhook Endpoint
# -------------------------------
@app.post(WEBHOOK_PATH)
async def webhook(request: Request):
    data = await request.json()
    logging.info(f"Received update: {data}")
    update = Update.de_json(data, application.bot)
    await application.update_queue.put(update)
    return {"ok": True}

@app.get("/")
async def root():
    return {"message": "Bot is running"}

# -------------------------------
# 🔊 Local Dev Run
# -------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
