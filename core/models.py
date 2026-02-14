"""
Core models for BuildGo Backend.
Custom User model extending AbstractUser for JWT authentication.
Authentication is via Telegram Mini App initData → JWT tokens.
"""

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    """
    Custom manager for User model with telegram_id as USERNAME_FIELD.
    """
    def create_user(self, telegram_id, first_name='', password=None, **extra_fields):
        if not telegram_id:
            raise ValueError('telegram_id is required')
        extra_fields.setdefault('is_active', True)
        user = self.model(
            telegram_id=telegram_id,
            first_name=first_name,
            **extra_fields
        )
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, telegram_id, first_name='Admin', password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('role', 'seller')
        return self.create_user(telegram_id, first_name, password, **extra_fields)


class User(AbstractUser):
    """
    Custom User model based on Telegram identity.
    Extends AbstractUser for SimpleJWT compatibility.
    USERNAME_FIELD is telegram_id — login by Telegram ID.
    """
    ROLE_CHOICES = [
        ('buyer', 'Buyer'),
        ('seller', 'Seller'),
    ]

    telegram_id = models.BigIntegerField(unique=True, db_index=True)
    phone = models.CharField(max_length=20, blank=True, default='')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='buyer')

    # Override username — not used for Telegram auth, but required by AbstractUser
    username = models.CharField(max_length=150, blank=True, null=True, unique=True)

    objects = UserManager()

    USERNAME_FIELD = 'telegram_id'
    REQUIRED_FIELDS = ['first_name']

    class Meta:
        db_table = 'users'
        ordering = ['-date_joined']

    def __str__(self):
        return f"{self.first_name} {self.last_name} (@{self.telegram_id})"


class Store(models.Model):
    """
    Store model - represents a seller's store.
    """
    name = models.CharField(max_length=200)
    image = models.ImageField(upload_to='stores/', null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'stores'
        ordering = ['name']

    def __str__(self):
        return self.name


class Seller(models.Model):
    """
    Seller profile - links a User to a Store.
    One user can be a seller for one store (OneToOne).
    Multiple sellers can work for the same store (if needed in future).
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='seller_profile'
    )
    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name='sellers'
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'sellers'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.first_name} - {self.store.name}"


class Category(models.Model):
    """
    Product category - scoped to a specific store.
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
    Product model - belongs to a store and optionally a category.
    """
    UNIT_CHOICES = [
        ('qop', 'Qop'),
        ('dona', 'Dona'),
        ('kg', 'KG'),
        ('m', 'Metr'),
    ]

    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
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
    image = models.ImageField(upload_to='products/', null=True, blank=True)
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'products'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} - {self.price} ({self.unit})"


class Order(models.Model):
    """
    Order model - buyer places order at a store.
    """
    STATUS_CHOICES = [
        ('new', 'New'),
        ('done', 'Done'),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='orders'
    )
    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name='orders'
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='new')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'orders'
        ordering = ['-created_at']

    def __str__(self):
        return f"Order #{self.id} - {self.user.first_name} @ {self.store.name}"


class OrderItem(models.Model):
    """
    Order item - products in an order.
    """
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='items'
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE
    )
    quantity = models.PositiveIntegerField()
    price_at_order = models.DecimalField(max_digits=10, decimal_places=2)  # Store price snapshot

    class Meta:
        db_table = 'order_items'

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"


class Location(models.Model):
    """
    Location model for customers (users) and sellers (stores).
    - Customer location: user is set, store is null
    - Seller/Store location: store is set, user is null
    """
    name = models.CharField(max_length=100)  # e.g., "Home", "Office", "Warehouse"
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    address = models.TextField()

    # For customer locations
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='locations',
        null=True,
        blank=True
    )

    # For seller/store locations
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

    def __str__(self):
        owner = self.user or self.store
        return f"{self.name} - {owner}"

    def save(self, *args, **kwargs):
        # Ensure only one default location per user/store
        if self.is_default:
            if self.user:
                Location.objects.filter(user=self.user, is_default=True).update(is_default=False)
            elif self.store:
                Location.objects.filter(store=self.store, is_default=True).update(is_default=False)
        super().save(*args, **kwargs)
