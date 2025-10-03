# bot.py
import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from deep_translator import GoogleTranslator
from dotenv import load_dotenv

# load .env
load_dotenv()

# --- CONFIG (from env) ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))  # set your numeric Telegram id
TRIGGERS = os.environ.get("TRIGGERS", "wallet,usdt,crypto,swap,stake,staking,help").split(",")
TRIGGER_WORDS = [w.strip().lower() for w in TRIGGERS if w.strip()]
HELP_LINK = os.environ.get("HELP_LINK", "https://alari12.github.io/MindCarePLC/")

if not TOKEN or OWNER_ID == 0:
    raise SystemExit("Please set TELEGRAM_TOKEN and OWNER_ID in .env")

# logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# runtime state
user_lang = {}      # user_id -> language code (e.g., 'es', 'fr', 'en')
active_manual = {}  # user_id -> True when user requested manual support

# translation helpers
def detect_lang(text: str) -> str:
    try:
        return GoogleTranslator(source="auto").detect(text)
    except Exception as e:
        logger.warning("Language detect failed: %s", e)
        return "en"

def translate_text(text: str, target: str) -> str:
    if not text:
        return text
    try:
        return GoogleTranslator(source="auto", target=target).translate(text)
    except Exception as e:
        logger.warning("Translate failed: %s", e)
        return text if target == "en" else text  # fallback

# --- Replies / UI ---
def make_issue_keyboard(target_lang: str):
    # Buttons text in English will be translated before sending
    buttons = [
        [InlineKeyboardButton(GoogleTranslator(source="en", target=target_lang).translate("Swapping Issues"),
                              callback_data="swap"),
         InlineKeyboardButton(GoogleTranslator(source="en", target=target_lang).translate("Staking Problems"),
                              callback_data="stake")],
        [InlineKeyboardButton(GoogleTranslator(source="en", target=target_lang).translate("Site Malfunction"),
                              callback_data="site")],
        [InlineKeyboardButton(GoogleTranslator(source="en", target=target_lang).translate("Manual Support"),
                              callback_data="manual_support")],
    ]
    return InlineKeyboardMarkup(buttons)

# --- Commands & Handlers ---
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Hello — type your problem (any language) or say hi to begin.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None or update.message.text is None:
        return

    uid = update.message.from_user.id
    text = update.message.text.strip()
    if not text:
        return

    # If user is already in manual mode, forward translated message to owner
    if active_manual.get(uid):
        # translate user message into English for the owner
        try:
            lang = user_lang.get(uid) or detect_lang(text)
            transl = GoogleTranslator(source=lang, target="en").translate(text)
        except Exception:
            transl = text
        # send to owner
        await context.bot.send_message(
            chat_id=OWNER_ID,
            text=f"📩 Message from {update.message.from_user.first_name} ({uid}):\n{transl}"
        )
        return

    # detect language and store
    lang = detect_lang(text)
    user_lang[uid] = lang

    # translate user text to English to check triggers
    try:
        text_en = GoogleTranslator(source=lang, target="en").translate(text).lower()
    except Exception:
        text_en = text.lower()

    if any(w in text_en for w in TRIGGER_WORDS):
        # ask issue type, in user's language
        prompt_en = "I noticed you mentioned crypto-related issues. What problem are you experiencing?"
        prompt = translate_text(prompt_en, lang)
        kb = make_issue_keyboard(lang)
        await update.message.reply_text(prompt, reply_markup=kb)
        return

    # default reply (in user language)
    fallback_en = "I’m here to help you. If you need manual support, choose Manual Support."
    await update.message.reply_text(translate_text(fallback_en, lang))

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    lang = user_lang.get(uid, detect_lang(query.message.text or "en"))

    if query.data in ("swap", "stake", "site"):
        # Provide help link (in user's language)
        help_en = {
            "swap": f"Guides for swapping: {HELP_LINK}",
            "stake": f"Guides for staking: {HELP_LINK}",
            "site": f"Site help: {HELP_LINK}",
        }
        reply = translate_text(help_en.get(query.data, HELP_LINK), lang)
        await query.edit_message_text(reply)
        return

    if query.data == "manual_support":
        # enable manual mode and notify owner (owner receives messages translated to English)
        active_manual[uid] = True
        # notify owner with user details
        uname = query.from_user.username or query.from_user.first_name
        await context.bot.send_message(
            chat_id=OWNER_ID,
            text=(f"⚠️ Manual support requested\nUser: {uname}\nID: {uid}\n"
                  f"Use /reply {uid} <message> to respond; user replies will be forwarded to you (auto-translated).")
        )
        reply = translate_text("A live support agent will assist you shortly.", lang)
        await query.edit_message_text(reply)
        return

async def owner_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # usage: /reply <user_id> <message...>
    if update.message.from_user.id != OWNER_ID:
        await update.message.reply_text("⛔ Unauthorized.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("Usage: /reply <user_id> <message>")
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("First arg must be numeric user_id.")
        return

    owner_message = " ".join(context.args[1:]).strip()
    # find user language
    lang = user_lang.get(target_id, "en")
    # translate owner's English message into user's language
    try:
        translated = GoogleTranslator(source="en", target=lang).translate(owner_message)
    except Exception:
        translated = owner_message

    try:
        await context.bot.send_message(chat_id=target_id, text=translated)
        await update.message.reply_text(f"Sent (translated to {lang}): {translated}")
    except Exception as e:
        await update.message.reply_text(f"Failed to send: {e}")

# cleanup command to end manual mode (owner)
async def end_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != OWNER_ID:
        await update.message.reply_text("⛔ Unauthorized.")
        return
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /endmanual <user_id>")
        return
    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Provide numeric user id.")
        return
    active_manual.pop(uid, None)
    user_lang.pop(uid, None)
    await update.message.reply_text(f"Manual session ended for {uid}.")

# --- App setup ---
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("reply", owner_reply))
    app.add_handler(CommandHandler("endmanual", end_manual))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Bot starting…")
    app.run_polling()

if __name__ == "__main__":
    main()

