import os
import logging
import asyncio
import httpx
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

# -------------------------------
# 🌐 Language Configuration
# -------------------------------
user_languages = {}

translations = {
    "menu": {
        "en": ["Wax", "Quests", "Shops and Spirits", "Reset", "Concert and Shows", "Fifth Anniversary Events", "Shards", "Setting"],
        "my": ["ဖျော့", "မေးခွန်းများ", "ဆိုင်နှင့်ဝိညာဉ်", "အမိန့်ပြန်လုပ်မည်", "ဖျော်ဖြေရေးများ", "ငါ့ငါးနှစ်မြောက်နေ့လှုပ်ရှားမှုများ", "ချပ်ကိန်းများ", "ဆက်တင်"],
        "zh": ["蜡", "任务", "商店与灵魂", "重置", "音乐会与表演", "五周年活动", "碎片", "设置"],
    },
    "language_btn": {
        "en": "Language", "my": "ဘာသာစကား", "zh": "语言"
    },
    "select_lang": {
        "en": "Select a language:", "my": "ဘာသာစကားရွေးပါ:", "zh": "请选择语言："
    },
    "language_updated": {
        "en": "✅ Language updated!",
        "my": "✅ ဘာသာစကားအားပြောင်းပြီးပါပြီ။",
        "zh": "✅ 语言已更新！"
    },
    "setting_title": {
        "en": "⚙️ Setting:",
        "my": "⚙️ ဆက်တင်:",
        "zh": "⚙️ 设置："
    },
    "welcome": {
        "en": "Welcome! 🌟",
        "my": "ကြိုဆိုပါတယ်! 🌟",
        "zh": "欢迎！🌟"
    }
}

# -------------------------------
# 🔗 Fetch shard data
# -------------------------------
async def fetch_shard_data():
    url = "https://raw.githubusercontent.com/PlutoyDev/sky-shards/main/data/shards/en.json"
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()

# -------------------------------
# 🔘 Start Command
# -------------------------------
async def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    user_languages.setdefault(user_id, "en")
    lang = user_languages[user_id]

    buttons = [
        [InlineKeyboardButton(text=label, callback_data=f"menu_{i}")]
        for i, label in enumerate(translations["menu"][lang])
    ]
    menu_markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text(translations["welcome"][lang], reply_markup=menu_markup)

# -------------------------------
# 🔁 Button Callback Handler
# -------------------------------
async def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    lang = user_languages.get(user_id, "en")

    if query.data.startswith("menu_"):
        index = int(query.data.split("_")[1])
        label = translations["menu"][lang][index]

        if label == translations["menu"][lang][-1]:  # "Setting"
            lang_btn = translations["language_btn"][lang]
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton(lang_btn, callback_data="setting_language")]
            ])
            await query.edit_message_text(translations["setting_title"][lang], reply_markup=markup)

        elif label == translations["menu"][lang][6]:  # "Shards"
            try:
                shards = await fetch_shard_data()
                lines = []
                for shard in shards:
                    name = shard.get("name", "Unknown")
                    location = shard.get("location", "Unknown")
                    time = shard.get("time", "Unknown")
                    shard_type = shard.get("type", "Unknown")
                    lines.append(f"🔹 {name}\n📍 {location}\n🕒 {time}\n✨ {shard_type}")
                message = "\n\n".join(lines)
                await query.edit_message_text(message[:4096])
            except Exception as e:
                await query.edit_message_text(f"Failed to load shard data.\n{e}")
        else:
            await query.edit_message_text(f"You selected: {label}")

    elif query.data == "setting_language":
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("English", callback_data="set_lang_en")],
            [InlineKeyboardButton("Burmese", callback_data="set_lang_my")],
            [InlineKeyboardButton("Chinese", callback_data="set_lang_zh")],
        ])
        await query.edit_message_text(translations["select_lang"][lang], reply_markup=markup)

    elif query.data.startswith("set_lang_"):
        selected_lang = query.data.split("_")[-1]
        user_languages[user_id] = selected_lang
        lang = selected_lang
        await query.edit_message_text(translations["language_updated"][lang])

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
