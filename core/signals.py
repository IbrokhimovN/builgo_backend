from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from .models import Order, Store, Category, Product
from .tasks import notify_seller_new_order_task

@receiver(post_save, sender=Order)
def notify_seller_on_new_order(sender, instance, created, **kwargs):
    if created:
        notify_seller_new_order_task.delay(instance.id)

@receiver([post_save, post_delete], sender=Store)
def invalidate_store_cache(sender, instance, **kwargs):
    cache.delete('stores_list_active')

@receiver([post_save, post_delete], sender=Category)
def invalidate_category_cache(sender, instance, **kwargs):
    store_id = instance.store_id
    cache.delete(f'store_{store_id}_categories')

@receiver([post_save, post_delete], sender=Product)
def invalidate_product_cache(sender, instance, **kwargs):
    store_id = instance.store_id
    try:
        cache.delete_pattern(f"*store_{store_id}_products_*")
    except AttributeError:
        pass
