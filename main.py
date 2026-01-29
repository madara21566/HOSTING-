import os, threading
from flask import Flask
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# ===== IMPORT BOT CORE =====
import bot_core

# ================= ENV =================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
PORT = int(os.environ.get("PORT", "10000"))

# ================= WRAPPER HANDLERS =================
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    return await bot_core.start(update, ctx)

async def callbacks(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    return await bot_core.callbacks(update, ctx)

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    return await bot_core.handle_message(update, ctx)

# ================= FLASK (RENDER KEEP-ALIVE) =================
flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "Bot is running"

def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT)

# ================= MAIN =================
if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callbacks))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🚀 Bot running successfully")
    app.run_polling()
