import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

def notify_seller_new_order(order):
    try:
        seller = order.store.sellers.filter(is_active=True).first()
        if not seller or not seller.telegram_id:
            return

        customer = order.customer
        location = customer.locations.filter(is_default=True).first()

        map_link = "Manzil ko'rsatilmagan"
        if location:
            map_link = f"https://www.google.com/maps?q={location.latitude},{location.longitude}"

        message = (
            "📦 New Order!\n\n"
            f"Order ID: #{order.id}\n"
            f"Customer: {customer.first_name}\n"
            f"📍 Xarita: {map_link}"
        )

        url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": seller.telegram_id,
            "text": message
        }

        requests.post(url, json=payload, timeout=5)

    except Exception:
        logger.exception("Telegram notification failed")
