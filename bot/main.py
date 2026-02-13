"""
BuildGo Telegram Bot - Main Entry Point

Handles user registration and authentication for Telegram Mini App.

Two flows:
1. Buyer: Collect name and phone, register in backend, show Mini App
2. Seller: Verify seller status, show Mini App with seller mode
"""

import logging
import aiohttp
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    KeyboardButton,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)

from config import BOT_TOKEN, MINI_APP_URL, TELEGRAM_AUTH_ENDPOINT, CHECK_SELLER_ENDPOINT

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Conversation states
SELECTING_ROLE, ASKING_FIRST_NAME, ASKING_LAST_NAME, ASKING_PHONE = range(4)

# Shared aiohttp timeout (10 seconds)
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=15)


# ============================================
# HELPERS
# ============================================

async def api_post(url: str, payload: dict) -> tuple[int, dict]:
    """Async POST to backend API. Returns (status_code, json_body)."""
    async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
        async with session.post(url, json=payload) as resp:
            body = await resp.json()
            return resp.status, body


async def api_get(url: str, params: dict) -> tuple[int, dict]:
    """Async GET to backend API. Returns (status_code, json_body)."""
    async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
        async with session.get(url, params=params) as resp:
            body = await resp.json()
            return resp.status, body


# ============================================
# HANDLERS
# ============================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    /start command - Show role selection buttons.
    """
    # Clear any leftover data from previous conversations
    context.user_data.clear()

    keyboard = [
        [
            InlineKeyboardButton("🧱 Xaridor", callback_data="buyer"),
            InlineKeyboardButton("🏪 Sotuvchi", callback_data="seller"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Assalomu alaykum! Rolni tanlang:",
        reply_markup=reply_markup,
    )

    return SELECTING_ROLE


async def role_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle role selection (buyer or seller).
    """
    query = update.callback_query
    await query.answer()

    role = query.data
    context.user_data["role"] = role

    if role == "buyer":
        # Start buyer registration flow
        await query.edit_message_text("Ismingizni kiriting:")
        return ASKING_FIRST_NAME

    elif role == "seller":
        # Check if user is a seller
        telegram_id = update.effective_user.id

        try:
            status_code, data = await api_get(
                CHECK_SELLER_ENDPOINT,
                params={"telegram_id": telegram_id},
            )

            if data.get("is_seller"):
                # User is a seller, show Mini App button
                await query.edit_message_text(
                    "✅ Xush kelibsiz!\n"
                    "Dashboard'ni ochish uchun pastdagi tugmani bosing."
                )

                # Send Mini App button
                keyboard = [
                    [
                        InlineKeyboardButton(
                            "📊 Dashboard",
                            web_app={"url": f"{MINI_APP_URL}?mode=seller"},
                        )
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="Dashboard:",
                    reply_markup=reply_markup,
                )
            else:
                # Not a seller
                await query.edit_message_text(
                    "❌ Siz sotuvchi sifatida ro'yxatdan o'tmagansiz.\n"
                    "Administrator bilan bog'laning."
                )

        except aiohttp.ClientError as e:
            logger.exception("Network error checking seller status for telegram_id=%s", telegram_id)
            await query.edit_message_text(
                "❌ Server bilan bog'lanishda xatolik. Iltimos qaytadan urinib ko'ring."
            )
        except Exception as e:
            logger.exception("Unexpected error checking seller status for telegram_id=%s", telegram_id)
            await query.edit_message_text(
                "❌ Xatolik yuz berdi. Iltimos qaytadan urinib ko'ring."
            )

        return ConversationHandler.END


async def receive_first_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Receive first name from buyer.
    """
    context.user_data["first_name"] = update.message.text.strip()
    await update.message.reply_text("Familiyangizni kiriting:")
    return ASKING_LAST_NAME


async def receive_last_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Receive last name from buyer.
    """
    context.user_data["last_name"] = update.message.text.strip()

    # Request phone number using Telegram contact button
    keyboard = [
        [KeyboardButton("📱 Telefon raqamni yuborish", request_contact=True)]
    ]
    reply_markup = ReplyKeyboardMarkup(
        keyboard, one_time_keyboard=True, resize_keyboard=True
    )

    await update.message.reply_text(
        "Telefon raqamingizni yuboring:",
        reply_markup=reply_markup,
    )
    return ASKING_PHONE


async def receive_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Receive phone number (CONTACT only) and register user in backend.
    """
    # Get phone from contact
    phone = update.message.contact.phone_number

    # Prepare data for backend
    telegram_id = update.effective_user.id
    first_name = context.user_data.get("first_name", "")
    last_name = context.user_data.get("last_name", "")

    payload = {
        "telegram_id": telegram_id,
        "first_name": first_name,
        "last_name": last_name,
        "phone": phone,
    }

    logger.info(
        "Registering user: telegram_id=%s, name=%s %s, phone=%s",
        telegram_id, first_name, last_name, phone,
    )

    try:
        # Send to backend (async, non-blocking)
        status_code, body = await api_post(TELEGRAM_AUTH_ENDPOINT, payload)

        if status_code in (200, 201):
            # Success - remove custom keyboard
            await update.message.reply_text(
                "✅ Ma'lumotlaringiz saqlandi.\n"
                "Buyurtma berish uchun ilovani oching 👇",
                reply_markup=ReplyKeyboardRemove(),
            )

            # Send Mini App button
            keyboard = [
                [
                    InlineKeyboardButton(
                        "🏪 Ilovani ochish",
                        web_app={"url": f"{MINI_APP_URL}?mode=buyer"},
                    )
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Ilova:",
                reply_markup=reply_markup,
            )
        else:
            logger.error(
                "Backend returned %s for telegram_id=%s: %s",
                status_code, telegram_id, body,
            )
            await update.message.reply_text(
                "❌ Ro'yxatdan o'tishda xatolik yuz berdi. "
                "Iltimos qaytadan urinib ko'ring.",
                reply_markup=ReplyKeyboardRemove(),
            )

    except aiohttp.ClientError as e:
        logger.exception("Network error registering user telegram_id=%s", telegram_id)
        await update.message.reply_text(
            "❌ Server bilan bog'lanishda xatolik. "
            "Iltimos qaytadan urinib ko'ring.",
            reply_markup=ReplyKeyboardRemove(),
        )
    except Exception as e:
        logger.exception("Unexpected error registering user telegram_id=%s", telegram_id)
        await update.message.reply_text(
            "❌ Xatolik yuz berdi. Iltimos qaytadan urinib ko'ring.",
            reply_markup=ReplyKeyboardRemove(),
        )

    # Clear user data
    context.user_data.clear()

    return ConversationHandler.END


async def phone_text_rejected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    User sent text instead of a contact in the phone step.
    Show error and stay in ASKING_PHONE state.
    """
    await update.message.reply_text(
        "❌ Iltimos, telefon raqamingizni pastdagi tugma orqali yuboring.\n"
        "Matn sifatida yubormang."
    )
    return ASKING_PHONE


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Cancel conversation.
    """
    await update.message.reply_text(
        "Bekor qilindi. /start buyrug'ini bosing.",
        reply_markup=ReplyKeyboardRemove(),
    )
    context.user_data.clear()
    return ConversationHandler.END


# ============================================
# MAIN
# ============================================

def main():
    """
    Start the bot.
    """
    if not BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not found in environment variables!")
        return

    if not MINI_APP_URL:
        logger.error("MINI_APP_URL not found in environment variables!")
        return

    # Create application
    application = Application.builder().token(BOT_TOKEN).build()

    # Conversation handler for registration flow
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECTING_ROLE: [
                CallbackQueryHandler(role_selected),
            ],
            ASKING_FIRST_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_first_name),
            ],
            ASKING_LAST_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_last_name),
            ],
            ASKING_PHONE: [
                # CONTACT only — accept shared contact
                MessageHandler(filters.CONTACT, receive_phone),
                # If user sends text instead of contact, reject it
                MessageHandler(filters.TEXT & ~filters.COMMAND, phone_text_rejected),
            ],
        },
        fallbacks=[
            CommandHandler("start", start),
            CommandHandler("cancel", cancel),
        ],
    )

    application.add_handler(conv_handler)

    # Start the bot
    logger.info("Bot started...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
