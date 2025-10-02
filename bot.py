import os
import logging
import requests
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
)
from telegram.error import Forbidden, BadRequest
from dotenv import load_dotenv

# Load .env
load_dotenv()

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ====== ENV VARIABLES ======
TOKEN = os.environ.get("TELEGRAM_TOKEN")
HELP_LINK = os.environ.get("HELP_LINK", "https://alari12.github.io/MindCarePLC/")
TRIGGERS = os.environ.get("TRIGGERS", "wallet,usdt,crypto,sol,help")
BSCSCAN_API_KEY = os.environ.get("BSCSCAN_API_KEY")  # optional

TRIGGER_WORDS = [t.strip().lower() for t in TRIGGERS.split(",") if t.strip()]

OWNER_ID = int(os.environ.get("OWNER_ID", "5252571392"))  # default = you
PASSCODE = os.environ.get("PASSCODE", "2486")
AUTHORIZED_USERS = set()

if not TOKEN:
    logger.error("❌ Missing TELEGRAM_TOKEN environment variable. Exiting.")
    raise SystemExit("TELEGRAM_TOKEN is required as env var")


# /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hi! I monitor groups for crypto keywords and will DM you with help. "
        "Make sure you’ve started me in private first!"
    )


# /help command
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Here’s your help link: {HELP_LINK}\n\n"
        "Commands:\n"
        "/authorize <passcode> - unlock private access\n"
        "/balance <wallet> - check balance"
    )


# /authorize command
async def authorize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if len(context.args) == 0:
        await update.message.reply_text("❌ Please provide a passcode. Example: /authorize 2486")
        return

    code = context.args[0]
    if code == PASSCODE:
        AUTHORIZED_USERS.add(user_id)
        await update.message.reply_text("✅ Authorization successful! You can now use private commands.")
    else:
        await update.message.reply_text("❌ Wrong passcode. Access denied.")


# /balance command
async def check_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    if user_id not in AUTHORIZED_USERS:
        await update.message.reply_text("⛔ You are not authorized. Use /authorize <passcode> first.")
        return

    if len(context.args) == 0:
        await update.message.reply_text("Please provide a wallet address. Example:\n/balance 0x123abc...")
        return

    wallet = context.args[0]

    if not BSCSCAN_API_KEY:
        # Fallback dummy balance
        dummy_balance = "81.46 USDT"
        await update.message.reply_text(
            f"💰 Wallet: {wallet}\nBalance: {dummy_balance}\n\n"
            "(Dummy result — add BSCSCAN_API_KEY to get live balances)"
        )
        return

    # Real API fetch
    try:
        url = f"https://api.bscscan.com/api?module=account&action=tokenbalance&contractaddress=0x55d398326f99059fF775485246999027B3197955&address={wallet}&tag=latest&apikey={BSCSCAN_API_KEY}"
        r = requests.get(url)
        data = r.json()

        if data["status"] == "1":
            raw = int(data["result"])
            usdt_balance = raw / 1e18  # decimals
            await update.message.reply_text(
                f"💰 Wallet: {wallet}\nBalance: {usdt_balance:.2f} USDT"
            )
        else:
            await update.message.reply_text("⚠️ Error fetching balance. Please try again.")
    except Exception as e:
        logger.exception("Balance fetch error: %s", e)
        await update.message.reply_text("❌ Failed to fetch balance. Check API or wallet.")


# Group monitoring
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None or update.message.text is None:
        return

    if update.message.from_user and update.message.from_user.is_bot:
        return  # ignore bots

    text = update.message.text.lower()

    for word in TRIGGER_WORDS:
        if word in text:
            user = update.message.from_user
            user_id = user.id
            first = user.first_name or "there"
            dm_text = (
                f"Hey {first}, I noticed you mentioned '{word}'.\n\n"
                f"For help click here: {HELP_LINK}"
            )

            try:
                await context.bot.send_message(chat_id=user_id, text=dm_text)
                logger.info("✅ Sent DM to %s for trigger '%s'", user_id, word)
            except Forbidden:
                logger.warning("⚠️ Could not DM %s (privacy blocked)", user_id)
            except BadRequest as e:
                logger.exception("Bad request sending DM: %s", e)
            except Exception as e:
                logger.exception("Unexpected error: %s", e)
            break


def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("authorize", authorize))
    app.add_handler(CommandHandler("balance", check_balance))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("🚀 Bot starting…")
    app.run_polling()


if __name__ == "__main__":
    main()
