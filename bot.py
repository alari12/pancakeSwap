import os
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    CallbackQueryHandler,
    filters,
)
from googletrans import Translator

# --- CONFIG ---
TOKEN = os.getenv("BOT_TOKEN")  # set BOT_TOKEN in Railway or replace with your token
TRIGGER_WORDS = ["wallet", "crypto", "usdt", "sol", "btc", "trx", "money", "withdraw"]

translator = Translator()

# --- START COMMAND ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Hello! I’m here to help. Just type your issue.")

# --- MESSAGE HANDLER ---
async def detect_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user_text = update.message.text.lower()
    user_lang = translator.detect(user_text).lang  # detect language

    # Check trigger words
    if any(word in user_text for word in TRIGGER_WORDS):
        # Auto translated response
        reply_en = (
            "I noticed you mentioned something about your wallet or crypto. "
            "Here’s a useful link that might help you: https://help.okx.com\n\n"
            "If you still need support, you can choose below 👇"
        )
        reply_translated = translator.translate(reply_en, dest=user_lang).text

        keyboard = [
            [InlineKeyboardButton("💬 Talk to Support", callback_data="manual_support")]
        ]
        await update.message.reply_text(
            reply_translated,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

# --- CALLBACK HANDLER ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "manual_support":
        await query.message.reply_text("✅ A support agent will join this chat shortly...")

# --- MAIN ---
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, detect_trigger))
    app.add_handler(CallbackQueryHandler(button_handler))

    app.run_polling()

if __name__ == "__main__":
    main()

