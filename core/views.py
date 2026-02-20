"""
API Views for BuildGo Backend.

Authentication:
- Mini App requests: TelegramInitDataAuthentication (HMAC-SHA256)
- Bot requests: BotSecretAuthentication (shared secret header)
- Public endpoints: stores, categories, products, search (no auth required)

Role logic is UNCHANGED. telegram_id resolution stays per-request.
"""

import logging
from django.db import IntegrityError
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Q

from .authentication import (
    TelegramInitDataAuthentication,
    BotSecretAuthentication,
    get_telegram_id,
)
from .models import Customer, Store, Seller, Category, Product, Order, Location
from .serializers import (
    CustomerSerializer, StoreSerializer,
    CategorySerializer, ProductSerializer, ProductCreateSerializer,
    OrderSerializer, OrderCreateSerializer, SellerSerializer,
    LocationSerializer, LocationCreateSerializer
)

logger = logging.getLogger(__name__)

# Valid order statuses for seller updates
VALID_ORDER_STATUSES = {'new', 'processing', 'done', 'cancelled'}


# ============================================
# PUBLIC ENDPOINTS (no auth required)
# ============================================

class StoreListView(generics.ListAPIView):
    """
    GET /api/stores/
    List all active stores. Public.
    """
    authentication_classes = []
    permission_classes = [AllowAny]
    queryset = Store.objects.filter(is_active=True)
    serializer_class = StoreSerializer


class StoreCategoriesView(generics.ListAPIView):
    """
    GET /api/stores/{id}/categories/
    List categories for a specific store. Public.
    """
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = CategorySerializer

    def get_queryset(self):
        store_id = self.kwargs['store_id']
        return Category.objects.filter(store_id=store_id)


class StoreProductsView(generics.ListAPIView):
    """
    GET /api/stores/{id}/products/
    GET /api/stores/{id}/products/?category=X
    List products for a specific store. Public.
    """
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = ProductSerializer

    def get_queryset(self):
        store_id = self.kwargs['store_id']
        queryset = Product.objects.filter(
            store_id=store_id,
            is_available=True
        )
        category_id = self.request.GET.get('category')
        if category_id:
            queryset = queryset.filter(category_id=category_id)
        return queryset


class SearchProductsView(generics.ListAPIView):
    """
    GET /api/search/?q=cement
    Search products across all stores. Public.
    Paginated via DRF default pagination.
    """
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = ProductSerializer

    def get_queryset(self):
        query = self.request.GET.get('q', '').strip()
        if not query:
            return Product.objects.none()
        return Product.objects.filter(
            Q(name__icontains=query),
            is_available=True,
            store__is_active=True
        )


# ============================================
# CUSTOMER ENDPOINTS (bot-authenticated)
# ============================================

class CustomerCreateView(APIView):
    """
    POST /api/customers/
    Create or update a Customer by telegram_id.
    Called by bot after registration. Authenticated via BotSecret.
    Race-condition safe with IntegrityError handling.
    """
    authentication_classes = [BotSecretAuthentication]

    def post(self, request):
        telegram_id = get_telegram_id(request)
        if not telegram_id:
            # Fallback: also accept from body for bot calls
            telegram_id = request.data.get('telegram_id')
            if not telegram_id:
                return Response(
                    {'error': 'telegram_id is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            try:
                telegram_id = int(telegram_id)
            except (ValueError, TypeError):
                return Response(
                    {'error': 'Invalid telegram_id'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Guard: don't register sellers as customers
        if Seller.objects.filter(telegram_id=telegram_id, is_active=True).exists():
            logger.warning(
                "Seller telegram_id=%s attempted customer registration", telegram_id
            )
            return Response(
                {'error': 'This telegram_id belongs to a seller'},
                status=status.HTTP_409_CONFLICT
            )

        try:
            customer, created = Customer.objects.update_or_create(
                telegram_id=telegram_id,
                defaults={
                    'first_name': request.data.get('first_name', ''),
                    'last_name': request.data.get('last_name', ''),
                    'phone': request.data.get('phone', ''),
                }
            )
        except IntegrityError:
            # Race condition: concurrent create — retry get
            customer = Customer.objects.get(telegram_id=telegram_id)
            created = False

        logger.info(
            "Customer %s: telegram_id=%s",
            "created" if created else "updated", telegram_id
        )

        return Response(
            CustomerSerializer(customer).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )


class CustomerCheckView(APIView):
    """
    GET /api/customers/check/?telegram_id=XXX
    Check if customer exists. Used by bot for returning-customer flow.
    Authenticated via BotSecret.
    """
    authentication_classes = [BotSecretAuthentication]

    def get(self, request):
        telegram_id = get_telegram_id(request)
        if not telegram_id:
            telegram_id = request.GET.get('telegram_id')
            if not telegram_id:
                return Response(
                    {'error': 'telegram_id is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            try:
                telegram_id = int(telegram_id)
            except (ValueError, TypeError):
                return Response(
                    {'error': 'Invalid telegram_id'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        try:
            customer = Customer.objects.get(telegram_id=telegram_id)
            is_complete = bool(
                customer.first_name and 
                customer.last_name and 
                customer.phone
            )
            return Response({
                'exists': True,
                'is_complete': is_complete
            })
        except Customer.DoesNotExist:
            return Response({
                'exists': False,
                'is_complete': False
            })


# ============================================
# SELLER CHECK (bot-authenticated)
# ============================================

class CheckSellerView(APIView):
    """
    GET /api/check-seller/?telegram_id=XXX
    Check if telegram_id belongs to an active seller.
    Authenticated via BotSecret.
    """
    authentication_classes = [BotSecretAuthentication]

    def get(self, request):
        telegram_id = get_telegram_id(request)
        if not telegram_id:
            telegram_id = request.GET.get('telegram_id')
            if not telegram_id:
                return Response(
                    {'error': 'telegram_id is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            try:
                telegram_id = int(telegram_id)
            except (ValueError, TypeError):
                return Response(
                    {'error': 'Invalid telegram_id'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        try:
            seller = Seller.objects.select_related('store').get(
                telegram_id=telegram_id,
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


# ============================================
# ORDER ENDPOINTS (authenticated)
# ============================================

class OrderCreateView(APIView):
    """
    POST /api/orders/
    Create a new order. Authenticated via initData or BotSecret.
    telegram_id is extracted from auth context, NOT from request body.
    """
    authentication_classes = [TelegramInitDataAuthentication, BotSecretAuthentication]

    def post(self, request):
        telegram_id = get_telegram_id(request)
        if not telegram_id:
            # Fallback: also accept from body for bot calls
            telegram_id = request.data.get('telegram_id')
            if not telegram_id:
                return Response(
                    {'error': 'telegram_id is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            try:
                telegram_id = int(telegram_id)
            except (ValueError, TypeError):
                return Response(
                    {'error': 'Invalid telegram_id'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Inject telegram_id into serializer data from auth context
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        data['telegram_id'] = telegram_id

        serializer = OrderCreateSerializer(data=data)
        if serializer.is_valid():
            order = serializer.save()
            return Response(
                OrderSerializer(order).data,
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CustomerOrdersView(generics.ListAPIView):
    """
    GET /api/orders/my/?telegram_id=XXX
    List orders for a customer. Authenticated.
    """
    authentication_classes = [TelegramInitDataAuthentication, BotSecretAuthentication]
    serializer_class = OrderSerializer

    def get_queryset(self):
        telegram_id = get_telegram_id(self.request)
        if not telegram_id:
            return Order.objects.none()
        return Order.objects.filter(
            customer__telegram_id=telegram_id
        ).select_related('customer', 'store').prefetch_related('items__product')


# ============================================
# SELLER HELPER
# ============================================

def _get_seller(telegram_id):
    """Helper: get active Seller by telegram_id or return None."""
    if not telegram_id:
        return None
    try:
        telegram_id = int(telegram_id)
    except (ValueError, TypeError):
        return None
    try:
        return Seller.objects.select_related('store').get(
            telegram_id=telegram_id,
            is_active=True
        )
    except Seller.DoesNotExist:
        return None


# ============================================
# SELLER ENDPOINTS (authenticated via initData)
# ============================================

class SellerOrdersView(generics.ListAPIView):
    """
    GET /api/seller/orders/?telegram_id=XXX
    List orders for seller's store. Paginated.
    """
    authentication_classes = [TelegramInitDataAuthentication, BotSecretAuthentication]
    serializer_class = OrderSerializer

    def get_queryset(self):
        telegram_id = get_telegram_id(self.request)
        if not telegram_id:
            return Order.objects.none()
        seller = _get_seller(telegram_id)
        if not seller:
            return Order.objects.none()
        return Order.objects.filter(
            store=seller.store
        ).select_related('customer', 'store').prefetch_related('items__product')

    def list(self, request, *args, **kwargs):
        telegram_id = get_telegram_id(request)
        if not telegram_id:
            return Response({'error': 'telegram_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        seller = _get_seller(telegram_id)
        if not seller:
            return Response({'error': 'Not a seller'}, status=status.HTTP_403_FORBIDDEN)
        return super().list(request, *args, **kwargs)


class SellerOrderUpdateView(APIView):
    """
    PATCH /api/seller/orders/{id}/
    Update order status (seller only).
    """
    authentication_classes = [TelegramInitDataAuthentication, BotSecretAuthentication]

    def patch(self, request, pk):
        telegram_id = get_telegram_id(request)
        if not telegram_id:
            return Response({'error': 'telegram_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        seller = _get_seller(telegram_id)
        if not seller:
            return Response({'error': 'Not a seller'}, status=status.HTTP_403_FORBIDDEN)

        try:
            order = Order.objects.get(pk=pk, store=seller.store)
        except Order.DoesNotExist:
            return Response(
                {'error': 'Order not found or access denied'},
                status=status.HTTP_404_NOT_FOUND
            )

        new_status = request.data.get('status')
        if new_status not in VALID_ORDER_STATUSES:
            return Response(
                {'error': f'Invalid status. Must be one of: {", ".join(sorted(VALID_ORDER_STATUSES))}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        order.status = new_status
        order.save()

        logger.info(
            "Order #%d status changed to '%s' by seller telegram_id=%s",
            order.id, new_status, telegram_id
        )

        return Response(OrderSerializer(order).data)


class SellerProfileView(APIView):
    """
    GET /api/seller/profile/
    Returns seller + store info for the authenticated seller.
    Used by frontend during bootstrap to detect seller and get store info.
    """
    authentication_classes = [TelegramInitDataAuthentication, BotSecretAuthentication]

    def get(self, request):
        telegram_id = get_telegram_id(request)
        if not telegram_id:
            return Response({'error': 'telegram_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        seller = _get_seller(telegram_id)
        if not seller:
            return Response({'error': 'Not a seller'}, status=status.HTTP_403_FORBIDDEN)

        return Response({
            'is_seller': True,
            'seller': SellerSerializer(seller).data
        })


class SellerProductListCreateView(APIView):
    """
    GET /api/seller/products/  — List products for seller's store (paginated)
    POST /api/seller/products/ — Create product (store auto-assigned)
    """
    authentication_classes = [TelegramInitDataAuthentication, BotSecretAuthentication]

    def get(self, request):
        telegram_id = get_telegram_id(request)
        if not telegram_id:
            return Response({'error': 'telegram_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        seller = _get_seller(telegram_id)
        if not seller:
            return Response({'error': 'Not a seller'}, status=status.HTTP_403_FORBIDDEN)

        products = Product.objects.filter(store=seller.store)
        # Apply DRF pagination
        from rest_framework.pagination import PageNumberPagination
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(products, request)
        if page is not None:
            serializer = ProductSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)
        serializer = ProductSerializer(products, many=True)
        return Response(serializer.data)

    def post(self, request):
        telegram_id = get_telegram_id(request)
        if not telegram_id:
            return Response({'error': 'telegram_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        seller = _get_seller(telegram_id)
        if not seller:
            return Response({'error': 'Not a seller'}, status=status.HTTP_403_FORBIDDEN)

        serializer = ProductCreateSerializer(data=request.data)
        if serializer.is_valid():
            product = serializer.save(store=seller.store)
            logger.info(
                "Product '%s' created in store '%s' by seller telegram_id=%s",
                product.name, seller.store.name, telegram_id
            )
            return Response(
                ProductSerializer(product).data,
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SellerCategoryListCreateView(generics.ListCreateAPIView):
    """
    GET /api/seller/categories/
    POST /api/seller/categories/
    List and create categories for the seller's store.
    """
    authentication_classes = [TelegramInitDataAuthentication, BotSecretAuthentication]
    serializer_class = CategorySerializer

    def get_queryset(self):
        telegram_id = get_telegram_id(self.request)
        if not telegram_id:
            return Category.objects.none()

        seller = _get_seller(telegram_id)
        if not seller:
            return Category.objects.none()

        return Category.objects.filter(store=seller.store)

    def perform_create(self, serializer):
        telegram_id = get_telegram_id(self.request)
        seller = _get_seller(telegram_id)
        # Assuming the check happens in list() or create() before we get here
        if seller:
            category = serializer.save(store=seller.store)
            logger.info(
                "Category '%s' created in store '%s' by seller telegram_id=%s",
                category.name, seller.store.name, telegram_id
            )

    def create(self, request, *args, **kwargs):
        telegram_id = get_telegram_id(request)
        if not telegram_id:
            return Response({'error': 'telegram_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        seller = _get_seller(telegram_id)
        if not seller:
            return Response({'error': 'Not a seller'}, status=status.HTTP_403_FORBIDDEN)
        
        return super().create(request, *args, **kwargs)

    def list(self, request, *args, **kwargs):
        telegram_id = get_telegram_id(request)
        if not telegram_id:
            return Response({'error': 'telegram_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        seller = _get_seller(telegram_id)
        if not seller:
            return Response({'error': 'Not a seller'}, status=status.HTTP_403_FORBIDDEN)
            
        return super().list(request, *args, **kwargs)


class SellerProductUpdateView(APIView):
    """
    PATCH /api/seller/products/{id}/
    DELETE /api/seller/products/{id}/
    Update or delete product (seller only).
    """
    authentication_classes = [TelegramInitDataAuthentication, BotSecretAuthentication]

    def patch(self, request, pk):
        telegram_id = get_telegram_id(request)
        if not telegram_id:
            return Response({'error': 'telegram_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        seller = _get_seller(telegram_id)
        if not seller:
            return Response({'error': 'Not a seller'}, status=status.HTTP_403_FORBIDDEN)

        try:
            product = Product.objects.get(pk=pk, store=seller.store)
        except Product.DoesNotExist:
            return Response(
                {'error': 'Product not found or access denied'},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = ProductCreateSerializer(product, data=request.data, partial=True)
        if serializer.is_valid():
            updated = serializer.save()
            return Response(ProductSerializer(updated).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        """
        Soft-delete: marks product as unavailable instead of hard delete.
        Prevents ProtectedError from OrderItem FK.
        """
        telegram_id = get_telegram_id(request)
        if not telegram_id:
            return Response({'error': 'telegram_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        seller = _get_seller(telegram_id)
        if not seller:
            return Response({'error': 'Not a seller'}, status=status.HTTP_403_FORBIDDEN)

        try:
            product = Product.objects.get(pk=pk, store=seller.store)
        except Product.DoesNotExist:
            return Response(
                {'error': 'Product not found or access denied'},
                status=status.HTTP_404_NOT_FOUND
            )

        product.is_available = False
        product.save(update_fields=['is_available', 'updated_at'])
        logger.info(
            "Product '%s' (id=%d) deactivated by seller telegram_id=%s",
            product.name, product.id, telegram_id
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


# ============================================
# CUSTOMER LOCATION ENDPOINTS (authenticated)
# ============================================

class CustomerLocationListCreateView(APIView):
    """
    GET /api/locations/?telegram_id=XXX
    POST /api/locations/
    List and create customer locations.
    """
    authentication_classes = [TelegramInitDataAuthentication, BotSecretAuthentication]

    def get(self, request):
        telegram_id = get_telegram_id(request)
        if not telegram_id:
            return Response({'error': 'telegram_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            customer = Customer.objects.get(telegram_id=telegram_id)
        except Customer.DoesNotExist:
            return Response({'error': 'Customer not found'}, status=status.HTTP_404_NOT_FOUND)

        locations = Location.objects.filter(customer=customer)
        return Response(LocationSerializer(locations, many=True).data)

    def post(self, request):
        telegram_id = get_telegram_id(request)
        if not telegram_id:
            return Response({'error': 'telegram_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        customer, _ = Customer.objects.get_or_create(
            telegram_id=telegram_id,
            defaults={'first_name': '', 'last_name': ''}
        )

        serializer = LocationCreateSerializer(data=request.data)
        if serializer.is_valid():
            location = serializer.save(customer=customer)
            return Response(
                LocationSerializer(location).data,
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CustomerLocationDetailView(APIView):
    """
    PATCH /api/locations/{id}/
    DELETE /api/locations/{id}/
    Update or delete a customer location.
    """
    authentication_classes = [TelegramInitDataAuthentication, BotSecretAuthentication]

    def patch(self, request, pk):
        telegram_id = get_telegram_id(request)
        if not telegram_id:
            return Response({'error': 'telegram_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            customer = Customer.objects.get(telegram_id=telegram_id)
            location = Location.objects.get(pk=pk, customer=customer)
        except (Customer.DoesNotExist, Location.DoesNotExist):
            return Response({'error': 'Location not found'}, status=status.HTTP_404_NOT_FOUND)

        serializer = LocationCreateSerializer(location, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(LocationSerializer(location).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        telegram_id = get_telegram_id(request)
        if not telegram_id:
            return Response({'error': 'telegram_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            customer = Customer.objects.get(telegram_id=telegram_id)
            location = Location.objects.get(pk=pk, customer=customer)
        except (Customer.DoesNotExist, Location.DoesNotExist):
            return Response({'error': 'Location not found'}, status=status.HTTP_404_NOT_FOUND)

        location.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ============================================
# SELLER LOCATION ENDPOINTS (authenticated)
# ============================================

class SellerLocationListCreateView(generics.ListCreateAPIView):
    """
    GET /api/seller/locations/?telegram_id=XXX
    POST /api/seller/locations/
    List and create seller store locations.
    """
    authentication_classes = [TelegramInitDataAuthentication, BotSecretAuthentication]
    serializer_class = LocationCreateSerializer

    def get_queryset(self):
        telegram_id = get_telegram_id(self.request)
        if not telegram_id:
            return Location.objects.none()

        seller = _get_seller(telegram_id)
        if not seller:
            return Location.objects.none()

        return Location.objects.filter(store=seller.store)

    def perform_create(self, serializer):
        telegram_id = get_telegram_id(self.request)
        seller = _get_seller(telegram_id)
        if seller:
            serializer.save(store=seller.store)

    def create(self, request, *args, **kwargs):
        telegram_id = get_telegram_id(request)
        if not telegram_id:
            return Response({'error': 'telegram_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        seller = _get_seller(telegram_id)
        if not seller:
            return Response({'error': 'Not a seller'}, status=status.HTTP_403_FORBIDDEN)
            
        return super().create(request, *args, **kwargs)

    def list(self, request, *args, **kwargs):
        telegram_id = get_telegram_id(request)
        if not telegram_id:
            return Response({'error': 'telegram_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        seller = _get_seller(telegram_id)
        if not seller:
            return Response({'error': 'Not a seller'}, status=status.HTTP_403_FORBIDDEN)
            
        return super().list(request, *args, **kwargs)


class SellerLocationDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET /api/seller/locations/{id}/
    PATCH /api/seller/locations/{id}/
    DELETE /api/seller/locations/{id}/
    """
    authentication_classes = [TelegramInitDataAuthentication, BotSecretAuthentication]
    serializer_class = LocationCreateSerializer

    def get_queryset(self):
        telegram_id = get_telegram_id(self.request)
        if not telegram_id:
            return Location.objects.none()

        seller = _get_seller(telegram_id)
        if not seller:
            return Location.objects.none()

        return Location.objects.filter(store=seller.store)

    def update(self, request, *args, **kwargs):
        telegram_id = get_telegram_id(request)
        if not telegram_id:
            return Response({'error': 'telegram_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        seller = _get_seller(telegram_id)
        if not seller:
            return Response({'error': 'Not a seller'}, status=status.HTTP_403_FORBIDDEN)
            
        kwargs['partial'] = True
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        telegram_id = get_telegram_id(request)
        if not telegram_id:
            return Response({'error': 'telegram_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        seller = _get_seller(telegram_id)
        if not seller:
            return Response({'error': 'Not a seller'}, status=status.HTTP_403_FORBIDDEN)
            
        return super().destroy(request, *args, **kwargs)
