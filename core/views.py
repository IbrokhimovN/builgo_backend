"""
API Views for BuildGo Backend.

Authentication:
- JWT Authentication (web login via phone_number + password)
- Mini App requests: TelegramInitDataAuthentication (HMAC-SHA256)
- Bot requests: BotSecretAuthentication (shared secret header)
- Public endpoints: stores, categories, products, search (no auth required)

Role logic is UNCHANGED. telegram_id resolution stays per-request.
"""

import logging
from django.db import IntegrityError
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Q
from django.contrib.postgres.search import SearchQuery
from django.core.cache import cache

from .authentication import (
    TelegramInitDataAuthentication,
    BotSecretAuthentication,
    get_telegram_id,
)
from .models import Customer, Store, Seller, Category, Product, Order, Location, User, StoreDocument
from .serializers import (
    CustomerSerializer, StoreSerializer,
    CategorySerializer, ProductListSerializer, ProductDetailSerializer, ProductCreateSerializer,
    OrderSerializer, OrderCreateSerializer, SellerSerializer,
    LocationSerializer, LocationCreateSerializer, StoreRatingSerializer,
    SellerStoreUpdateSerializer, CartItemSerializer,
    SetPasswordSerializer, WebLoginSerializer, StoreVerificationSerializer, StoreDocumentSerializer,
)
from .permissions import IsBuyer, IsSeller, IsUnverifiedSeller

logger = logging.getLogger(__name__)

# Valid order statuses for seller updates
VALID_ORDER_STATUSES = {'new', 'processing', 'done', 'cancelled'}


# ============================================
# AUTH ENDPOINTS (JWT + Telegram)
# ============================================

class SetPasswordView(APIView):
    """
    POST /api/auth/set-password/
    For Telegram-authenticated users to set a web password and save phone_number.
    Creates or updates the User record linked via telegram_id.
    """
    authentication_classes = [TelegramInitDataAuthentication, BotSecretAuthentication]

    def post(self, request):
        telegram_id = get_telegram_id(request)
        if not telegram_id:
            return Response(
                {'error': 'telegram_id is required (authenticate via Telegram first)'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        serializer = SetPasswordSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)

        phone_number = serializer.validated_data['phone_number']
        password = serializer.validated_data['password']

        # Get or create User by telegram_id
        user, created = User.objects.get_or_create(
            telegram_id=telegram_id,
            defaults={'phone_number': phone_number}
        )

        if not created:
            user.phone_number = phone_number

        user.set_password(password)
        user.save()

        # Also update Customer's phone if customer record exists
        Customer.objects.filter(telegram_id=telegram_id).update(phone=phone_number)

        logger.info(
            "User %s: telegram_id=%s set web password",
            "created" if created else "updated", telegram_id
        )

        return Response({
            'message': 'Password set successfully.',
            'phone_number': phone_number,
        }, status=status.HTTP_200_OK)


class WebLoginView(APIView):
    """
    POST /api/auth/web-login/
    Authenticate via phone_number + password, returning JWT tokens.
    No Telegram auth required.
    """
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = WebLoginSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data, status=status.HTTP_200_OK)


class RegisterStoreView(APIView):
    """
    POST /api/auth/register-store/
    Creates a Store profile for an authenticated Telegram user.
    Request body: { "name": "Store Name" }
    Creates: User (if not exists) → Store → Seller record.
    """
    authentication_classes = [TelegramInitDataAuthentication, BotSecretAuthentication]

    def post(self, request):
        telegram_id = get_telegram_id(request)
        if not telegram_id:
            return Response(
                {'error': 'telegram_id is required'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        store_name = request.data.get('name', '').strip()
        if not store_name:
            return Response(
                {'error': 'Store name is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if user already has a store (via Seller record)
        if Seller.objects.filter(telegram_id=telegram_id).exists():
            return Response(
                {'error': 'You already have a store registered'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get or create User for this telegram_id
        user, _ = User.objects.get_or_create(
            telegram_id=telegram_id,
            defaults={'phone_number': f'tg_{telegram_id}'}
        )

        # Create Store linked to user
        store = Store.objects.create(
            user=user,
            name=store_name,
            status='pending',
        )

        # Create Seller record
        tg_user = getattr(request, '_tg_user', None)
        seller_name = ''
        if tg_user:
            seller_name = f"{tg_user.get('first_name', '')} {tg_user.get('last_name', '')}".strip()
        if not seller_name:
            seller_name = store_name

        seller = Seller.objects.create(
            telegram_id=telegram_id,
            name=seller_name,
            store=store,
        )

        logger.info(
            "Store '%s' (id=%d) registered by telegram_id=%s",
            store.name, store.id, telegram_id
        )

        from .serializers import SellerSerializer
        return Response({
            'message': 'Store registered successfully.',
            'is_seller': True,
            'seller': SellerSerializer(seller).data,
        }, status=status.HTTP_201_CREATED)

class VerifyStoreView(APIView):
    """
    POST /api/auth/verify-store/
    Accepts multipart/form-data with INN, legal_name, and document file uploads.
    Authenticated via Telegram initData or JWT.
    Uses IsAuthenticated — sellers must be logged in but do NOT need to be approved yet.
    """
    authentication_classes = [TelegramInitDataAuthentication, BotSecretAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        telegram_id = get_telegram_id(request)
        if not telegram_id:
            return Response(
                {'error': 'telegram_id is required'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        seller = _get_seller(telegram_id)
        if not seller:
            return Response({'error': 'Not a seller'}, status=status.HTTP_403_FORBIDDEN)

        store = seller.store

        # Extract fields
        legal_name = request.data.get('legal_name', '').strip()
        inn = request.data.get('inn', '').strip()

        if not legal_name or not inn:
            return Response(
                {'error': 'legal_name and inn are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Update store legal fields
        store.legal_name = legal_name
        store.inn = inn
        store.status = 'pending'
        store.save(update_fields=['legal_name', 'inn', 'status', 'updated_at'])

        # Process uploaded documents
        documents_created = []
        files = request.FILES.getlist('documents')
        doc_types = request.data.getlist('document_types') if hasattr(request.data, 'getlist') else []

        for i, file in enumerate(files):
            doc_type = doc_types[i] if i < len(doc_types) else 'guvohnoma'
            if doc_type not in ('guvohnoma', 'passport'):
                doc_type = 'guvohnoma'
            doc = StoreDocument.objects.create(
                store=store,
                document_type=doc_type,
                file=file,
            )
            documents_created.append(StoreDocumentSerializer(doc).data)

        logger.info(
            "Store '%s' (id=%d) submitted verification by seller telegram_id=%s",
            store.name, store.id, telegram_id
        )

        return Response({
            'message': 'Verification documents submitted successfully.',
            'store_status': store.status,
            'legal_name': store.legal_name,
            'inn': store.inn,
            'documents': documents_created,
        }, status=status.HTTP_200_OK)

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
    serializer_class = StoreSerializer

    def get_queryset(self):
        queryset = Store.objects.filter(is_active=True).prefetch_related('products__category')
        category_id = self.request.query_params.get('category_id')
        if category_id:
            queryset = queryset.filter(products__category_id=category_id).distinct()
        return queryset

    def list(self, request, *args, **kwargs):
        category_id = request.query_params.get('category_id', 'all')
        cache_key = f'stores_list_active_{category_id}'
        data = cache.get(cache_key)
        if not data:
            response = super().list(request, *args, **kwargs)
            data = response.data
            cache.set(cache_key, data, timeout=60 * 60)  # 1 hour
        return Response(data)

class CategoryListView(generics.ListAPIView):
    """
    GET /api/categories/
    List all global categories. Public.
    """
    authentication_classes = []
    permission_classes = [AllowAny]
    queryset = Category.objects.filter(store__isnull=True).order_by('name')
    serializer_class = CategorySerializer


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

    def list(self, request, *args, **kwargs):
        store_id = self.kwargs['store_id']
        cache_key = f'store_{store_id}_categories'
        data = cache.get(cache_key)
        if not data:
            response = super().list(request, *args, **kwargs)
            data = response.data
            cache.set(cache_key, data, timeout=60 * 60)
        return Response(data)


class StoreProductsView(generics.ListAPIView):
    """
    GET /api/stores/{id}/products/
    GET /api/stores/{id}/products/?category=X
    List products for a specific store. Public.
    """
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = ProductListSerializer

    def get_queryset(self):
        store_id = self.kwargs['store_id']
        queryset = Product.objects.select_related('store', 'category').filter(
            store_id=store_id,
            is_available=True
        )
        category_id = self.request.GET.get('category')
        if category_id:
            queryset = queryset.filter(category_id=category_id)
        return queryset

    def list(self, request, *args, **kwargs):
        store_id = self.kwargs['store_id']
        category_id = self.request.GET.get('category', '')
        
        # We don't want to break cursor pagination caching by caching a single large list.
        # So we include query parameters in the cache key.
        cache_key = f'store_{store_id}_products_{category_id}'
        # InDRF, generic lists handle pagination natively. 
        # Caching the paginated response dictates using the exact page query param too.
        page = self.request.GET.get('page', '1')
        cache_key += f'_page_{page}'
        
        data = cache.get(cache_key)
        if not data:
            response = super().list(request, *args, **kwargs)
            data = response.data
            cache.set(cache_key, data, timeout=60 * 15)  # 15 minutes
        return Response(data)


class StoreProductDetailView(generics.RetrieveAPIView):
    """
    GET /api/products/{id}/
    Retrieve full details of a specific product. Public.
    """
    authentication_classes = []
    permission_classes = [AllowAny]
    queryset = Product.objects.select_related('store', 'category').filter(is_available=True)
    serializer_class = ProductDetailSerializer

    def retrieve(self, request, *args, **kwargs):
        product_id = self.kwargs.get('pk')
        cache_key = f'product_detail_{product_id}'
        data = cache.get(cache_key)
        if not data:
            response = super().retrieve(request, *args, **kwargs)
            data = response.data
            cache.set(cache_key, data, timeout=60 * 60)
        return Response(data)

class UniversalSearchView(APIView):
    """
    GET /api/search/?q=
    Search across products, stores, categories. Public.
    """
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        query = request.GET.get('q', '').strip()
        if not query:
            return Response({
                "products": [],
                "stores": [],
                "categories": []
            })
            
        from django.contrib.postgres.search import SearchQuery, SearchRank
        from django.db.models import F, Q

        search_query = SearchQuery(query)
        
        products = Product.objects.select_related('store', 'category').annotate(
            rank=SearchRank(F('search_vector'), search_query)
        ).filter(
            Q(rank__gte=0.05) | Q(name__icontains=query),
            is_available=True,
            store__is_active=True
        ).order_by('-rank')[:20]
        
        stores = Store.objects.filter(
            Q(name__icontains=query) | Q(products__category__name__icontains=query),
            is_active=True
        ).distinct()[:20]
        
        categories = Category.objects.filter(
            name__icontains=query,
            store__isnull=True
        )[:10]
        
        # Track search term
        if query:
            from .models import SearchTerm
            try:
                term_obj, created = SearchTerm.objects.get_or_create(term=query.lower())
                if not created:
                    term_obj.count += 1
                    term_obj.save(update_fields=['count', 'updated_at'])
            except Exception as e:
                logger.error(f"Failed to track search term: {e}")
        
        return Response({
            "products": ProductListSerializer(products, many=True).data,
            "stores": StoreSerializer(stores, many=True).data,
            "categories": CategorySerializer(categories, many=True).data
        })


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

class CustomerActiveOrderView(APIView):
    """
    GET /api/customer/active-order/
    Check if customer has any active orders ('new' or 'processing').
    Used to prompt address confirmation on app launch.
    """
    authentication_classes = [TelegramInitDataAuthentication, BotSecretAuthentication]

    def get(self, request):
        telegram_id = get_telegram_id(request)
        if not telegram_id:
             return Response({"has_active_order": False})
        
        try:
             customer = Customer.objects.get(telegram_id=telegram_id)
        except Customer.DoesNotExist:
             return Response({"has_active_order": False})
             
        has_active = Order.objects.filter(
             customer=customer, 
             status__in=['new', 'processing']
        ).exists()
        
        return Response({"has_active_order": has_active})

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

        # Validate business rules: customer phone and location
        customer = Customer.objects.filter(telegram_id=telegram_id).first()
        if not customer:
            return Response({'error': 'Customer not found'}, status=status.HTTP_400_BAD_REQUEST)
        
        if not customer.phone:
            return Response(
                {"error": "Phone number is required to place an order"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        location = Location.objects.filter(customer=customer, is_default=True).first()
        if not location:
            # Fallback to any location just in case they don't have a default
            location = Location.objects.filter(customer=customer).first()
            if not location:
                return Response(
                    {"error": "Delivery location is required to place an order"},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Validate that the store is open
        store_id = data.get('store')
        if store_id:
            try:
                store = Store.objects.get(id=store_id, is_active=True)
                if not store.is_open:
                    return Response(
                        {"error": "This store is currently closed. You cannot place an order at this time."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            except Store.DoesNotExist:
                return Response(
                    {"error": "Store not found or is inactive."},
                    status=status.HTTP_400_BAD_REQUEST
                )

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


class StoreRateView(APIView):
    """
    POST /api/stores/{id}/rate/
    Rate a store. Authenticated via initData or BotSecret.
    """
    authentication_classes = [TelegramInitDataAuthentication, BotSecretAuthentication]

    def post(self, request, store_id):
        telegram_id = get_telegram_id(request)
        if not telegram_id:
            return Response({'error': 'telegram_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            store = Store.objects.get(id=store_id, is_active=True)
        except Store.DoesNotExist:
            return Response({'error': 'Store not found'}, status=status.HTTP_404_NOT_FOUND)

        customer = Customer.objects.filter(telegram_id=telegram_id).first()
        if not customer:
            return Response({'error': 'Customer not found'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Guard: Seller cannot rate their own store
        seller = _get_seller(telegram_id)
        if seller and seller.store_id == store.id:
            return Response(
                {'error': 'You cannot rate your own store'},
                status=status.HTTP_403_FORBIDDEN
            )
            
        serializer = StoreRatingSerializer(data=request.data)
        if serializer.is_valid():
            from .models import StoreRating
            rating_val = serializer.validated_data['rating']
            rating, created = StoreRating.objects.update_or_create(
                store=store,
                customer=customer,
                defaults={'rating': rating_val}
            )
            return Response(
                StoreRatingSerializer(rating).data,
                status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ============================================
# SELLER ENDPOINTS (authenticated via initData)
# ============================================

class SellerStoreUpdateView(generics.RetrieveUpdateAPIView):
    """
    GET /api/seller/store/
    PATCH /api/seller/store/
    Retrieve and update seller's own store.
    """
    authentication_classes = [TelegramInitDataAuthentication, BotSecretAuthentication]
    serializer_class = SellerStoreUpdateSerializer

    def get_object(self):
        telegram_id = get_telegram_id(self.request)
        if not telegram_id:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'error': 'telegram_id is required'})
            
        seller = _get_seller(telegram_id)
        if not seller:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied({'error': 'Not a seller'})
            
        return seller.store

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        if 'working_hours_json' in data:
            import json
            try:
                parsed = json.loads(data['working_hours_json'])
                if hasattr(data, 'setlist'):
                    # QueryDict (multipart/form-data) requires setlist for lists
                    # But actually nested lists of dicts in DRF might just need setting
                    # However, DRF's ListField requires a list. Let's try basic assignment
                    # or creating a regular dict.
                    pass
                data['working_hours'] = parsed
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning("Failed to parse working_hours_json: %s", e)

        # Build regular dict if data is QueryDict to avoid setlist issues with complex types
        if hasattr(data, 'dict'):
            parsed_data = {}
            for k in data.keys():
                if k == 'working_hours':
                    parsed_data[k] = data[k]
                else:
                    parsed_data[k] = data.get(k)
            data = parsed_data

        serializer = self.get_serializer(instance, data=data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)

    def patch(self, request, *args, **kwargs):
        kwargs['partial'] = True
        return self.update(request, *args, **kwargs)

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

        products = Product.objects.select_related('store', 'category').filter(store=seller.store)
        # Apply DRF pagination
        from rest_framework.pagination import PageNumberPagination
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(products, request)
        if page is not None:
            serializer = ProductListSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)
        serializer = ProductListSerializer(products, many=True)
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
                ProductDetailSerializer(product).data,
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

        return Category.objects.select_related('store').filter(store=seller.store)

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
            return Response(ProductDetailSerializer(updated).data)
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
    pagination_class = None

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

# ============================================
# CART ENDPOINTS (authenticated)
# ============================================

from .serializers import CartItemSerializer

class CartItemListView(APIView):
    """
    GET /api/customer/cart/
    POST /api/customer/cart/
    List cart items or add item to cart. Authenticated via initData or BotSecret.
    """
    authentication_classes = [TelegramInitDataAuthentication, BotSecretAuthentication]

    def get(self, request):
        telegram_id = get_telegram_id(request)
        if not telegram_id:
            return Response({'error': 'telegram_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            customer = Customer.objects.get(telegram_id=telegram_id)
        except Customer.DoesNotExist:
            return Response([])

        from .models import CartItem
        items = CartItem.objects.filter(customer=customer).select_related('product', 'variant')
        return Response(CartItemSerializer(items, many=True).data)

    def post(self, request):
        telegram_id = get_telegram_id(request)
        if not telegram_id:
            return Response({'error': 'telegram_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            customer = Customer.objects.get(telegram_id=telegram_id)
        except Customer.DoesNotExist:
             return Response({'error': 'Customer not found'}, status=status.HTTP_400_BAD_REQUEST)

        product_id = request.data.get('product_id')
        variant_id = request.data.get('variant_id')
        quantity = request.data.get('quantity', 1)

        if not product_id:
             return Response({'error': 'product_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
             product = Product.objects.get(id=product_id, is_available=True)
        except Product.DoesNotExist:
             return Response({'error': 'Product not found or unavailable'}, status=status.HTTP_404_NOT_FOUND)

        from .models import ProductVariant, CartItem

        variant = None
        if variant_id:
             try:
                 variant = ProductVariant.objects.get(id=variant_id, product=product)
             except ProductVariant.DoesNotExist:
                 return Response({'error': 'Variant not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Check against existing items from different stores
        if CartItem.objects.filter(customer=customer).exclude(product__store=product.store).exists():
             return Response({'error': 'Cart contains items from another store', 'conflict': True}, status=status.HTTP_409_CONFLICT)

        cart_item, created = CartItem.objects.get_or_create(
             customer=customer,
             product=product,
             variant=variant,
             defaults={'quantity': quantity}
        )

        if not created:
             cart_item.quantity += int(quantity)
             cart_item.save()

        return Response(CartItemSerializer(cart_item).data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class CartItemDetailView(APIView):
    """
    PATCH /api/customer/cart/{id}/
    DELETE /api/customer/cart/{id}/
    Update quantity or delete cart item.
    """
    authentication_classes = [TelegramInitDataAuthentication, BotSecretAuthentication]

    def patch(self, request, pk):
        telegram_id = get_telegram_id(request)
        if not telegram_id:
            return Response({'error': 'telegram_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
             customer = Customer.objects.get(telegram_id=telegram_id)
        except Customer.DoesNotExist:
             return Response({'error': 'Customer not found'}, status=status.HTTP_400_BAD_REQUEST)

        quantity = request.data.get('quantity')
        if quantity is None:
             return Response({'error': 'quantity is required'}, status=status.HTTP_400_BAD_REQUEST)
             
        try:
            quantity_int = int(quantity)
        except ValueError:
            return Response({'error': 'invalid quantity format'}, status=status.HTTP_400_BAD_REQUEST)

        from .models import CartItem
        try:
             item = CartItem.objects.get(id=pk, customer=customer)
        except CartItem.DoesNotExist:
             return Response({'error': 'Cart item not found'}, status=status.HTTP_404_NOT_FOUND)

        if quantity_int <= 0:
             item.delete()
             return Response(status=status.HTTP_204_NO_CONTENT)

        item.quantity = quantity_int
        item.save()
        return Response(CartItemSerializer(item).data)

    def delete(self, request, pk):
         telegram_id = get_telegram_id(request)
         if not telegram_id:
             return Response({'error': 'telegram_id is required'}, status=status.HTTP_400_BAD_REQUEST)

         try:
              customer = Customer.objects.get(telegram_id=telegram_id)
         except Customer.DoesNotExist:
              return Response({'error': 'Customer not found'}, status=status.HTTP_400_BAD_REQUEST)

         from .models import CartItem
         try:
              item = CartItem.objects.get(id=pk, customer=customer)
              item.delete()
         except CartItem.DoesNotExist:
              return Response({'error': 'Cart item not found'}, status=status.HTTP_404_NOT_FOUND)

         return Response(status=status.HTTP_204_NO_CONTENT)

class CartClearView(APIView):
     """
     DELETE /api/customer/cart/clear/
     Clear all items in cart.
     """
     authentication_classes = [TelegramInitDataAuthentication, BotSecretAuthentication]
     
     def delete(self, request):
         telegram_id = get_telegram_id(request)
         if not telegram_id:
             return Response({'error': 'telegram_id is required'}, status=status.HTTP_400_BAD_REQUEST)

         try:
              customer = Customer.objects.get(telegram_id=telegram_id)
         except Customer.DoesNotExist:
              return Response({'error': 'Customer not found'}, status=status.HTTP_400_BAD_REQUEST)

         from .models import CartItem
         CartItem.objects.filter(customer=customer).delete()
         return Response(status=status.HTTP_204_NO_CONTENT)


class SearchSuggestionView(APIView):
    """
    GET /api/search/suggestions/?q=
    Returns top search term suggestions matching q.
    """
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        query = request.GET.get('q', '').strip()
        if not query:
            return Response({"suggestions": []})
        
        from .models import SearchTerm
        terms = SearchTerm.objects.filter(term__icontains=query.lower()).order_by('-count', '-updated_at')[:10]
        return Response({"suggestions": [t.term for t in terms]})


class SellerAnalyticsView(APIView):
    """
    GET /api/seller/analytics/
    Returns orders_today, revenue_today, top_products.
    Authenticated via initData.
    """
    authentication_classes = [TelegramInitDataAuthentication, BotSecretAuthentication]

    def get(self, request):
        telegram_id = get_telegram_id(request)
        if not telegram_id:
            return Response({'error': 'telegram_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        seller = _get_seller(telegram_id)
        if not seller:
            return Response({'error': 'Not a seller'}, status=status.HTTP_403_FORBIDDEN)
            
        range_param = request.GET.get('range', 'daily')
        from django.utils import timezone
        from datetime import timedelta
        from django.db.models import Sum, F
        
        now = timezone.localtime()
        
        if range_param == 'weekly':
            start_date = now - timedelta(days=7)
        elif range_param == 'monthly':
            start_date = now - timedelta(days=30)
        elif range_param == 'all':
            start_date = None
        else: # daily
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
            
        orders_qs = Order.objects.filter(store=seller.store)
        if start_date and range_param == 'daily':
            orders_qs = orders_qs.filter(created_at__date=start_date.date())
        elif start_date:
            orders_qs = orders_qs.filter(created_at__gte=start_date)
            
        orders_count = orders_qs.count()
        valid_orders = orders_qs.exclude(status='cancelled')
        
        revenue_calc = OrderItem.objects.filter(order__in=valid_orders).annotate(
            total_price=F('quantity') * F('price_at_order')
        ).aggregate(sum=Sum('total_price'))['sum']
        
        revenue = revenue_calc if revenue_calc else 0.0

        delivered = valid_orders.filter(status='done').count()
        pending = valid_orders.filter(status__in=['new', 'processing']).count()
        average_check = revenue / valid_orders.count() if valid_orders.count() > 0 else 0

        chart = []
        if range_param == 'daily':
            chart = [0, revenue, revenue]
        elif range_param == 'weekly':
            for d in range(6, -1, -1):
                day_start = (now - timedelta(days=d)).date()
                day_rev = OrderItem.objects.filter(order__in=valid_orders.filter(created_at__date=day_start)).annotate(total_price=F('quantity') * F('price_at_order')).aggregate(sum=Sum('total_price'))['sum'] or 0
                chart.append(day_rev)
        elif range_param == 'monthly':
            for d in range(29, -1, -1):
                day_start = (now - timedelta(days=d)).date()
                day_rev = OrderItem.objects.filter(order__in=valid_orders.filter(created_at__date=day_start)).annotate(total_price=F('quantity') * F('price_at_order')).aggregate(sum=Sum('total_price'))['sum'] or 0
                chart.append(day_rev)
        else:
            chart = [0, revenue]

        top_items = OrderItem.objects.filter(order__in=valid_orders).values(
            'product__id', 'product__name'
        ).annotate(
            total_sold=Sum('quantity')
        ).order_by('-total_sold')[:5]
        
        top_products = [
            {
                "id": item['product__id'],
                "name": item['product__name'],
                "sold": item['total_sold']
            }
            for item in top_items
        ]
        
        return Response({
            "revenue": revenue,
            "orders": orders_count,
            "delivered": delivered,
            "pending": pending,
            "average_check": average_check,
            "chart": chart,
            "top_products": top_products
        })


class ProductRecommendationView(APIView):
    """
    GET /api/products/<int:pk>/related/
    Returns related products (same category).
    """
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, pk):
        try:
            product = Product.objects.get(pk=pk)
        except Product.DoesNotExist:
            return Response({'error': 'Product not found'}, status=status.HTTP_404_NOT_FOUND)
            
        queryset = Product.objects.select_related('store', 'category').filter(
            category=product.category,
            store=product.store,
            is_available=True
        ).exclude(pk=pk).order_by('-created_at')[:10]
        
        if not queryset.exists():
            queryset = Product.objects.select_related('store', 'category').filter(
                store=product.store,
                is_available=True
            ).exclude(pk=pk).order_by('-created_at')[:10]
            
        return Response(ProductListSerializer(queryset, many=True).data)


# ============================================
# RBAC DEMO ENDPOINTS
# ============================================

class CreateProductExampleView(APIView):
    """
    POST /api/demo/create-product/
    Demo endpoint protected by IsSeller permission.
    Only sellers with store.status == 'approved' can access this.
    """
    permission_classes = [IsSeller]

    def post(self, request):
        return Response({
            'message': 'Success! You are an approved seller and can create products.',
            'user': str(request.user),
        }, status=status.HTTP_200_OK)


class CreateOrderExampleView(APIView):
    """
    POST /api/demo/create-order/
    Demo endpoint protected by IsBuyer permission.
    Only users with a linked Customer profile can access this.
    """
    permission_classes = [IsBuyer]

    def post(self, request):
        return Response({
            'message': 'Success! You are a buyer and can create orders.',
            'user': str(request.user),
        }, status=status.HTTP_200_OK)
