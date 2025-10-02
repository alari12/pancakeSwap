# bot.py
import os
import logging
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    CallbackQueryHandler,
)
from dotenv import load_dotenv

# Load local .env when running locally
load_dotenv()

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment variables
TOKEN = os.environ.get("TELEGRAM_TOKEN")
HELP_LINK = os.environ.get("HELP_LINK", "https://alari12.github.io/MindCarePLC/")
TRIGGERS = os.environ.get("TRIGGERS", "wallet,usdt,crypto,sol,help,swap,staking,transfer")
TRIGGER_WORDS = [t.strip().lower() for t in TRIGGERS.split(",") if t.strip()]

if not TOKEN:
    logger.error("Missing TELEGRAM_TOKEN env var. Exiting.")
    raise SystemExit("TELEGRAM_TOKEN is required")

# Conversation states
LANGUAGE, ISSUE, ASK_ADDRESS = range(3)

def issues_keyboard():
    keyboard = [
        [InlineKeyboardButton("Swapping", callback_data="swapping"),
         InlineKeyboardButton("Staking", callback_data="staking")],
        [InlineKeyboardButton("Site malfunction", callback_data="site"),
         InlineKeyboardButton("Other", callback_data="other")],
    ]
    return InlineKeyboardMarkup(keyboard)

# /start - user visible welcome message (private chat)
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome! This support assistant can help with common crypto issues.\n\n"
        "Type /help for the main resource link, or type anything to begin."
    )

# /help - direct help link
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Here is a trusted resource:\n{HELP_LINK}\n\n"
        "If you want personalized troubleshooting, I can check public wallet data (you must paste your public address)."
    )

# Entry when starting a support DM conversation
async def support_start_dm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    await update.message.reply_text(
        f"Hello {user.first_name or ''}! 👋\n"
        "Do you speak English? Reply 'yes' or tell me your preferred language."
    )
    return LANGUAGE

# User replied about language
async def language_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip().lower()
    if text in ("yes", "y", "en", "english"):
        await update.message.reply_text("Great — we'll continue in English. What problem are you experiencing?")
    else:
        await update.message.reply_text(
            f"Okay — you said '{text}'. I will attempt to provide replies in that language (translations may be imperfect).\n"
            "What problem are you experiencing?"
        )
    await update.message.reply_text("Choose an issue:", reply_markup=issues_keyboard())
    return ISSUE

# Issue chosen by callback or message
async def issue_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    data = None
    if update.callback_query:
        data = update.callback_query.data
        await update.callback_query.answer()
    else:
        data = (update.message.text or "").strip().lower()

    context.user_data["issue"] = data
    if data in ("swapping", "staking"):
        await update.message.reply_text(
            "If you'd like me to check public on-chain info, please paste your PUBLIC wallet address now.\n\n"
            "⚠️ DO NOT share private keys or seed phrases. Only paste a public address (starts with 0x)."
        )
        return ASK_ADDRESS
    else:
        # Site or other: provide generic troubleshooting + help link
        await update.message.reply_text(
            f"Thanks — noted the issue: {data}.\n\n"
            "- Try clearing cache and refreshing the page\n"
            "- Ensure you selected the correct network\n"
            "- Try a different wallet or browser\n\n"
            f"Detailed resource: {HELP_LINK}\n\n"
            "If you'd like me to check a public wallet address, you can paste it here."
        )
        return ConversationHandler.END

# Handle user-provided public address
async def address_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    # basic validation
    if not (text.startswith("0x") and len(text) >= 40):
        await update.message.reply_text("That doesn't look like a valid public address. Please paste your wallet address (starts with 0x).")
        return ASK_ADDRESS

    address = text
    # Public BscScan link
    bscscan_url = f"https://bscscan.com/address/{address}"
    await update.message.reply_text(
        "Thanks. I can only check public data. Open the link below to view transactions and balance:\n\n"
        f"{bscscan_url}\n\n"
        "This page shows public on-chain information only (balances, tx history)."
    )

    issue = context.user_data.get("issue", "issue")
    if issue == "swapping":
        advice = (
            "- Check that you have enough BNB for gas on BSC.\n"
            "- Verify token allowance and slippage settings for the swap.\n"
            "- Try a different DEX/router or increase slippage if needed.\n"
        )
    elif issue == "staking":
        advice = (
            "- Check the staking contract address and token approval status.\n"
            "- Verify contract state (locked/unlocked) and staking rules.\n"
        )
    else:
        advice = "- Follow steps in the resource for troubleshooting.\n"

    await update.message.reply_text(
        f"Suggested next steps:\n{advice}\nFull resource: {HELP_LINK}\n\n"
        "I will NOT ask for private keys or seed phrases. If you'd like additional help, describe the exact error or behavior."
    )

    return ConversationHandler.END

# Cancel
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Support session closed. Type /help to view the resource link again.")
    return ConversationHandler.END

# Monitor group messages for triggers and DM the user (private)
async def handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # only process text messages
    if update.message is None or update.message.text is None:
        return

    # ignore bot messages
    if update.message.from_user and update.message.from_user.is_bot:
        return

    text = update.message.text.lower()
    for w in TRIGGER_WORDS:
        if w in text:
            user = update.message.from_user
            user_id = user.id
            # compose a gentle DM that starts the safe support flow
            try:
                dm = (
                    f"Hello {user.first_name or ''}, 👋\n\n"
                    "I can help troubleshoot crypto issues safely. "
                    "Reply here to continue. (I only use public on-chain data.)"
                )
                await context.bot.send_message(chat_id=user_id, text=dm)
                # Optionally — start the conversation handler: we cannot directly trigger ConversationHandler entry here,
                # but sending this DM will let the user reply and start the flow (we can also instruct them to type anything).
            except Exception as e:
                logger.info("Could not DM user %s: %s", user_id, e)
            break

def build_conv_handler():
    conv = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND, support_start_dm)],
        states={
            LANGUAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, language_received)],
            ISSUE: [
                CallbackQueryHandler(issue_selected),
                MessageHandler(filters.TEXT & ~filters.COMMAND, issue_selected),
            ],
            ASK_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, address_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )
    return conv

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # expose help link in bot data for handlers
    app.bot_data["HELP_LINK"] = HELP_LINK

    # Basic commands
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))

    # Conversation handler for support flow (private chat)
    app.add_handler(build_conv_handler())

    # Group listener for triggers (will DM user)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_group_message))

    logger.info("Bot starting…")
    app.run_polling()

if __name__ == "__main__":
    main()
