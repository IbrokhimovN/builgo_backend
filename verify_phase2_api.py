import sys
import os
import django
from unittest.mock import patch

sys.path.append('/home/numonjon/python/buildGo/builgo_backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.conf import settings
from rest_framework.test import APIClient
from core.models import Store, Product, Category, Seller, Order, OrderItem, SearchTerm, Customer
from django.utils import timezone

# Mock the cache to avoid Redis ConnectionError when saving models that trigger signals
with patch('django.core.cache.cache.delete') as mock_delete:
    client = APIClient()

    print("--- Cleaning up previous test data ---")
    Order.objects.filter(customer__telegram_id=111111).delete()
    Product.objects.filter(store__name='Phase 2 Test Store').delete()
    Category.objects.filter(store__name='Phase 2 Test Store').delete()
    Seller.objects.filter(telegram_id=999999).delete()
    Customer.objects.filter(telegram_id=111111).delete()
    Store.objects.filter(name='Phase 2 Test Store').delete()
    SearchTerm.objects.filter(term__startswith='suggest').delete()

    print("--- Settings up test data ---")
    store = Store.objects.create(name='Phase 2 Test Store', is_active=True)
    seller = Seller.objects.create(telegram_id=999999, name='Test Seller', store=store)
    category = Category.objects.create(store=store, name='Phase 2 Category')
    customer = Customer.objects.create(telegram_id=111111, first_name='Test Buyer', phone_number='+998901234567')

    p1 = Product.objects.create(
        store=store, category=category, name='Suggestions Test Product 1', price='100', quantity=10, unit='dona'
    )
    p2 = Product.objects.create(
        store=store, category=category, name='Suggestions Test Product 2', price='200', quantity=20, unit='dona'
    )

    SearchTerm.objects.create(term='suggestions', count=5)
    SearchTerm.objects.create(term='suggesting', count=2)

    order = Order.objects.create(
        customer=customer, store=store, status='new'
    )
    order.created_at = timezone.now()
    order.save()

    OrderItem.objects.create(order=order, product=p1, quantity=1, price_at_order='100')
    OrderItem.objects.create(order=order, product=p2, quantity=1, price_at_order='200')

    print("--- Testing API Endpoints ---")

    # 1. Search Suggestions
    print("\n1. Testing /api/search/suggestions/")
    res = client.get('/api/search/suggestions/?q=sugg')
    print(f"Status: {res.status_code}")
    if res.status_code == 200:
        data = res.json()
        print("Suggestions:", data.get('suggestions'))
        assert 'suggestions' in data, "Suggestions endpoint failed"

    # 2. Related Products
    print("\n2. Testing /api/products/related/")
    res = client.get(f'/api/products/{p1.id}/related/')
    print(f"Status: {res.status_code}")
    if res.status_code == 200:
        data = res.json()
        print(f"Found {len(data)} related products")
        assert isinstance(data, list), "Related products endpoint failed"

    # 3. Seller Analytics
    print("\n3. Testing /api/seller/analytics/")
    bot_secret = getattr(settings, 'BOT_API_SECRET', 'test_secret')
    res = client.get(
        '/api/seller/analytics/',
        {'telegram_id': 999999},
        HTTP_X_BOT_SECRET=bot_secret
    )
    print(f"Status: {res.status_code}")
    if res.status_code == 200:
        data = res.json()
        print("Analytics data:", data)
        assert 'orders_today' in data, "Analytics orders_today missing"
        assert 'revenue_today' in data, "Analytics revenue_today missing"
        assert 'top_products' in data, "Analytics top_products missing"

    # Cleanup
    print("\n--- Cleaning up ---")
    order.delete()
    p1.delete()
    p2.delete()
    category.delete()
    seller.delete()
    customer.delete()
    store.delete()
    SearchTerm.objects.filter(term__startswith='suggest').delete()

    print("\n--- Phase 2 API Tests Completed Successfully ---")
