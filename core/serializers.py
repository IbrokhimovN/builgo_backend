"""
DRF Serializers for BuildGo Backend.
"""

from rest_framework import serializers
from .models import (
    User, Store, Seller, Category, Product, Order, OrderItem, Location
)


class UserSerializer(serializers.ModelSerializer):
    """
    User profile serializer.
    """
    class Meta:
        model = User
        fields = ['id', 'telegram_id', 'first_name', 'last_name', 'phone', 'role', 'date_joined']
        read_only_fields = ['id', 'date_joined']


class TelegramAuthSerializer(serializers.Serializer):
    """
    Serializer for Telegram Mini App authentication.
    Accepts raw initData string from Telegram WebApp.
    """
    init_data = serializers.CharField()


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
    user_name = serializers.SerializerMethodField()
    store_name = serializers.CharField(source='store.name', read_only=True)

    class Meta:
        model = Order
        fields = [
            'id', 'user', 'user_name', 'store', 'store_name',
            'status', 'items', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'user', 'created_at', 'updated_at', 'user_name', 'store_name']

    def get_user_name(self, obj):
        return f"{obj.user.first_name} {obj.user.last_name}"


class OrderCreateSerializer(serializers.Serializer):
    """
    Serializer for creating orders.
    Accepts store_id and list of items.
    """
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
        user = validated_data['user']  # Injected in view
        store = validated_data['store']
        items_data = validated_data.pop('items')

        # Create order
        order = Order.objects.create(
            user=user,
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
                price_at_order=product.price  # Snapshot current price
            )

        return order


class SellerSerializer(serializers.ModelSerializer):
    """
    Seller profile serializer.
    """
    user = UserSerializer(read_only=True)
    store = StoreSerializer(read_only=True)

    class Meta:
        model = Seller
        fields = ['id', 'user', 'store', 'is_active', 'created_at']
        read_only_fields = ['id', 'created_at']


class LocationSerializer(serializers.ModelSerializer):
    """
    Location serializer for reading location details.
    """
    user_name = serializers.SerializerMethodField()
    store_name = serializers.CharField(source='store.name', read_only=True, allow_null=True)

    class Meta:
        model = Location
        fields = [
            'id', 'name', 'latitude', 'longitude', 'address',
            'user', 'user_name', 'store', 'store_name',
            'is_default', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'user_name', 'store_name']

    def get_user_name(self, obj):
        if obj.user:
            return f"{obj.user.first_name} {obj.user.last_name}"
        return None


class LocationCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating/updating locations.
    User or store is auto-assigned based on context.
    """
    class Meta:
        model = Location
        fields = ['id', 'name', 'latitude', 'longitude', 'address', 'is_default']
        read_only_fields = ['id']
