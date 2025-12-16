from django.urls import path

from .views import MakeOrderView, SubmitReturnView, CancelReturnView, PaymentSuccessView, PaymentCancelView, StripeWebhookView

urlpatterns = [
    path('order/', MakeOrderView.as_view(), name = 'order'),
    path('<int:order_id>/return/', SubmitReturnView.as_view(), name = 'submit_return'),
    path('<int:return_id>/cancel/', CancelReturnView.as_view(), name = 'cancel_return'),

    path('payment/success/', PaymentSuccessView.as_view(), name = 'payment_success'),
    path('payment/cancel/', PaymentCancelView.as_view(), name = 'payment_cancel'),
    path('webhook/stripe/', StripeWebhookView.as_view(), name = 'stripe_webhook'),
]