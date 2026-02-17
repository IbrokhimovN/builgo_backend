"""
API Views for BuildGo Backend.
No authentication. telegram_id is the single identity.
All endpoints are public or use telegram_id for identification.
"""

from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Q

from .models import Customer, Store, Seller, Category, Product, Order, Location
from .serializers import (
    CustomerSerializer, StoreSerializer,
    CategorySerializer, ProductSerializer, ProductCreateSerializer,
    OrderSerializer, OrderCreateSerializer, SellerSerializer,
    LocationSerializer, LocationCreateSerializer
)


# ============================================
# CUSTOMER ENDPOINTS
# ============================================

class CustomerCreateView(APIView):
    """
    POST /api/customers/
    Create or update a Customer by telegram_id.
    No auth required.
    """

    def post(self, request):
        telegram_id = request.data.get('telegram_id')
        if not telegram_id:
            return Response(
                {'error': 'telegram_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        customer, created = Customer.objects.update_or_create(
            telegram_id=telegram_id,
            defaults={
                'first_name': request.data.get('first_name', ''),
                'last_name': request.data.get('last_name', ''),
                'phone': request.data.get('phone', ''),
            }
        )

        return Response(
            CustomerSerializer(customer).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )


# ============================================
# SELLER CHECK
# ============================================

class CheckSellerView(APIView):
    """
    GET /api/check-seller/?telegram_id=XXX
    Check if telegram_id belongs to an active seller.
    No auth required.
    """

    def get(self, request):
        telegram_id = request.GET.get('telegram_id')
        if not telegram_id:
            return Response(
                {'error': 'telegram_id is required'},
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
        category_id = self.request.GET.get('category')
        if category_id:
            queryset = queryset.filter(category_id=category_id)
        return queryset


class OrderCreateView(APIView):
    """
    POST /api/orders/
    Create a new order. Accepts telegram_id in request body.
    No auth required.
    """

    def post(self, request):
        serializer = OrderCreateSerializer(data=request.data)
        if serializer.is_valid():
            order = serializer.save()
            return Response(
                OrderSerializer(order).data,
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SearchProductsView(APIView):
    """
    GET /api/search/?q=cement
    Search products across all stores.
    """

    def get(self, request):
        query = request.GET.get('q', '').strip()
        if not query:
            return Response({'results': []})

        products = Product.objects.filter(
            Q(name__icontains=query),
            is_available=True,
            store__is_active=True
        )[:50]

        return Response({
            'results': ProductSerializer(products, many=True).data
        })


# ============================================
# SELLER ENDPOINTS
# ============================================

def _get_seller(telegram_id):
    """Helper: get active Seller by telegram_id or return None."""
    try:
        return Seller.objects.select_related('store').get(
            telegram_id=telegram_id,
            is_active=True
        )
    except Seller.DoesNotExist:
        return None


class SellerOrdersView(APIView):
    """
    GET /api/seller/orders/?telegram_id=XXX
    List orders for seller's store.
    """

    def get(self, request):
        telegram_id = request.GET.get('telegram_id')
        if not telegram_id:
            return Response({'error': 'telegram_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        seller = _get_seller(telegram_id)
        if not seller:
            return Response({'error': 'Not a seller'}, status=status.HTTP_403_FORBIDDEN)

        orders = Order.objects.filter(store=seller.store).select_related('customer', 'store')
        return Response(OrderSerializer(orders, many=True).data)


class SellerOrderUpdateView(APIView):
    """
    PATCH /api/seller/orders/{id}/?telegram_id=XXX
    Update order status (seller only).
    """

    def patch(self, request, pk):
        telegram_id = request.data.get('telegram_id') or request.GET.get('telegram_id')
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
    telegram_id required in request body.
    """

    def post(self, request):
        telegram_id = request.data.get('telegram_id')
        if not telegram_id:
            return Response({'error': 'telegram_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        seller = _get_seller(telegram_id)
        if not seller:
            return Response({'error': 'Not a seller'}, status=status.HTTP_403_FORBIDDEN)

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
    telegram_id required in request body or query param.
    """

    def patch(self, request, pk):
        telegram_id = request.data.get('telegram_id') or request.GET.get('telegram_id')
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
            serializer.save()
            return Response(ProductSerializer(product).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ============================================
# CUSTOMER LOCATION ENDPOINTS
# ============================================

class CustomerLocationListCreateView(APIView):
    """
    GET /api/locations/?telegram_id=XXX
    POST /api/locations/
    List and create customer locations.
    """

    def get(self, request):
        telegram_id = request.GET.get('telegram_id')
        if not telegram_id:
            return Response({'error': 'telegram_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            customer = Customer.objects.get(telegram_id=telegram_id)
        except Customer.DoesNotExist:
            return Response({'error': 'Customer not found'}, status=status.HTTP_404_NOT_FOUND)

        locations = Location.objects.filter(customer=customer)
        return Response(LocationSerializer(locations, many=True).data)

    def post(self, request):
        telegram_id = request.data.get('telegram_id')
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

    def patch(self, request, pk):
        telegram_id = request.data.get('telegram_id') or request.GET.get('telegram_id')
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
        telegram_id = request.GET.get('telegram_id')
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
# SELLER LOCATION ENDPOINTS
# ============================================

class SellerLocationListCreateView(APIView):
    """
    GET /api/seller/locations/?telegram_id=XXX
    POST /api/seller/locations/
    List and create seller store locations.
    """

    def get(self, request):
        telegram_id = request.GET.get('telegram_id')
        if not telegram_id:
            return Response({'error': 'telegram_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        seller = _get_seller(telegram_id)
        if not seller:
            return Response({'error': 'Not a seller'}, status=status.HTTP_403_FORBIDDEN)

        locations = Location.objects.filter(store=seller.store)
        return Response(LocationSerializer(locations, many=True).data)

    def post(self, request):
        telegram_id = request.data.get('telegram_id')
        if not telegram_id:
            return Response({'error': 'telegram_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        seller = _get_seller(telegram_id)
        if not seller:
            return Response({'error': 'Not a seller'}, status=status.HTTP_403_FORBIDDEN)

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
    """

    def patch(self, request, pk):
        telegram_id = request.data.get('telegram_id') or request.GET.get('telegram_id')
        if not telegram_id:
            return Response({'error': 'telegram_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        seller = _get_seller(telegram_id)
        if not seller:
            return Response({'error': 'Not a seller'}, status=status.HTTP_403_FORBIDDEN)

        try:
            location = Location.objects.get(pk=pk, store=seller.store)
        except Location.DoesNotExist:
            return Response({'error': 'Location not found'}, status=status.HTTP_404_NOT_FOUND)

        serializer = LocationCreateSerializer(location, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(LocationSerializer(location).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        telegram_id = request.GET.get('telegram_id')
        if not telegram_id:
            return Response({'error': 'telegram_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        seller = _get_seller(telegram_id)
        if not seller:
            return Response({'error': 'Not a seller'}, status=status.HTTP_403_FORBIDDEN)

        try:
            location = Location.objects.get(pk=pk, store=seller.store)
        except Location.DoesNotExist:
            return Response({'error': 'Location not found'}, status=status.HTTP_404_NOT_FOUND)

        location.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
