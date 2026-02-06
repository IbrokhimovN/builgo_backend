"""
URL configuration for core app.
"""

from django.urls import path
from . import views

urlpatterns = [
    # Authentication
    path('telegram-auth/', views.TelegramAuthView.as_view(), name='telegram-auth'),
    path('check-seller/', views.check_seller, name='check-seller'),
    path('seller/me/', views.seller_me, name='seller-me'),
    
    # Buyer endpoints
    path('stores/', views.StoreListView.as_view(), name='store-list'),
    path('stores/<int:store_id>/categories/', views.StoreCategoriesView.as_view(), name='store-categories'),
    path('stores/<int:store_id>/products/', views.StoreProductsView.as_view(), name='store-products'),
    path('orders/', views.OrderCreateView.as_view(), name='order-create'),
    path('search/', views.search_products, name='search-products'),
    
    # Customer location endpoints
    path('locations/', views.CustomerLocationListCreateView.as_view(), name='customer-locations'),
    path('locations/<int:pk>/', views.CustomerLocationDetailView.as_view(), name='customer-location-detail'),
    
    # Seller endpoints
    path('seller/orders/', views.SellerOrdersView.as_view(), name='seller-orders'),
    path('seller/orders/<int:pk>/', views.SellerOrderUpdateView.as_view(), name='seller-order-update'),
    path('seller/products/', views.SellerProductCreateView.as_view(), name='seller-product-create'),
    path('seller/products/<int:pk>/', views.SellerProductUpdateView.as_view(), name='seller-product-update'),
    
    # Seller location endpoints
    path('seller/locations/', views.SellerLocationListCreateView.as_view(), name='seller-locations'),
    path('seller/locations/<int:pk>/', views.SellerLocationDetailView.as_view(), name='seller-location-detail'),
]
