import os
import django
os.environ['DJANGO_SETTINGS_MODULE'] = 'builgo_backend.settings'
django.setup()

from core.models import Customer, Store, Product
from core.serializers import OrderCreateSerializer
from rest_framework.test import APIClient
from django.urls import reverse
from django.conf import settings

client = APIClient()

c, _ = Customer.objects.get_or_create(telegram_id=99991234, defaults={'phone': ''})
s = Store.objects.filter(is_active=True).first()
if getattr(s, 'id', None) is None:
    s = Store.objects.create(name='test')
p = Product.objects.filter(store=s).first()
if getattr(p, 'id', None) is None:
    p = Product.objects.create(store=s, name='t', price=1, unit='dona', quantity=10, is_available=True)

data = {
    'telegram_id': 99991234,
    'store': s.id,
    'items': [{'product': p.id, 'quantity': 1}]
}

url = reverse('order-create')
client.credentials(HTTP_X_TELEGRAM_BOT_SECRET=settings.TELEGRAM_BOT_TOKEN)

print("--- Testing Without Phone ---")
c.phone = ''
c.save()
res1 = client.post(url, data, format='json')
print(f"Status: {res1.status_code}")
print(f"Data: {res1.json()}")

print("--- Testing With Phone, Without Location ---")
c.phone = '+998901234567'
c.save()
res2 = client.post(url, data, format='json')
print(f"Status: {res2.status_code}")
print(f"Data: {res2.json()}")

print("--- Testing With Phone, With Location ---")
from core.models import Location
loc, _ = Location.objects.get_or_create(customer=c, name='home', defaults={'address': '1', 'latitude': 0, 'longitude': 0, 'is_default': True})
res3 = client.post(url, data, format='json')
print(f"Status: {res3.status_code}")
print(f"Data: {res3.json()}")

p.refresh_from_db()
print(f"--- Product Quantity after success: {p.quantity} ---")
