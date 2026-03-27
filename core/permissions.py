"""
Custom DRF Permission Classes for BuildGo RBAC.

Three roles enforced at the view level:
- IsBuyer:            Authenticated user with a linked Customer profile.
- IsSeller:           Authenticated user with a linked Store profile AND status == 'approved'.
- IsUnverifiedSeller: Authenticated user with a linked Store profile AND status in ('pending', 'rejected').

Usage in views:
    from .permissions import IsBuyer, IsSeller, IsUnverifiedSeller

    class MyView(APIView):
        permission_classes = [IsSeller]
"""

from rest_framework.permissions import BasePermission


class IsBuyer(BasePermission):
    """
    Allow access only to authenticated users who have a linked Customer profile.
    Works with both JWT-authenticated Users and Telegram-authenticated requests
    where a Customer record exists for the telegram_id.
    """
    message = "Faqat xaridorlar uchun ruxsat berilgan."  # "Only buyers are allowed."

    def has_permission(self, request, view):
        # JWT-authenticated: request.user is a User instance
        if hasattr(request, 'user') and request.user and request.user.is_authenticated:
            # Check for linked Customer via OneToOneField
            if hasattr(request.user, 'customer') and request.user.customer is not None:
                return True

        # Telegram-authenticated: check if a Customer record exists for this telegram_id
        telegram_id = getattr(request, 'telegram_id', None)
        if telegram_id:
            from .models import Customer
            return Customer.objects.filter(telegram_id=telegram_id).exists()

        return False


class IsSeller(BasePermission):
    """
    Allow access only to authenticated users who:
    1. Have a linked Store profile (via User.store OneToOneField), AND
    2. The store's verification status is EXACTLY 'approved'.

    This blocks unverified/pending/rejected sellers from performing
    privileged actions like creating products.
    """
    message = "Faqat tasdiqlangan sotuvchilar uchun ruxsat berilgan."  # "Only approved sellers are allowed."

    def has_permission(self, request, view):
        # JWT-authenticated
        if hasattr(request, 'user') and request.user and request.user.is_authenticated:
            if hasattr(request.user, 'store') and request.user.store is not None:
                return request.user.store.status == 'approved'

        # Telegram-authenticated: resolve via Seller -> Store
        telegram_id = getattr(request, 'telegram_id', None)
        if telegram_id:
            from .models import Seller
            try:
                seller = Seller.objects.select_related('store').get(
                    telegram_id=telegram_id,
                    is_active=True,
                )
                return seller.store.status == 'approved'
            except Seller.DoesNotExist:
                return False

        return False


class IsUnverifiedSeller(BasePermission):
    """
    Allow access only to authenticated users who have a Store profile
    with status 'pending' or 'rejected'.

    Use this for endpoints that unverified sellers need access to,
    such as the store verification/document upload endpoint.
    """
    message = "Bu endpoint faqat tasdiqlanmagan sotuvchilar uchun."  # "Only for unverified sellers."

    def has_permission(self, request, view):
        # JWT-authenticated
        if hasattr(request, 'user') and request.user and request.user.is_authenticated:
            if hasattr(request.user, 'store') and request.user.store is not None:
                return request.user.store.status in ('pending', 'rejected')

        # Telegram-authenticated
        telegram_id = getattr(request, 'telegram_id', None)
        if telegram_id:
            from .models import Seller
            try:
                seller = Seller.objects.select_related('store').get(
                    telegram_id=telegram_id,
                    is_active=True,
                )
                return seller.store.status in ('pending', 'rejected')
            except Seller.DoesNotExist:
                return False

        return False
