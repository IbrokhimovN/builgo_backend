"""
BuildGo Telegram Bot — Production-Hardened

Flow (UNCHANGED):
1. Get telegram_id
2. Call GET /api/check-seller/
3. If seller → open Seller Mini App
4. Else → check if returning customer → if yes, show app
5. Else → registration → POST /api/customers/ → open Customer Mini App

Hardening:
- Shared aiohttp session (no per-request session creation)
- X-Bot-Secret header on all API calls
- Returning customer detection (skip re-registration)
- /help and /orders commands
- Conversation timeout (5 minutes)
- Graceful error messages with retry hints

NO role selection. NO authentication decisions. NO sessions.
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
    ConversationHandler,
    filters,
    ContextTypes,
)

from config import (
    BOT_TOKEN,
    BOT_API_SECRET,
    MINI_APP_URL,
    CUSTOMER_ENDPOINT,
    CUSTOMER_CHECK_ENDPOINT,
    CUSTOMER_ORDERS_ENDPOINT,
    CHECK_SELLER_ENDPOINT,
)

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Conversation states
ASKING_FIRST_NAME, ASKING_LAST_NAME, ASKING_PHONE = range(3)

# Shared aiohttp timeout
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=15)

# Module-level session (initialized in post_init)
_http_session: aiohttp.ClientSession | None = None


# ============================================
# HTTP HELPERS (with shared session + auth)
# ============================================

def _get_headers() -> dict:
    """Return auth headers for bot → API calls."""
    return {"X-Bot-Secret": BOT_API_SECRET}


async def _ensure_session():
    """Get or create the shared aiohttp session."""
    global _http_session
    if _http_session is None or _http_session.closed:
        _http_session = aiohttp.ClientSession(
            timeout=REQUEST_TIMEOUT,
            headers=_get_headers(),
        )
    return _http_session


async def api_post(url: str, payload: dict) -> tuple[int, dict]:
    """Async POST to backend API. Returns (status_code, json_body)."""
    session = await _ensure_session()
    async with session.post(url, json=payload) as resp:
        body = await resp.json()
        return resp.status, body


async def api_get(url: str, params: dict) -> tuple[int, dict]:
    """Async GET to backend API. Returns (status_code, json_body)."""
    session = await _ensure_session()
    async with session.get(url, params=params) as resp:
        body = await resp.json()
        return resp.status, body


# ============================================
# LIFECYCLE
# ============================================

async def post_init(application: Application) -> None:
    """Initialize shared HTTP session after application starts."""
    global _http_session
    _http_session = aiohttp.ClientSession(
        timeout=REQUEST_TIMEOUT,
        headers=_get_headers(),
    )
    logger.info("HTTP session initialized")


async def post_shutdown(application: Application) -> None:
    """Close shared HTTP session on shutdown."""
    global _http_session
    if _http_session and not _http_session.closed:
        await _http_session.close()
        logger.info("HTTP session closed")


# ============================================
# HANDLERS
# ============================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    /start command — deterministic flow:
    1. Check if seller by telegram_id
    2. If seller → show Seller Mini App
    3. Else → check if returning customer
    4. If returning customer → show app (skip registration)
    5. Else → start customer registration (ask name)
    """
    context.user_data.clear()
    telegram_id = update.effective_user.id

    try:
        # Step 1: Check if seller
        status_code, data = await api_get(
            CHECK_SELLER_ENDPOINT,
            params={"telegram_id": telegram_id},
        )
        logger.info(
            "check-seller: telegram_id=%s status=%s body=%s",
            telegram_id, status_code, data,
        )

        if status_code != 200:
            # API error — don't silently fall through to registration
            logger.error(
                "check-seller returned %s for telegram_id=%s: %s",
                status_code, telegram_id, data,
            )
            await update.message.reply_text(
                "❌ Server bilan bog'lanishda xatolik.\n"
                "Iltimos /start buyrug'ini qaytadan bosing."
            )
            return ConversationHandler.END

        if data.get("is_seller"):
            # Seller → show dashboard
            keyboard = [
                [
                    InlineKeyboardButton(
                        "📊 Dashboard",
                        web_app={"url": f"{MINI_APP_URL}?mode=seller"},
                    )
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                "✅ Xush kelibsiz!\n"
                "Dashboard'ni ochish uchun pastdagi tugmani bosing.",
                reply_markup=reply_markup,
            )
            return ConversationHandler.END

        # Step 2: Check if returning customer
        status_code, data = await api_get(
            CUSTOMER_CHECK_ENDPOINT,
            params={"telegram_id": telegram_id},
        )
        logger.info(
            "customer-check: telegram_id=%s status=%s body=%s",
            telegram_id, status_code, data,
        )

        if status_code != 200:
            logger.error(
                "customer-check returned %s for telegram_id=%s: %s",
                status_code, telegram_id, data,
            )
            await update.message.reply_text(
                "❌ Server bilan bog'lanishda xatolik.\n"
                "Iltimos /start buyrug'ini qaytadan bosing."
            )
            return ConversationHandler.END

        if data.get("exists"):
            # Returning customer → show app directly (skip registration)
            keyboard = [
                [
                    InlineKeyboardButton(
                        "🏪 Ilovani ochish",
                        web_app={"url": f"{MINI_APP_URL}?mode=buyer"},
                    )
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                "Xush kelibsiz! Ilovani oching 👇",
                reply_markup=reply_markup,
            )
            return ConversationHandler.END

    except aiohttp.ClientError as e:
        logger.exception("Network error for telegram_id=%s", telegram_id)
        await update.message.reply_text(
            "❌ Server bilan bog'lanishda xatolik.\n"
            "Iltimos /start buyrug'ini qaytadan bosing."
        )
        return ConversationHandler.END
    except Exception as e:
        logger.exception("Unexpected error for telegram_id=%s", telegram_id)
        await update.message.reply_text(
            "❌ Xatolik yuz berdi.\n"
            "Iltimos /start buyrug'ini qaytadan bosing."
        )
        return ConversationHandler.END

    # Not a seller, not a returning customer → start registration
    await update.message.reply_text("Assalomu alaykum! Ismingizni kiriting:")
    return ASKING_FIRST_NAME


async def receive_first_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive first name from customer."""
    context.user_data["first_name"] = update.message.text.strip()
    await update.message.reply_text("Familiyangizni kiriting:")
    return ASKING_LAST_NAME


async def receive_last_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive last name from customer."""
    context.user_data["last_name"] = update.message.text.strip()

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
    Receive phone number (CONTACT only) and save customer via POST /api/customers/.
    """
    phone = update.message.contact.phone_number
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
        "Saving customer: telegram_id=%s, name=%s %s",
        telegram_id, first_name, last_name,
    )

    try:
        status_code, body = await api_post(CUSTOMER_ENDPOINT, payload)

        if status_code in (200, 201):
            await update.message.reply_text(
                "✅ Ma'lumotlaringiz saqlandi.\n"
                "Buyurtma berish uchun ilovani oching 👇",
                reply_markup=ReplyKeyboardRemove(),
            )

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
                "❌ Ro'yxatdan o'tishda xatolik yuz berdi.\n"
                "Iltimos /start buyrug'ini qaytadan bosing.",
                reply_markup=ReplyKeyboardRemove(),
            )

    except aiohttp.ClientError as e:
        logger.exception("Network error saving customer telegram_id=%s", telegram_id)
        await update.message.reply_text(
            "❌ Server bilan bog'lanishda xatolik.\n"
            "Iltimos /start buyrug'ini qaytadan bosing.",
            reply_markup=ReplyKeyboardRemove(),
        )
    except Exception as e:
        logger.exception("Unexpected error saving customer telegram_id=%s", telegram_id)
        await update.message.reply_text(
            "❌ Xatolik yuz berdi.\n"
            "Iltimos /start buyrug'ini qaytadan bosing.",
            reply_markup=ReplyKeyboardRemove(),
        )

    context.user_data.clear()
    return ConversationHandler.END


async def phone_text_rejected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User sent text instead of a contact — reject."""
    await update.message.reply_text(
        "❌ Iltimos, telefon raqamingizni pastdagi tugma orqali yuboring.\n"
        "Matn sifatida yubormang."
    )
    return ASKING_PHONE


async def conversation_timeout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Conversation timed out — notify user."""
    if update and update.effective_chat:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="⏱ Vaqt tugadi. Qaytadan boshlash uchun /start buyrug'ini bosing.",
            reply_markup=ReplyKeyboardRemove(),
        )
    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel conversation."""
    await update.message.reply_text(
        "Bekor qilindi. /start buyrug'ini bosing.",
        reply_markup=ReplyKeyboardRemove(),
    )
    context.user_data.clear()
    return ConversationHandler.END


# ============================================
# EXTRA COMMANDS
# ============================================

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /help — show available commands and app link.
    """
    help_text = (
        "🏗 *BuildGo — Qurilish materiallari*\n\n"
        "📋 *Buyruqlar:*\n"
        "/start — Boshlash / Ilovani ochish\n"
        "/orders — Buyurtmalarim\n"
        "/help — Yordam\n"
        "/cancel — Bekor qilish\n\n"
        "Savol yoki muammo bo'lsa, admin bilan bog'laning."
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")


async def orders_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /orders — show recent orders for this user.
    """
    telegram_id = update.effective_user.id

    try:
        status_code, data = await api_get(
            CUSTOMER_ORDERS_ENDPOINT,
            params={"telegram_id": telegram_id},
        )

        if status_code != 200:
            await update.message.reply_text(
                "Buyurtmalarni yuklashda xatolik. /start buyrug'ini bosing."
            )
            return

        # Handle paginated response
        results = data.get("results", data) if isinstance(data, dict) else data

        if not results:
            await update.message.reply_text(
                "📦 Sizda hali buyurtmalar yo'q.\n"
                "Ilovani ochib buyurtma bering!"
            )
            return

        # Show last 5 orders
        lines = ["📦 *Oxirgi buyurtmalaringiz:*\n"]
        for order in results[:5]:
            status_emoji = {
                "new": "🆕",
                "processing": "⏳",
                "done": "✅",
                "cancelled": "❌",
            }.get(order.get("status", ""), "❓")

            items_count = len(order.get("items", []))
            store_name = order.get("store_name", "—")

            lines.append(
                f"{status_emoji} *#{order['id']}* — {store_name} "
                f"({items_count} mahsulot)"
            )

        lines.append("\nBatafsil ko'rish uchun ilovani oching.")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    except aiohttp.ClientError:
        logger.exception("Network error fetching orders for telegram_id=%s", telegram_id)
        await update.message.reply_text(
            "❌ Server bilan bog'lanishda xatolik.\n"
            "Iltimos keyinroq urinib ko'ring."
        )
    except Exception:
        logger.exception("Unexpected error fetching orders for telegram_id=%s", telegram_id)
        await update.message.reply_text(
            "❌ Xatolik yuz berdi. Iltimos keyinroq urinib ko'ring."
        )


# ============================================
# MAIN
# ============================================

def main():
    """Start the bot."""
    if not BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not found in environment variables!")
        return

    if not MINI_APP_URL:
        logger.error("MINI_APP_URL not found in environment variables!")
        return

    if not BOT_API_SECRET:
        logger.warning("BOT_API_SECRET not set — API calls will fail authentication!")

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ASKING_FIRST_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_first_name),
            ],
            ASKING_LAST_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_last_name),
            ],
            ASKING_PHONE: [
                MessageHandler(filters.CONTACT, receive_phone),
                MessageHandler(filters.TEXT & ~filters.COMMAND, phone_text_rejected),
            ],
            ConversationHandler.TIMEOUT: [
                MessageHandler(filters.ALL, conversation_timeout),
            ],
        },
        fallbacks=[
            CommandHandler("start", start),
            CommandHandler("cancel", cancel),
        ],
        conversation_timeout=300,  # 5 minutes
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("orders", orders_command))

    logger.info("Bot started (production-hardened)...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
