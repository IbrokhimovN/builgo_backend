"""
Django admin configuration for BuildGo Backend.
"""

from django.contrib import admin
from .models import User, Store, Seller, Category, Product, Order, OrderItem, Location


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ['telegram_id', 'first_name', 'last_name', 'phone', 'role', 'created_at']
    list_filter = ['role', 'created_at']
    search_fields = ['telegram_id', 'first_name', 'last_name', 'phone']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Seller)
class SellerAdmin(admin.ModelAdmin):
    list_display = ['user', 'store', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['user__first_name', 'user__last_name', 'store__name']
    readonly_fields = ['created_at']
    raw_id_fields = ['user', 'store']


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'store', 'created_at']
    list_filter = ['created_at']
    search_fields = ['name', 'store__name']
    readonly_fields = ['created_at']
    raw_id_fields = ['store']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'store', 'category', 'price', 'unit', 'is_available', 'created_at']
    list_filter = ['is_available', 'unit', 'created_at']
    search_fields = ['name', 'store__name']
    readonly_fields = ['created_at', 'updated_at']
    raw_id_fields = ['store', 'category']


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ['product', 'quantity', 'price_at_order']
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'store', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['user__first_name', 'user__last_name', 'store__name']
    readonly_fields = ['created_at', 'updated_at']
    raw_id_fields = ['user', 'store']
    inlines = [OrderItemInline]


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ['order', 'product', 'quantity', 'price_at_order']
    search_fields = ['order__id', 'product__name']
    raw_id_fields = ['order', 'product']
    readonly_fields = ['price_at_order']


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'store', 'address', 'is_default', 'created_at']
    list_filter = ['is_default', 'created_at']
    search_fields = ['name', 'address', 'user__first_name', 'user__last_name', 'store__name']
    readonly_fields = ['created_at', 'updated_at']
    raw_id_fields = ['user', 'store']
