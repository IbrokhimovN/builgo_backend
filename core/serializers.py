"""
DRF Serializers for BuildGo Backend.
No User model. No auth. telegram_id is identity.
"""

from rest_framework import serializers
from .models import (
    Customer, Store, Seller, Category, Product, Order, OrderItem, Location
)


class CustomerSerializer(serializers.ModelSerializer):
    """
    Customer serializer.
    """
    class Meta:
        model = Customer
        fields = ['id', 'telegram_id', 'first_name', 'last_name', 'phone', 'created_at']
        read_only_fields = ['id', 'created_at']


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
    """
    class Meta:
        model = Category
        fields = ['id', 'name', 'store']
        read_only_fields = ['id']


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


class OrderCreateSerializer(serializers.Serializer):
    """
    Serializer for creating orders.
    Accepts telegram_id, store_id and list of items.
    """
    telegram_id = serializers.IntegerField()
    store = serializers.PrimaryKeyRelatedField(queryset=Store.objects.filter(is_active=True))
    items = serializers.ListField(
        child=serializers.DictField(),
        write_only=True
    )

    def validate_items(self, items):
        """Validate that items list is not empty and has required fields."""
        if not items:
            raise serializers.ValidationError("Order must have at least one item")

        for item in items:
            if 'product' not in item or 'quantity' not in item:
                raise serializers.ValidationError("Each item must have 'product' and 'quantity'")

            if item['quantity'] <= 0:
                raise serializers.ValidationError("Quantity must be greater than 0")

        return items

    def create(self, validated_data):
        """Create order with items."""
        telegram_id = validated_data['telegram_id']
        store = validated_data['store']
        items_data = validated_data.pop('items')

        # Get or create customer
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

        # Create order items
        for item_data in items_data:
            product = Product.objects.get(id=item_data['product'])
            OrderItem.objects.create(
                order=order,
                product=product,
                quantity=item_data['quantity'],
                price_at_order=product.price
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
