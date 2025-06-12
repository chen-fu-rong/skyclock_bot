import os
import logging
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

# ===== CONFIG =====
BOT_TOKEN = os.getenv("BOT_TOKEN") or "YOUR_BOT_TOKEN"  # Replace or use env var
ADMIN_ID = 123456789  # Replace with your Telegram user ID

# ===== Logging =====
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# ===== Chat ID Storage =====
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

# ===== Bot Handlers =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_chat_ids.add(chat_id)
    save_chat_ids(user_chat_ids)

    user = update.effective_user
    name = user.full_name or user.username or "User"

    await update.message.reply_text(f"Hi {name}! You're now subscribed for updates.")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return

    if not context.args:
        await update.message.reply_text("Usage:\n/broadcast <your message>")
        return

    message = " ".join(context.args)

    success, fail = 0, 0
    for chat_id in user_chat_ids:
        try:
            await context.bot.send_message(chat_id=chat_id, text=message)
            success += 1
        except Exception as e:
            logging.warning(f"Failed to send to {chat_id}: {e}")
            fail += 1

    await update.message.reply_text(f"✅ Sent to {success} users. ❌ Failed: {fail}")

# ===== Main =====
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("broadcast", broadcast))

    print("✅ Bot is running...")
    app.run_polling()
