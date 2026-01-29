import os
import html
import threading
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

# ================= ENV =================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
PORT = int(os.environ.get("PORT", "10000"))

# ================= FLASK APP =================
flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "Bot is running 🚀"

def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT)

# ================= KEYBOARD =================
def reset_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("♻️ Reset", callback_data="reset")]
    ])

# ================= SAFE LONG MESSAGE =================
async def send_long_message(update, text, parse_mode=None):
    MAX_LEN = 3900
    while len(text) > MAX_LEN:
        cut = text.rfind("\n", 0, MAX_LEN)
        if cut == -1:
            cut = MAX_LEN
        await update.message.reply_text(text[:cut], parse_mode=parse_mode)
        text = text[cut:].lstrip()
    await update.message.reply_text(text, parse_mode=parse_mode)

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "📋 Please upload your LIST",
        reply_markup=reset_kb()
    )

# ================= CALLBACK =================
async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "reset":
        context.user_data.clear()
        await q.message.reply_text(
            "♻️ Reset done\n📋 Please upload new LIST",
            reply_markup=reset_kb()
        )

# ================= MAIN HANDLER =================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    # STEP 1: SAVE LIST
    if "list" not in context.user_data:
        context.user_data["list"] = [
            l.strip() for l in text.splitlines() if l.strip()
        ]
        await update.message.reply_text(
            "✅ List uploaded successfully\n➡️ Now send your User ID(s)",
            reply_markup=reset_kb()
        )
        return

    # STEP 2: USER IDs
    user_ids = [i.strip() for i in text.splitlines() if i.strip()]
    saved_list = context.user_data["list"]

    results = []
    found_map = {}

    for idx, line in enumerate(saved_list, start=1):
        parts = line.split(maxsplit=1)
        list_id = parts[0]
        if list_id in user_ids:
            status = "VALID" if len(parts) == 1 else "INVALID"
            found_map[list_id] = (idx, status)

    # FULL LIST VIEW
    full_view = []
    for idx, line in enumerate(saved_list, start=1):
        safe = html.escape(line)
        list_id = line.split(maxsplit=1)[0]
        if list_id in found_map:
            full_view.append(f"{idx}. 👉 <b>{safe}</b>")
        else:
            full_view.append(f"{idx}. {safe}")

    await send_long_message(update, "\n".join(full_view), parse_mode="HTML")

    # RESULT
    for uid in user_ids:
        if uid in found_map:
            idx, status = found_map[uid]
            emoji = "✅" if status == "VALID" else "❌"
            results.append(f"👉 {idx}. {uid} {emoji} {status}")
        else:
            results.append(f"❌ {uid} NOT FOUND")

    await update.message.reply_text(
        "\n".join(results),
        reply_markup=reset_kb()
    )

# ================= MAIN =================
if __name__ == "__main__":
    # 🔥 Flask thread (Render ke liye)
    threading.Thread(target=run_flask, daemon=True).start()

    # 🤖 Telegram Bot
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callbacks))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🚀 Bot running on Render with Flask + Polling")
    app.run_polling()
