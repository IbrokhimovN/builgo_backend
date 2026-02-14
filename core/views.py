"""
API Views for BuildGo Backend.
All protected endpoints use JWT authentication via SimpleJWT.
"""

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl, unquote

from django.conf import settings
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from django.db.models import Q

from .models import User, Store, Seller, Category, Product, Order, Location
from .serializers import (
    TelegramAuthSerializer, UserSerializer, StoreSerializer,
    CategorySerializer, ProductSerializer, ProductCreateSerializer,
    OrderSerializer, OrderCreateSerializer, SellerSerializer,
    LocationSerializer, LocationCreateSerializer
)
from .permissions import IsSeller, IsStoreOwner


# ============================================
# TELEGRAM initData VERIFICATION
# ============================================

def verify_telegram_init_data(init_data: str, bot_token: str) -> dict | None:
    """
    Verify Telegram Mini App initData using HMAC-SHA256.
    Returns parsed user data if valid, None if invalid.

    See: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """
    try:
        # Parse init_data into key-value pairs
        parsed = dict(parse_qsl(init_data, keep_blank_values=True))

        # Extract the hash
        received_hash = parsed.pop('hash', None)
        if not received_hash:
            return None

        # Build the data-check-string:
        # Sort remaining key=value pairs alphabetically by key, join with \n
        data_check_string = '\n'.join(
            f'{key}={value}' for key, value in sorted(parsed.items())
        )

        # Create the secret key: HMAC-SHA256 of bot_token with "WebAppData" as key
        secret_key = hmac.new(
            b'WebAppData',
            bot_token.encode('utf-8'),
            hashlib.sha256
        ).digest()

        # Calculate the hash
        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        # Compare hashes
        if not hmac.compare_digest(calculated_hash, received_hash):
            return None

        # Verify auth_date is not too old (allow 24 hours)
        auth_date = parsed.get('auth_date')
        if auth_date:
            auth_timestamp = int(auth_date)
            current_timestamp = int(time.time())
            if current_timestamp - auth_timestamp > 86400:  # 24 hours
                return None

        # Parse user JSON
        user_data_str = parsed.get('user')
        if not user_data_str:
            return None

        user_data = json.loads(unquote(user_data_str))
        return user_data

    except (ValueError, KeyError, json.JSONDecodeError):
        return None


# ============================================
# AUTHENTICATION ENDPOINTS
# ============================================

class TelegramAuthView(APIView):
    """
    POST /api/telegram-auth/

    Authenticate user via Telegram Mini App initData.
    1. Verifies initData HMAC signature using BOT_TOKEN
    2. Creates user if not exists (role=buyer)
    3. Preserves existing role (seller) if already set by admin
    4. Returns JWT access + refresh tokens and user profile

    Request:  { "init_data": "<Telegram initData string>" }
    Response: { "access": "...", "refresh": "...", "user": {...} }
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = TelegramAuthSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        init_data = serializer.validated_data['init_data']

        # Verify initData with Telegram HMAC
        bot_token = settings.TELEGRAM_BOT_TOKEN
        if not bot_token:
            return Response(
                {'error': 'Server configuration error: BOT_TOKEN not set'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        user_data = verify_telegram_init_data(init_data, bot_token)
        if user_data is None:
            return Response(
                {'error': 'Invalid or expired Telegram initData'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        telegram_id = user_data.get('id')
        if not telegram_id:
            return Response(
                {'error': 'Telegram user ID not found in initData'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get or create user — preserve existing role if user was promoted
        try:
            user = User.objects.get(telegram_id=telegram_id)
            # Update name from Telegram (may change), but NEVER overwrite role
            user.first_name = user_data.get('first_name', user.first_name)
            user.last_name = user_data.get('last_name', '') or user.last_name
            user.save(update_fields=['first_name', 'last_name'])
        except User.DoesNotExist:
            user = User.objects.create(
                telegram_id=telegram_id,
                first_name=user_data.get('first_name', ''),
                last_name=user_data.get('last_name', ''),
                role='buyer',
            )

        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)

        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserSerializer(user).data,
        }, status=status.HTTP_200_OK)


class MeView(APIView):
    """
    GET /api/me/
    Returns the authenticated user's profile.
    Requires JWT Bearer token.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


class SellerDashboardView(APIView):
    """
    GET /api/seller/dashboard/
    Seller-only endpoint. Returns seller profile and store info.
    Requires JWT + role=seller.
    """
    permission_classes = [IsAuthenticated, IsSeller]

    def get(self, request):
        try:
            seller = Seller.objects.select_related('store').get(
                user=request.user,
                is_active=True
            )
            return Response({
                'seller': SellerSerializer(seller).data,
                'message': 'Seller dashboard data',
            })
        except Seller.DoesNotExist:
            return Response(
                {'error': 'Seller profile not found. Contact admin.'},
                status=status.HTTP_404_NOT_FOUND
            )


# ============================================
# LEGACY-COMPATIBLE ENDPOINTS
# ============================================

class CheckSellerView(APIView):
    """
    GET /api/check-seller/?telegram_id=XXX
    Check if telegram_id belongs to an active seller.
    Public endpoint (no auth required).
    """
    permission_classes = [AllowAny]

    def get(self, request):
        telegram_id = request.GET.get('telegram_id')
        if not telegram_id:
            return Response(
                {'error': 'telegram_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            seller = Seller.objects.get(
                user__telegram_id=telegram_id,
                is_active=True
            )
            return Response({
                'is_seller': True,
                'seller': SellerSerializer(seller).data
            })
        except Seller.DoesNotExist:
            return Response({
                'is_seller': False
            })


class SellerMeView(APIView):
    """
    GET /api/seller/me/
    Get current seller details. Requires JWT + seller role.
    """
    permission_classes = [IsAuthenticated, IsSeller]

    def get(self, request):
        try:
            seller = Seller.objects.get(
                user=request.user,
                is_active=True
            )
            return Response(SellerSerializer(seller).data)
        except Seller.DoesNotExist:
            return Response(
                {'error': 'Not a seller'},
                status=status.HTTP_403_FORBIDDEN
            )


# ============================================
# BUYER ENDPOINTS
# ============================================

class StoreListView(generics.ListAPIView):
    """
    GET /api/stores/
    List all active stores. Public endpoint.
    """
    permission_classes = [AllowAny]
    queryset = Store.objects.filter(is_active=True)
    serializer_class = StoreSerializer


class StoreCategoriesView(generics.ListAPIView):
    """
    GET /api/stores/{id}/categories/
    List categories for a specific store. Public endpoint.
    """
    permission_classes = [AllowAny]
    serializer_class = CategorySerializer

    def get_queryset(self):
        store_id = self.kwargs['store_id']
        return Category.objects.filter(store_id=store_id)


class StoreProductsView(generics.ListAPIView):
    """
    GET /api/stores/{id}/products/
    GET /api/stores/{id}/products/?category=X
    List products for a specific store, optionally filtered by category.
    Public endpoint.
    """
    permission_classes = [AllowAny]
    serializer_class = ProductSerializer

    def get_queryset(self):
        store_id = self.kwargs['store_id']
        queryset = Product.objects.filter(
            store_id=store_id,
            is_available=True
        )

        # Filter by category if provided
        category_id = self.request.GET.get('category')
        if category_id:
            queryset = queryset.filter(category_id=category_id)

        return queryset


class OrderCreateView(APIView):
    """
    POST /api/orders/
    Create a new order. Requires JWT authentication.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = OrderCreateSerializer(data=request.data)
        if serializer.is_valid():
            serializer.validated_data['user'] = request.user
            order = serializer.save()
            return Response(
                OrderSerializer(order).data,
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SearchProductsView(APIView):
    """
    GET /api/search/?q=cement
    Search products across all stores. Public endpoint.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        query = request.GET.get('q', '').strip()
        if not query:
            return Response({'results': []})

        products = Product.objects.filter(
            Q(name__icontains=query),
            is_available=True,
            store__is_active=True
        )[:50]  # Limit to 50 results

        return Response({
            'results': ProductSerializer(products, many=True).data
        })


# ============================================
# SELLER ENDPOINTS
# ============================================

class SellerOrdersView(generics.ListAPIView):
    """
    GET /api/seller/orders/
    List orders for seller's store only. Requires JWT + seller role.
    """
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated, IsSeller]

    def get_queryset(self):
        seller = Seller.objects.get(user=self.request.user)
        return Order.objects.filter(store=seller.store)


class SellerOrderUpdateView(APIView):
    """
    PATCH /api/seller/orders/{id}/
    Update order status (seller only). Requires JWT + seller role.
    """
    permission_classes = [IsAuthenticated, IsSeller]

    def patch(self, request, pk):
        seller = Seller.objects.get(user=request.user)

        try:
            order = Order.objects.get(pk=pk, store=seller.store)
        except Order.DoesNotExist:
            return Response(
                {'error': 'Order not found or access denied'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Update status
        new_status = request.data.get('status')
        if new_status not in ['new', 'done']:
            return Response(
                {'error': 'Invalid status. Must be "new" or "done"'},
                status=status.HTTP_400_BAD_REQUEST
            )

        order.status = new_status
        order.save()

        return Response(OrderSerializer(order).data)


class SellerProductCreateView(APIView):
    """
    POST /api/seller/products/
    Create product (seller only). Store is auto-assigned.
    Requires JWT + seller role.
    """
    permission_classes = [IsAuthenticated, IsSeller]

    def post(self, request):
        seller = Seller.objects.get(user=request.user)

        serializer = ProductCreateSerializer(data=request.data)
        if serializer.is_valid():
            product = serializer.save(store=seller.store)
            return Response(
                ProductSerializer(product).data,
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SellerProductUpdateView(APIView):
    """
    PATCH /api/seller/products/{id}/
    Update product (seller only, only their own products).
    Requires JWT + seller role.
    """
    permission_classes = [IsAuthenticated, IsSeller]

    def patch(self, request, pk):
        seller = Seller.objects.get(user=request.user)

        try:
            product = Product.objects.get(pk=pk, store=seller.store)
        except Product.DoesNotExist:
            return Response(
                {'error': 'Product not found or access denied'},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = ProductCreateSerializer(product, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(ProductSerializer(product).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ============================================
# CUSTOMER LOCATION ENDPOINTS
# ============================================

class CustomerLocationListCreateView(APIView):
    """
    GET /api/locations/
    POST /api/locations/
    List and create customer locations. Requires JWT.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        locations = Location.objects.filter(user=request.user)
        return Response(LocationSerializer(locations, many=True).data)

    def post(self, request):
        serializer = LocationCreateSerializer(data=request.data)
        if serializer.is_valid():
            location = serializer.save(user=request.user)
            return Response(
                LocationSerializer(location).data,
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CustomerLocationDetailView(APIView):
    """
    PATCH /api/locations/{id}/
    DELETE /api/locations/{id}/
    Update or delete a customer location. Requires JWT.
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        try:
            location = Location.objects.get(pk=pk, user=request.user)
        except Location.DoesNotExist:
            return Response(
                {'error': 'Location not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = LocationCreateSerializer(location, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(LocationSerializer(location).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        try:
            location = Location.objects.get(pk=pk, user=request.user)
        except Location.DoesNotExist:
            return Response(
                {'error': 'Location not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        location.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ============================================
# SELLER LOCATION ENDPOINTS
# ============================================

class SellerLocationListCreateView(APIView):
    """
    GET /api/seller/locations/
    POST /api/seller/locations/
    List and create seller store locations. Requires JWT + seller role.
    """
    permission_classes = [IsAuthenticated, IsSeller]

    def get(self, request):
        seller = Seller.objects.get(user=request.user)
        locations = Location.objects.filter(store=seller.store)
        return Response(LocationSerializer(locations, many=True).data)

    def post(self, request):
        seller = Seller.objects.get(user=request.user)

        serializer = LocationCreateSerializer(data=request.data)
        if serializer.is_valid():
            location = serializer.save(store=seller.store)
            return Response(
                LocationSerializer(location).data,
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SellerLocationDetailView(APIView):
    """
    PATCH /api/seller/locations/{id}/
    DELETE /api/seller/locations/{id}/
    Update or delete a seller store location. Requires JWT + seller role.
    """
    permission_classes = [IsAuthenticated, IsSeller]

    def patch(self, request, pk):
        seller = Seller.objects.get(user=request.user)

        try:
            location = Location.objects.get(pk=pk, store=seller.store)
        except Location.DoesNotExist:
            return Response(
                {'error': 'Location not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = LocationCreateSerializer(location, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(LocationSerializer(location).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        seller = Seller.objects.get(user=request.user)

        try:
            location = Location.objects.get(pk=pk, store=seller.store)
        except Location.DoesNotExist:
            return Response(
                {'error': 'Location not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        location.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
