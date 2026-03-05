import logging
import requests
from celery import shared_task
from django.conf import settings
from .models import Order

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3)
def notify_seller_new_order_task(self, order_id):
    try:
        order = Order.objects.select_related('store', 'customer').get(id=order_id)
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

        response = requests.post(url, json=payload, timeout=5)
        response.raise_for_status()

    except requests.exceptions.RequestException as exc:
        logger.exception("Telegram API error")
        raise self.retry(exc=exc, countdown=10) # Retry after 10 seconds if network fails
    except Order.DoesNotExist:
        logger.warning(f"Order {order_id} no longer exists for notification.")
    except Exception as exc:
        logger.exception("Unexpected error in Telegram notification")
