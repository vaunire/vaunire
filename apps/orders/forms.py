from django import forms
from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import Order

User = get_user_model()

class OrderForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['order_date'].label = 'Дата получения заказа'
    
    order_date = forms.DateField(
        initial = timezone.now,
        widget = forms.DateTimeInput(attrs = {'type': 'datetime-local'})
    )

    class Meta:
        model = Order
        fields = (
            'first_name', 'last_name', 'phone', 'address', 'buying_type', 'order_date', 'comment'
        )