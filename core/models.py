"""
Core models for BuildGo Backend.
Telegram-only identity: Customer (data) + Seller (admin-controlled).
NO Django User model. NO authentication.
"""

from django.db import models
from django.db.models import Q, Avg
from django.utils import timezone
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField, SearchVector


class Customer(models.Model):
    """
    Customer model — data only, NOT auth.
    Created by Telegram bot when buyer registers.
    """
    telegram_id = models.BigIntegerField(unique=True, db_index=True)
    first_name = models.CharField(max_length=150, blank=True, default='')
    last_name = models.CharField(max_length=150, blank=True, default='')
    phone = models.CharField(max_length=20, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'customers'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.telegram_id})"


class Store(models.Model):
    """
    Store model — represents a seller's store.
    """
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    phone = models.CharField(max_length=20, blank=True, default='')
    image = models.ImageField(upload_to='stores/', null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'stores'
        ordering = ['name']
        indexes = [
            models.Index(fields=['is_active', 'created_at']),
            models.Index(fields=['name']),
        ]

    def __str__(self):
        return self.name

    @property
    def average_rating(self):
        avg = self.ratings.aggregate(avg=Avg('rating'))['avg']
        return round(avg, 1) if avg else 0.0

    @property
    def ratings_count(self):
        return self.ratings.count()

    @property
    def is_open(self):
        if not self.is_active:
            return False
        now = timezone.localtime()
        today = now.weekday()
        schedule = self.working_hours.filter(day_of_week=today).first()
        if not schedule:
            return False
        return schedule.open_time <= now.time() <= schedule.close_time


class StoreWorkingHours(models.Model):
    """
    Working hours per day for a store.
    """
    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name="working_hours"
    )
    day_of_week = models.IntegerField()  # 0=Monday, 6=Sunday
    open_time = models.TimeField()
    close_time = models.TimeField()

    class Meta:
        db_table = 'store_working_hours'
        unique_together = ('store', 'day_of_week')
        ordering = ['day_of_week']

    def __str__(self):
        return f"{self.store.name} - Day {self.day_of_week} ({self.open_time} - {self.close_time})"


class StoreRating(models.Model):
    """
    Store rating by a customer.
    Customer can rate a store 1-5.
    """
    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name="ratings"
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="store_ratings"
    )
    rating = models.IntegerField()  # 1-5
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'store_ratings'
        unique_together = ('store', 'customer')

    def __str__(self):
        return f"{self.customer} rated {self.store} {self.rating} stars"


class Seller(models.Model):
    """
    Seller model — admin-controlled ONLY.
    Created exclusively via Django Admin.
    NOT linked to Customer. NOT linked to User.
    Identity = telegram_id.
    """
    telegram_id = models.BigIntegerField(unique=True, db_index=True)
    name = models.CharField(max_length=150)
    store = models.ForeignKey(
        Store,
        on_delete=models.PROTECT,
        related_name='sellers'
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'sellers'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} - {self.store.name}"


class Category(models.Model):
    """
    Product category — scoped to a specific store.
    """
    name = models.CharField(max_length=100)
    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name='categories'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'categories'
        ordering = ['name']
        verbose_name_plural = 'Categories'

    def __str__(self):
        return f"{self.name} ({self.store.name})"


class Product(models.Model):
    """
    Product model — belongs to a store and optionally a category.
    """
    UNIT_CHOICES = [
        ('qop', 'Qop'),
        ('dona', 'Dona'),
        ('kg', 'KG'),
        ('m', 'Metr'),
        ('m2',"Metr kvadrat")
    ]

    store = models.ForeignKey(
        Store,
        on_delete=models.PROTECT,
        related_name='products'
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='products'
    )
    name = models.CharField(max_length=200)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    unit = models.CharField(max_length=10, choices=UNIT_CHOICES)
    description = models.TextField(blank=True)
    quantity = models.PositiveIntegerField(default=0)
    image = models.ImageField(upload_to='products/', null=True, blank=True)
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    search_vector = SearchVectorField(null=True, blank=True)

    class Meta:
        db_table = 'products'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['category', 'is_available']),
            models.Index(fields=['store', 'is_available']),
            models.Index(fields=['is_available', 'price']),
            GinIndex(fields=['search_vector']),
        ]

    def __str__(self):
        return f"{self.name} - {self.price} ({self.unit})"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Update the search vector asynchronously or in-place
        Product.objects.filter(pk=self.pk).update(
            search_vector=SearchVector('name', 'description')
        )


class Order(models.Model):
    """
    Order model — customer places order at a store.
    References Customer (NOT User). Seller never referenced.
    """
    STATUS_CHOICES = [
        ('new', 'New'),
        ('processing', 'Processing'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ]

    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name='orders'
    )
    store = models.ForeignKey(
        Store,
        on_delete=models.PROTECT,
        related_name='orders'
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='new')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'orders'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['store', 'status']),
            models.Index(fields=['customer', 'status']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"Order #{self.id} - {self.customer.first_name} @ {self.store.name}"


class OrderItem(models.Model):
    """
    Order item — products in an order.
    """
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='items'
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT
    )
    quantity = models.PositiveIntegerField()
    price_at_order = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = 'order_items'

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"


class Location(models.Model):
    """
    Location model for customers and stores.
    - Customer location: customer is set, store is null
    - Store location: store is set, customer is null
    """
    name = models.CharField(max_length=100)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    address = models.TextField()

    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name='locations',
        null=True,
        blank=True
    )
    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name='locations',
        null=True,
        blank=True
    )

    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'locations'
        ordering = ['-is_default', '-created_at']
        constraints = [
            models.CheckConstraint(
                check=~Q(customer__isnull=True, store__isnull=True),
                name='location_must_have_owner',
            ),
            models.CheckConstraint(
                check=Q(customer__isnull=True) | Q(store__isnull=True),
                name='location_cannot_have_both_owners',
            ),
        ]

    def __str__(self):
        owner = self.customer or self.store
        return f"{self.name} - {owner}"

    def save(self, *args, **kwargs):
        if self.is_default:
            if self.customer:
                Location.objects.filter(customer=self.customer, is_default=True).update(is_default=False)
            elif self.store:
                Location.objects.filter(store=self.store, is_default=True).update(is_default=False)
        super().save(*args, **kwargs)
