# api/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    AnimalViewSet,
    OrderViewSet,
    MakePaymentView,
    MpesaCallbackView,
    UserProfileView,
    RegisterUserView,
)

# The router automatically generates URL patterns for ViewSets
router = DefaultRouter()
router.register(r'animals', AnimalViewSet, basename='animal')
router.register(r'orders', OrderViewSet, basename='order')

urlpatterns = [
    # ViewSet routes
    path('', include(router.urls)),
    
    # Custom view routes
    path('register/', RegisterUserView.as_view(), name='register-user'),
    path('users/me/', UserProfileView.as_view(), name='user-profile'),
    path('make-payment/', MakePaymentView.as_view(), name='make-payment'),
    path('mpesa-callback/', MpesaCallbackView.as_view(), name='mpesa-callback'),
]
