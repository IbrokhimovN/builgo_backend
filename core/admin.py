"""
Django admin configuration for BuildGo Backend.
Hardened against destructive operations.
"""

import logging
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.db.models import ProtectedError
from .models import (
    User, Customer, Store, Seller, Category, Product, Order, OrderItem, Location,
    ProductImage, ProductAttribute, ProductAttributeValue, ProductVariant, CartItem,
    StoreDocument
)

logger = logging.getLogger(__name__)


# ============================================
# Custom User Admin
# ============================================

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Admin for the custom User model (phone_number as USERNAME_FIELD)."""
    list_display = ['phone_number', 'telegram_id', 'is_active', 'is_staff', 'date_joined']
    list_filter = ['is_active', 'is_staff', 'date_joined']
    search_fields = ['phone_number', 'telegram_id']
    ordering = ['-date_joined']

    fieldsets = (
        (None, {'fields': ('phone_number', 'password')}),
        ('Telegram', {'fields': ('telegram_id',)}),
        ('Personal', {'fields': ('first_name', 'last_name')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Dates', {'fields': ('last_login', 'date_joined')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('phone_number', 'telegram_id', 'password1', 'password2'),
        }),
    )



@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ['telegram_id', 'first_name', 'last_name', 'phone', 'created_at']
    list_filter = ['created_at']
    search_fields = ['telegram_id', 'first_name', 'last_name', 'phone']
    ordering = ['-created_at']
    readonly_fields = ['created_at']


class StoreDocumentInline(admin.TabularInline):
    model = StoreDocument
    extra = 0
    readonly_fields = ['document_type', 'file', 'uploaded_at']


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    """
    Store deletion is PROTECTED by FK constraints.
    If store has sellers, products, or orders, delete will raise ProtectedError.
    Admin must deactivate stores instead of deleting.
    """
    list_display = ['name', 'status', 'is_active', 'seller_count', 'product_count', 'order_count', 'created_at']
    list_filter = ['is_active', 'status', 'created_at']
    search_fields = ['name', 'legal_name', 'inn']
    readonly_fields = ['created_at', 'updated_at']
    inlines = [StoreDocumentInline]
    actions = ['deactivate_stores', 'activate_stores', 'approve_stores', 'reject_stores']

    def seller_count(self, obj):
        return obj.sellers.count()
    seller_count.short_description = 'Sellers'

    def product_count(self, obj):
        return obj.products.count()
    product_count.short_description = 'Products'

    def order_count(self, obj):
        return obj.orders.count()
    order_count.short_description = 'Orders'

    def delete_model(self, request, obj):
        """Warn admin before deletion attempt."""
        try:
            obj.delete()
            logger.info("Store '%s' (id=%d) deleted by admin %s", obj.name, obj.id, request.user)
        except ProtectedError:
            self.message_user(
                request,
                f"Cannot delete store '{obj.name}' — it has sellers, products, or orders. "
                f"Deactivate instead.",
                level='ERROR'
            )

    def delete_queryset(self, request, queryset):
        """Prevent bulk deletion of stores with dependencies."""
        for obj in queryset:
            self.delete_model(request, obj)

    @admin.action(description="Deactivate selected stores")
    def deactivate_stores(self, request, queryset):
        count = queryset.update(is_active=False)
        self.message_user(request, f"{count} store(s) deactivated.")

    @admin.action(description="Activate selected stores")
    def activate_stores(self, request, queryset):
        count = queryset.update(is_active=True)
        self.message_user(request, f"{count} store(s) activated.")

    @admin.action(description="Approve selected stores")
    def approve_stores(self, request, queryset):
        count = queryset.update(status='approved')
        self.message_user(request, f"{count} store(s) approved.")

    @admin.action(description="Reject selected stores")
    def reject_stores(self, request, queryset):
        count = queryset.update(status='rejected')
        self.message_user(request, f"{count} store(s) rejected.")


@admin.register(StoreDocument)
class StoreDocumentAdmin(admin.ModelAdmin):
    list_display = ['store', 'document_type', 'uploaded_at']
    list_filter = ['document_type', 'uploaded_at']
    search_fields = ['store__name']
    readonly_fields = ['uploaded_at']

@admin.register(Seller)
class SellerAdmin(admin.ModelAdmin):
    """
    Seller is created ONLY from Django Admin.
    Admin enters telegram_id + name + store.
    """
    list_display = ['telegram_id', 'name', 'store', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['telegram_id', 'name', 'store__name']
    readonly_fields = ['created_at']
    raw_id_fields = ['store']
    actions = ['deactivate_sellers', 'activate_sellers']

    def save_model(self, request, obj, form, change):
        """Log seller creation and deactivation."""
        action = 'updated' if change else 'created'
        super().save_model(request, obj, form, change)
        logger.info(
            "Seller %s: telegram_id=%s, store='%s', is_active=%s by admin %s",
            action, obj.telegram_id, obj.store.name, obj.is_active, request.user
        )

        # Warn if deactivating an active seller
        if change and 'is_active' in form.changed_data and not obj.is_active:
            self.message_user(
                request,
                f"⚠️ Seller '{obj.name}' (telegram_id={obj.telegram_id}) has been DEACTIVATED. "
                f"They will lose access immediately on next API call.",
                level='WARNING'
            )

    @admin.action(description="Deactivate selected sellers")
    def deactivate_sellers(self, request, queryset):
        count = queryset.update(is_active=False)
        self.message_user(
            request,
            f"⚠️ {count} seller(s) deactivated. They will lose access immediately.",
            level='WARNING'
        )

    @admin.action(description="Activate selected sellers")
    def activate_sellers(self, request, queryset):
        count = queryset.update(is_active=True)
        self.message_user(request, f"{count} seller(s) activated.")


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'store', 'created_at']
    list_filter = ['created_at']
    search_fields = ['name', 'store__name']
    readonly_fields = ['created_at']
    raw_id_fields = ['store']


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1
    filter_horizontal = ('attribute_values',)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    """
    Product deletion is PROTECTED if product has order items.
    Admin should deactivate products instead of deleting.
    """
    list_display = ['name', 'store', 'category', 'price', 'unit', 'is_available', 'created_at']
    list_filter = ['is_available', 'unit', 'created_at']
    search_fields = ['name', 'store__name']
    readonly_fields = ['created_at', 'updated_at']
    raw_id_fields = ['store', 'category']
    inlines = [ProductImageInline, ProductVariantInline]
    actions = ['deactivate_products', 'activate_products']

    def delete_model(self, request, obj):
        try:
            obj.delete()
        except ProtectedError:
            self.message_user(
                request,
                f"Cannot delete product '{obj.name}' — it has order history. "
                f"Mark as unavailable instead.",
                level='ERROR'
            )

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            self.delete_model(request, obj)

    @admin.action(description="Mark selected products as unavailable")
    def deactivate_products(self, request, queryset):
        count = queryset.update(is_available=False)
        self.message_user(request, f"{count} product(s) marked as unavailable.")

    @admin.action(description="Mark selected products as available")
    def activate_products(self, request, queryset):
        count = queryset.update(is_available=True)
        self.message_user(request, f"{count} product(s) marked as available.")


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ['product', 'quantity', 'price_at_order']
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'customer', 'store', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['customer__first_name', 'customer__last_name', 'customer__telegram_id', 'store__name']
    readonly_fields = ['created_at', 'updated_at']
    raw_id_fields = ['customer', 'store']
    inlines = [OrderItemInline]


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ['order', 'product', 'quantity', 'price_at_order']
    search_fields = ['order__id', 'product__name']
    raw_id_fields = ['order', 'product']
    readonly_fields = ['price_at_order']


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ['name', 'customer', 'store', 'address', 'is_default', 'created_at']
    list_filter = ['is_default', 'created_at']
    search_fields = ['name', 'address', 'customer__first_name', 'customer__last_name', 'store__name']
    readonly_fields = ['created_at', 'updated_at']
    raw_id_fields = ['customer', 'store']

@admin.register(ProductAttribute)
class ProductAttributeAdmin(admin.ModelAdmin):
    list_display = ['name']
    search_fields = ['name']

@admin.register(ProductAttributeValue)
class ProductAttributeValueAdmin(admin.ModelAdmin):
    list_display = ['attribute', 'value']
    list_filter = ['attribute']
    search_fields = ['value']

@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ['customer', 'product', 'variant', 'quantity', 'created_at']
    list_filter = ['created_at']
    search_fields = ['customer__first_name', 'product__name']
    raw_id_fields = ['customer', 'product', 'variant']

