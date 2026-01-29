import os, threading
from flask import Flask
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    CallbackQueryHandler, MessageHandler,
    ContextTypes, filters
)

# ===== IMPORT ORIGINAL BOT =====
import bot_core  # tumhara original script

# ================= ENV =================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
PORT = int(os.environ.get("PORT", "10000"))

# ================= ORIGINAL HANDLERS =================
orig_start = bot_core.start
orig_buttons = bot_core.buttons
orig_text = bot_core.handle_text
orig_file = bot_core.handle_file

# ================= START =================
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    return await orig_start(update, ctx)

# ================= BUTTONS =================
async def buttons(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    return await orig_buttons(update, ctx)

# ================= TEXT =================
async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    return await orig_text(update, ctx)

# ================= FILE =================
async def handle_file(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    return await orig_file(update, ctx)

# ================= FLASK =================
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
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))

    print("🚀 Bot running (No Admin, Public Access)")
    app.run_polling()
