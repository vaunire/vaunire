from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group, User
from django.db import models
from django.urls import reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline
from unfold.contrib.filters.admin import RangeDateFilter, RelatedDropdownFilter
from unfold.contrib.forms.widgets import WysiwygWidget
from unfold.forms import (AdminPasswordChangeForm, UserChangeForm,
                          UserCreationForm)

from apps.accounts.models import Customer, Notifications
from apps.orders.models import Order

admin.site.unregister(User)
admin.site.unregister(Group)

@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm

@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    pass

class BaseAdmin(ModelAdmin):
    list_filter_submit = True
    formfield_overrides = {
        models.TextField: {"widget": WysiwygWidget},
    }

class OrdersInline(TabularInline):
    model = Order
    fields = ('order_number', 'divider', 'order', 'id', 'status', 'buying_type', 'created_at', 'cart_link', 'payment_status', 'order_amount')
    extra = 0

    def get_readonly_fields(self, request, obj=None):
        return self.fields 

    def has_add_permission(self, request, obj):
        return False 

    def order_number(self, obj):
        return obj.id
    order_number.short_description = 'ID'

    def divider(self, obj):
        return ":"
    divider.short_description = ''

    def order(self, obj):
        """Отображает ссылку на заказ"""
        url = reverse('admin:orders_order_change', args=[obj.id])
        return format_html('<a href="{}" style = "text-decoration: underline;">Нажмите, чтобы перейти</a>', url, obj.id)
    order.short_description = 'Заказ (ссылка)'

    def cart_link(self, obj):
        """Отображает ссылку на корзину заказа"""
        if obj.cart:
            url = reverse('admin:cart_cart_change', args = [obj.cart.id])
            return format_html('<a href="{}" style = "text-decoration: underline;">Нажмите, чтобы перейти</a>', url, obj.cart.id)
        return "-"
    cart_link.short_description = 'Корзина (ссылка)'

    def payment_status(self, obj):
        """Отображает статус оплаты заказа"""
        if obj.paid:
            return "Заказ оплачен"
        elif obj.payments.exists():
            payment = obj.payments.first()
            return payment.get_status_display() 
        return "Заказ не оплачен"
    payment_status.short_description = 'Статус оплаты'

    def order_amount(self, obj):
        """Отображает сумму заказа"""
        if obj.payments.exists():
            payment = obj.payments.first()
            return f"{payment.amount} ₽" 
        return "0.00 ₽"
    order_amount.short_description = 'Сумма'

@admin.register(Customer)
class CustomerAdmin(BaseAdmin):
    list_display = ('user', 'phone', 'email', 'is_active')
    search_fields = ('user__username', 'phone', 'email')
    list_filter = (
        'is_active',
        ('wishlist', RelatedDropdownFilter),
        ('favorite', RelatedDropdownFilter),
    )
    inlines = [OrdersInline]
    fieldsets = (
        ('Основная информация', {
            'fields': (
                'user',
                'is_active',
                'phone',
                'email',
                'address',
                'avatar',
            )
        }),
        ('Предпочтения', {
            'fields': (
                'wishlist',
                'favorite',
            ),
        }),
    )

@admin.register(Notifications)
class NotificationsAdmin(BaseAdmin):
    list_display = ('recipient', 'created_at', 'is_read')
    search_fields = ('recipient__user__username', 'text')
    list_filter = (
        'is_read',
        ('recipient', RelatedDropdownFilter),
        ('created_at', RangeDateFilter),
    )
    fieldsets = (
        ('Основная информация', {
            'fields': (
                'recipient',
                'created_at',
                'is_read',
            )
        }),
        ('Текст', {
            'fields': ('text',),
        }),
    )
    readonly_fields = ('created_at',)