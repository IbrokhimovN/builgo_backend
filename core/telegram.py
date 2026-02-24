import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

def notify_seller_new_order(order):
    """
    Send a Telegram message to the seller when a new order is placed.
    Fails silently so as to not block order creation.
    """
    try:
        # Get active seller
        seller = order.store.sellers.filter(is_active=True).first()
        if not seller:
            return

        message = (
            "📦 New Order!\n\n"
            f"Order ID: #{order.id}\n"
            f"Customer: {order.customer.first_name}"
        )

        bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', None)
        if not bot_token:
            logger.error("TELEGRAM_BOT_TOKEN is not set in settings.")
            return

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": seller.telegram_id,
            "text": message,
            "parse_mode": "Markdown"
        }

        # Use a short timeout to prevent blocking
        response = requests.post(url, json=payload, timeout=5)
        response.raise_for_status()

    except Exception as e:
        logger.error(f"Failed to send Telegram notification to seller for Order #{order.id}: {e}")
