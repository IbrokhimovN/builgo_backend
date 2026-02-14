"""
Custom permissions for BuildGo Backend.
All permissions use JWT-authenticated request.user.
"""

from rest_framework import permissions
from .models import Seller


class IsSeller(permissions.BasePermission):
    """
    Permission to check if the authenticated user has role='seller'.
    Requires JWT authentication.
    """
    message = 'Only sellers can access this endpoint.'

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.role == 'seller'


class IsStoreOwner(permissions.BasePermission):
    """
    Permission to check if seller owns the store related to the object.
    Used for product/order updates.
    """

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False

        try:
            seller = Seller.objects.get(
                user=request.user,
                is_active=True
            )

            # Check if object's store matches seller's store
            if hasattr(obj, 'store'):
                return obj.store == seller.store

            return False
        except Seller.DoesNotExist:
            return False
