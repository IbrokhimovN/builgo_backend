"""
Custom permissions for BuildGo Backend.
All permissions assume telegram_id is available via middleware.
"""

from rest_framework import permissions
from .models import Seller


class IsSeller(permissions.BasePermission):
    """
    Permission to check if user is an active seller.
    Requires telegram_id from middleware.
    """
    
    def has_permission(self, request, view):
        # Check if telegram_id is present
        telegram_id = getattr(request, 'telegram_user_id', None)
        if not telegram_id:
            return False
        
        # Check if user is an active seller
        return Seller.objects.filter(
            user__telegram_id=telegram_id,
            is_active=True
        ).exists()


class IsStoreOwner(permissions.BasePermission):
    """
    Permission to check if seller owns the store related to the object.
    Used for product/order updates.
    """
    
    def has_object_permission(self, request, view, obj):
        telegram_id = getattr(request, 'telegram_user_id', None)
        if not telegram_id:
            return False
        
        try:
            seller = Seller.objects.get(
                user__telegram_id=telegram_id,
                is_active=True
            )
            
            # Check if object's store matches seller's store
            if hasattr(obj, 'store'):
                return obj.store == seller.store
            
            return False
        except Seller.DoesNotExist:
            return False
