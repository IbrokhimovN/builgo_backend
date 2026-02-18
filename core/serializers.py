"""
DRF Serializers for BuildGo Backend.
No User model. No auth. telegram_id is identity.
"""

import logging
from django.db import transaction
from rest_framework import serializers
from .models import (
    Customer, Store, Seller, Category, Product, Order, OrderItem, Location
)

logger = logging.getLogger(__name__)


class CustomerSerializer(serializers.ModelSerializer):
    """
    Customer serializer.
    telegram_id is write_only — never exposed in responses.
    """
    class Meta:
        model = Customer
        fields = ['id', 'telegram_id', 'first_name', 'last_name', 'phone', 'created_at']
        read_only_fields = ['id', 'created_at']
        extra_kwargs = {
            'telegram_id': {'write_only': True},
        }


class StoreSerializer(serializers.ModelSerializer):
    """
    Store serializer for listing stores.
    """
    class Meta:
        model = Store
        fields = ['id', 'name', 'image', 'is_active', 'created_at']
        read_only_fields = ['id', 'created_at']


class CategorySerializer(serializers.ModelSerializer):
    """
    Category serializer.
    store is optional on input — auto-assigned by seller endpoint.
    """
    class Meta:
        model = Category
        fields = ['id', 'name', 'store']
        read_only_fields = ['id']
        extra_kwargs = {
            'store': {'required': False},
        }


class ProductSerializer(serializers.ModelSerializer):
    """
    Product serializer with category details.
    """
    category_name = serializers.CharField(source='category.name', read_only=True, allow_null=True)
    store_name = serializers.CharField(source='store.name', read_only=True)

    class Meta:
        model = Product
        fields = [
            'id', 'store', 'store_name', 'category', 'category_name',
            'name', 'price', 'unit', 'image', 'is_available', 'created_at'
        ]
        read_only_fields = ['id', 'created_at', 'store_name', 'category_name']


class ProductCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating/updating products by sellers.
    Store is auto-assigned, not from request data.
    """
    class Meta:
        model = Product
        fields = ['id', 'category', 'name', 'price', 'unit', 'image', 'is_available']
        read_only_fields = ['id']

    def validate_price(self, value):
        """Price must be positive."""
        if value <= 0:
            raise serializers.ValidationError("Price must be greater than 0")
        return value

    def validate_name(self, value):
        """Strip whitespace and enforce length."""
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Product name cannot be empty")
        if len(value) > 200:
            raise serializers.ValidationError("Product name too long (max 200 chars)")
        return value


class OrderItemSerializer(serializers.ModelSerializer):
    """
    Order item serializer.
    """
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_unit = serializers.CharField(source='product.unit', read_only=True)

    class Meta:
        model = OrderItem
        fields = ['id', 'product', 'product_name', 'product_unit', 'quantity', 'price_at_order']
        read_only_fields = ['id', 'product_name', 'product_unit', 'price_at_order']


class OrderSerializer(serializers.ModelSerializer):
    """
    Order serializer with items.
    """
    items = OrderItemSerializer(many=True, read_only=True)
    customer_name = serializers.SerializerMethodField()
    store_name = serializers.CharField(source='store.name', read_only=True)

    class Meta:
        model = Order
        fields = [
            'id', 'customer', 'customer_name', 'store', 'store_name',
            'status', 'items', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'customer', 'created_at', 'updated_at', 'customer_name', 'store_name']

    def get_customer_name(self, obj):
        return f"{obj.customer.first_name} {obj.customer.last_name}"


class OrderItemInputSerializer(serializers.Serializer):
    """
    Typed serializer for order item input.
    Replaces untyped DictField for proper validation.
    """
    product = serializers.IntegerField(min_value=1)
    quantity = serializers.IntegerField(min_value=1)


class OrderCreateSerializer(serializers.Serializer):
    """
    Serializer for creating orders.
    Accepts store_id and list of items.
    telegram_id is injected by the view from auth context (NOT from request body).
    """
    telegram_id = serializers.IntegerField(min_value=1, required=False)
    store = serializers.PrimaryKeyRelatedField(queryset=Store.objects.filter(is_active=True))
    items = OrderItemInputSerializer(many=True)

    def validate_items(self, items):
        """Validate that items list is not empty."""
        if not items:
            raise serializers.ValidationError("Order must have at least one item")
        return items

    def create(self, validated_data):
        """
        Create order with items.
        Atomic: either all items are created or none.
        Validates each product exists, belongs to the store, and is available.
        """
        telegram_id = validated_data['telegram_id']
        store = validated_data['store']
        items_data = validated_data['items']

        with transaction.atomic():
            # Get or create customer (race-condition safe via unique constraint)
            customer, _ = Customer.objects.get_or_create(
                telegram_id=telegram_id,
                defaults={'first_name': '', 'last_name': ''}
            )

            # Create order
            order = Order.objects.create(
                customer=customer,
                store=store,
                status='new'
            )

            # Validate and create order items
            for item_data in items_data:
                try:
                    product = Product.objects.get(
                        id=item_data['product'],
                        store=store,
                        is_available=True
                    )
                except Product.DoesNotExist:
                    raise serializers.ValidationError(
                        f"Product {item_data['product']} not found, "
                        f"unavailable, or does not belong to this store"
                    )

                OrderItem.objects.create(
                    order=order,
                    product=product,
                    quantity=item_data['quantity'],
                    price_at_order=product.price
                )

            logger.info(
                "Order #%d created: customer=%d, store=%s, items=%d",
                order.id, telegram_id, store.name, len(items_data)
            )

        return order


class SellerSerializer(serializers.ModelSerializer):
    """
    Seller profile serializer.
    """
    store = StoreSerializer(read_only=True)

    class Meta:
        model = Seller
        fields = ['id', 'telegram_id', 'name', 'store', 'is_active', 'created_at']
        read_only_fields = ['id', 'created_at']


class LocationSerializer(serializers.ModelSerializer):
    """
    Location serializer for reading location details.
    """
    customer_name = serializers.SerializerMethodField()
    store_name = serializers.CharField(source='store.name', read_only=True, allow_null=True)

    class Meta:
        model = Location
        fields = [
            'id', 'name', 'latitude', 'longitude', 'address',
            'customer', 'customer_name', 'store', 'store_name',
            'is_default', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'customer_name', 'store_name']

    def get_customer_name(self, obj):
        if obj.customer:
            return f"{obj.customer.first_name} {obj.customer.last_name}"
        return None


class LocationCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating/updating locations.
    Customer or store is auto-assigned based on context.
    """
    class Meta:
        model = Location
        fields = ['id', 'name', 'latitude', 'longitude', 'address', 'is_default']
        read_only_fields = ['id']
