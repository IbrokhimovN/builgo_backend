from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Order
from .telegram import notify_seller_new_order

@receiver(post_save, sender=Order)
def notify_seller_on_new_order(sender, instance, created, **kwargs):
    if created:
        notify_seller_new_order(instance)
