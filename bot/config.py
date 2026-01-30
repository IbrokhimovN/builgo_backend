"""
Configuration for Telegram bot.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# Bot configuration
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
MINI_APP_URL = os.getenv('MINI_APP_URL')

# Backend API configuration
BACKEND_URL = os.getenv('BACKEND_URL', 'http://localhost:8000')
TELEGRAM_AUTH_ENDPOINT = f'{BACKEND_URL}/api/telegram-auth/'
CHECK_SELLER_ENDPOINT = f'{BACKEND_URL}/api/check-seller/'
