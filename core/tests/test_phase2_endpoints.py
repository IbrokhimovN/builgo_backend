from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from core.models import Store, Product, Category, Seller, Order, OrderItem, SearchTerm, Customer
from django.utils import timezone
from datetime import timedelta

@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}})
class Phase2APITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.store = Store.objects.create(name='Phase 2 Test Store', is_active=True)
        self.seller = Seller.objects.create(telegram_id=999999, name='Test Seller', store=self.store)
        self.category = Category.objects.create(store=self.store, name='Phase 2 Category')
        self.customer = Customer.objects.create(telegram_id=111111, first_name='Test Buyer', phone_number='+998901234567')

        self.p1 = Product.objects.create(
            store=self.store, category=self.category, name='Suggestions Test Product 1', price='100', quantity=10, unit='dona'
        )
        self.p2 = Product.objects.create(
            store=self.store, category=self.category, name='Suggestions Test Product 2', price='200', quantity=20, unit='dona'
        )

        SearchTerm.objects.create(term='suggestions', count=5)
        SearchTerm.objects.create(term='suggesting', count=2)

        self.order = Order.objects.create(
            customer=self.customer, store=self.store, status='new'
        )
        # Manually alter created_at to today
        self.order.created_at = timezone.now()
        self.order.save()

        OrderItem.objects.create(order=self.order, product=self.p1, quantity=1, price_at_order='100')
        OrderItem.objects.create(order=self.order, product=self.p2, quantity=1, price_at_order='200')

    def test_search_suggestions_api(self):
        res = self.client.get('/api/search/suggestions/?q=sugg')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn('suggestions', data)
        self.assertTrue(len(data['suggestions']) > 0)

    def test_related_products_api(self):
        res = self.client.get(f'/api/products/{self.p1.id}/related/')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIsInstance(data, list)

    @override_settings(BOT_API_SECRET='test_secret')
    def test_seller_analytics_api(self):
        res = self.client.get(
            '/api/seller/analytics/',
            {'telegram_id': 999999},
            **{'HTTP_X_BOT_SECRET': 'test_secret'}
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn('orders_today', data)
        self.assertIn('revenue_today', data)
        self.assertIn('top_products', data)
        self.assertEqual(data['orders_today'], 1)
        self.assertEqual(data['revenue_today'], 300.0)
