"""
URL configuration for core app.

Public endpoints: stores, categories, products, search
Authenticated endpoints: all others (initData or BotSecret)
"""

from django.urls import path
from . import views

urlpatterns = [
    # Customer (bot-authenticated)
    path('customers/', views.CustomerCreateView.as_view(), name='customer-create'),
    path('customers/check/', views.CustomerCheckView.as_view(), name='customer-check'),

    # Seller check (bot-authenticated)
    path('check-seller/', views.CheckSellerView.as_view(), name='check-seller'),

    path('stores/', views.StoreListView.as_view(), name='store-list'),
    path('categories/', views.CategoryListView.as_view(), name='category-list'),
    path('stores/<int:store_id>/categories/', views.StoreCategoriesView.as_view(), name='store-categories'),
    path('stores/<int:store_id>/products/', views.StoreProductsView.as_view(), name='store-products'),
    path('products/<int:pk>/', views.StoreProductDetailView.as_view(), name='product-detail'),
    path('products/<int:pk>/related/', views.ProductRecommendationView.as_view(), name='product-related'),
    path('stores/<int:store_id>/rate/', views.StoreRateView.as_view(), name='store-rate'),
    path('search/', views.UniversalSearchView.as_view(), name='search-universal'),
    path('search/suggestions/', views.SearchSuggestionView.as_view(), name='search-suggestions'),

    # Customer specific endpoints
    path('customer/active-order/', views.CustomerActiveOrderView.as_view(), name='customer-active-order'),

    # Cart endpoints (authenticated)
    path('customer/cart/', views.CartItemListView.as_view(), name='customer-cart'),
    path('customer/cart/<int:pk>/', views.CartItemDetailView.as_view(), name='customer-cart-detail'),
    path('customer/cart/clear/', views.CartClearView.as_view(), name='customer-cart-clear'),

    # Order endpoints (authenticated)
    path('orders/', views.OrderCreateView.as_view(), name='order-create'),
    path('orders/my/', views.CustomerOrdersView.as_view(), name='customer-orders'),

    # Customer location endpoints (authenticated)
    path('locations/', views.CustomerLocationListCreateView.as_view(), name='customer-locations'),
    path('locations/<int:pk>/', views.CustomerLocationDetailView.as_view(), name='customer-location-detail'),

    # Seller endpoints (authenticated)
    path('seller/profile/', views.SellerProfileView.as_view(), name='seller-profile'),
    path('seller/analytics/', views.SellerAnalyticsView.as_view(), name='seller-analytics'),
    path('seller/store/', views.SellerStoreUpdateView.as_view(), name='seller-store-update'),
    path('seller/orders/', views.SellerOrdersView.as_view(), name='seller-orders'),
    path('seller/orders/<int:pk>/', views.SellerOrderUpdateView.as_view(), name='seller-order-update'),
    path('seller/products/', views.SellerProductListCreateView.as_view(), name='seller-products'),
    path('seller/products/<int:pk>/', views.SellerProductUpdateView.as_view(), name='seller-product-update'),
    path('seller/categories/', views.SellerCategoryListCreateView.as_view(), name='seller-categories'),

    # Seller location endpoints (authenticated)
    path('seller/locations/', views.SellerLocationListCreateView.as_view(), name='seller-locations'),
    path('seller/locations/<int:pk>/', views.SellerLocationDetailView.as_view(), name='seller-location-detail'),
]
