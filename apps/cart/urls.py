from django.urls import path

from .views import CartView, AddToCartView, RemoveFromCartView, ChangeQuantityView, ClearCartView, CheckoutView, ApplyPromoCodeView

urlpatterns = [
    path('', CartView.as_view(), name = 'cart'),
    path('add-to-cart/<str:ct_model>/<str:slug>/', AddToCartView.as_view(), name = 'add_to_cart'),
    path('remove-from-cart/<str:ct_model>/<str:slug>/', RemoveFromCartView.as_view(), name = 'remove_from_cart'),
    path('change-qty/<str:ct_model>/<str:slug>/', ChangeQuantityView.as_view(), name = 'change_quantity'),
    path('apply-promocode/', ApplyPromoCodeView.as_view(), name = 'apply_promocode'),
    path('checkout/', CheckoutView.as_view(), name = 'checkout'),
    path('clear-cart/', ClearCartView.as_view(), name='clear_cart'),
]