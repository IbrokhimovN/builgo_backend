"""
Django admin configuration for BuildGo Backend.
Uses custom UserAdmin for AbstractUser-based User model.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, Store, Seller, Category, Product, Order, OrderItem, Location


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """
    Custom admin for User model (extends AbstractUser).
    Role is editable in admin — this is how buyers get promoted to sellers.
    """
    list_display = ['telegram_id', 'first_name', 'last_name', 'phone', 'role', 'is_active', 'date_joined']
    list_filter = ['role', 'is_active', 'date_joined']
    search_fields = ['telegram_id', 'first_name', 'last_name', 'phone']
    ordering = ['-date_joined']

    # Override fieldsets to show our custom fields
    fieldsets = (
        (None, {'fields': ('telegram_id',)}),
        ('Personal Info', {'fields': ('first_name', 'last_name', 'phone')}),
        ('Role', {'fields': ('role',)}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('telegram_id', 'first_name', 'last_name', 'role', 'password1', 'password2'),
        }),
    )


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
