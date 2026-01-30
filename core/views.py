"""
API Views for BuildGo Backend.
"""

from rest_framework import generics, status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Q

from .models import User, Store, Seller, Category, Product, Order
from .serializers import (
    TelegramAuthSerializer, UserSerializer, StoreSerializer,
    CategorySerializer, ProductSerializer, ProductCreateSerializer,
    OrderSerializer, OrderCreateSerializer, SellerSerializer
)
from .permissions import IsSeller, IsStoreOwner


# ============================================
# AUTHENTICATION ENDPOINTS
# ============================================

class TelegramAuthView(APIView):
    """
    POST /api/telegram-auth/
    Create or update buyer user from Telegram bot.
    """
    
    def post(self, request):
        serializer = TelegramAuthSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response(
                UserSerializer(user).data,
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
def check_seller(request):
    """
    GET /api/check-seller/?telegram_id=XXX
    Check if telegram_id belongs to an active seller.
    """
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


@api_view(['GET'])
def seller_me(request):
    """
    GET /api/seller/me/
    Get current seller details from telegram_id in header.
    """
    telegram_id = getattr(request, 'telegram_user_id', None)
    if not telegram_id:
        return Response(
            {'error': 'Telegram authentication required'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        seller = Seller.objects.get(
            user__telegram_id=telegram_id,
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
    List all active stores.
    """
    queryset = Store.objects.filter(is_active=True)
    serializer_class = StoreSerializer


class StoreCategoriesView(generics.ListAPIView):
    """
    GET /api/stores/{id}/categories/
    List categories for a specific store.
    """
    serializer_class = CategorySerializer
    
    def get_queryset(self):
        store_id = self.kwargs['store_id']
        return Category.objects.filter(store_id=store_id)


class StoreProductsView(generics.ListAPIView):
    """
    GET /api/stores/{id}/products/
    GET /api/stores/{id}/products/?category=X
    List products for a specific store, optionally filtered by category.
    """
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
    Create a new order (buyer only).
    """
    
    def post(self, request):
        telegram_id = getattr(request, 'telegram_user_id', None)
        if not telegram_id:
            return Response(
                {'error': 'Telegram authentication required'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        # Get or create buyer user
        try:
            user = User.objects.get(telegram_id=telegram_id)
        except User.DoesNotExist:
            return Response(
                {'error': 'User not found. Please register via Telegram bot first.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = OrderCreateSerializer(data=request.data)
        if serializer.is_valid():
            # Inject user into validated data
            serializer.validated_data['user'] = user
            order = serializer.save()
            return Response(
                OrderSerializer(order).data,
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
def search_products(request):
    """
    GET /api/search/?q=cement
    Search products across all stores.
    """
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
    List orders for seller's store only.
    """
    serializer_class = OrderSerializer
    permission_classes = [IsSeller]
    
    def get_queryset(self):
        telegram_id = getattr(self.request, 'telegram_user_id', None)
        seller = Seller.objects.get(user__telegram_id=telegram_id)
        return Order.objects.filter(store=seller.store)


class SellerOrderUpdateView(APIView):
    """
    PATCH /api/seller/orders/{id}/
    Update order status (seller only).
    """
    permission_classes = [IsSeller, IsStoreOwner]
    
    def patch(self, request, pk):
        telegram_id = getattr(request, 'telegram_user_id', None)
        seller = Seller.objects.get(user__telegram_id=telegram_id)
        
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
    """
    permission_classes = [IsSeller]
    
    def post(self, request):
        telegram_id = getattr(request, 'telegram_user_id', None)
        seller = Seller.objects.get(user__telegram_id=telegram_id)
        
        serializer = ProductCreateSerializer(data=request.data)
        if serializer.is_valid():
            # Auto-assign store from seller
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
    """
    permission_classes = [IsSeller]
    
    def patch(self, request, pk):
        telegram_id = getattr(request, 'telegram_user_id', None)
        seller = Seller.objects.get(user__telegram_id=telegram_id)
        
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
