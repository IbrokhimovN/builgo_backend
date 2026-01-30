"""
BuildGo Telegram Bot - Main Entry Point

Handles user registration and authentication for Telegram Mini App.

Two flows:
1. Buyer: Collect name and phone, register in backend, show Mini App
2. Seller: Verify seller status, show Mini App with seller mode
"""

import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
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
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
SELECTING_ROLE, ASKING_FIRST_NAME, ASKING_LAST_NAME, ASKING_PHONE = range(4)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    /start command - Show role selection buttons.
    """
    keyboard = [
        [
            InlineKeyboardButton("🧱 Xaridor", callback_data='buyer'),
            InlineKeyboardButton("🏪 Sotuvchi", callback_data='seller')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Assalomu alaykum! Rolni tanlang:",
        reply_markup=reply_markup
    )
    
    return SELECTING_ROLE


async def role_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle role selection (buyer or seller).
    """
    query = update.callback_query
    await query.answer()
    
    role = query.data
    context.user_data['role'] = role
    
    if role == 'buyer':
        # Start buyer registration flow
        await query.edit_message_text("Ismingizni kiriting:")
        return ASKING_FIRST_NAME
    
    elif role == 'seller':
        # Check if user is a seller
        telegram_id = update.effective_user.id
        
        try:
            response = requests.get(
                CHECK_SELLER_ENDPOINT,
                params={'telegram_id': telegram_id},
                timeout=10
            )
            data = response.json()
            
            if data.get('is_seller'):
                # User is a seller, show Mini App button
                await query.edit_message_text(
                    "✅ Xush kelibsiz!\n"
                    "Dashboard'ni ochish uchun pastdagi tugmani bosing."
                )
                
                # Send Mini App button
                keyboard = [[
                    InlineKeyboardButton(
                        "📊 Dashboard",
                        web_app={'url': f"{MINI_APP_URL}?mode=seller"}
                    )
                ]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.effective_user.send_message(
                    "Dashboard:",
                    reply_markup=reply_markup
                )
            else:
                # Not a seller
                await query.edit_message_text(
                    "❌ Siz sotuvchi sifatida ro'yxatdan o'tmagansiz.\n"
                    "Administrator bilan bog'laning."
                )
        
        except Exception as e:
            logger.error(f"Error checking seller status: {e}")
            await query.edit_message_text(
                "❌ Xatolik yuz berdi. Iltimos qaytadan urinib ko'ring."
            )
        
        return ConversationHandler.END


async def receive_first_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Receive first name from buyer.
    """
    context.user_data['first_name'] = update.message.text
    await update.message.reply_text("Familiyangizni kiriting:")
    return ASKING_LAST_NAME


async def receive_last_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Receive last name from buyer.
    """
    context.user_data['last_name'] = update.message.text
    
    # Request phone number using Telegram contact button
    keyboard = [
        [KeyboardButton("📱 Telefon raqamni yuborish", request_contact=True)]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    await update.message.reply_text(
        "Telefon raqamingizni yuboring:",
        reply_markup=reply_markup
    )
    return ASKING_PHONE


async def receive_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Receive phone number and register user in backend.
    """
    # Get phone from contact
    if update.message.contact:
        phone = update.message.contact.phone_number
    else:
        await update.message.reply_text(
            "❌ Iltimos, telefon raqamingizni tugma orqali yuboring."
        )
        return ASKING_PHONE
    
    # Prepare data for backend
    telegram_id = update.effective_user.id
    first_name = context.user_data.get('first_name')
    last_name = context.user_data.get('last_name')
    
    payload = {
        'telegram_id': telegram_id,
        'first_name': first_name,
        'last_name': last_name,
        'phone': phone
    }
    
    try:
        # Send to backend
        response = requests.post(
            TELEGRAM_AUTH_ENDPOINT,
            json=payload,
            timeout=10
        )
        
        if response.status_code in [200, 201]:
            # Success - show Mini App button
            await update.message.reply_text(
                "✅ Ma'lumotlaringiz saqlandi.\n"
                "Buyurtma berish uchun ilovani oching 👇",
                reply_markup={'remove_keyboard': True}
            )
            
            # Send Mini App button
            keyboard = [[
                InlineKeyboardButton(
                    "🏪 Ilovani ochish",
                    web_app={'url': f"{MINI_APP_URL}?mode=buyer"}
                )
            ]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.effective_user.send_message(
                "Ilova:",
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                "❌ Xatolik yuz berdi. Iltimos qaytadan urinib ko'ring."
            )
    
    except Exception as e:
        logger.error(f"Error registering user: {e}")
        await update.message.reply_text(
            "❌ Xatolik yuz berdi. Iltimos qaytadan urinib ko'ring."
        )
    
    # Clear user data
    context.user_data.clear()
    
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Cancel conversation.
    """
    await update.message.reply_text(
        "Bekor qilindi. /start buyrug'ini bosing."
    )
    context.user_data.clear()
    return ConversationHandler.END


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
        entry_points=[CommandHandler('start', start)],
        states={
            SELECTING_ROLE: [CallbackQueryHandler(role_selected)],
            ASKING_FIRST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_first_name)],
            ASKING_LAST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_last_name)],
            ASKING_PHONE: [MessageHandler(filters.CONTACT | filters.TEXT, receive_phone)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    
    application.add_handler(conv_handler)
    
    # Start the bot
    logger.info("Bot started...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
