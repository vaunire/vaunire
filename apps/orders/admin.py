from django.contrib import admin
from django.db import models
from unfold.admin import ModelAdmin, TabularInline
from unfold.contrib.filters.admin import (ChoicesDropdownFilter,
                                          RangeDateFilter,
                                          RelatedDropdownFilter)
from unfold.contrib.forms.widgets import WysiwygWidget

from .models import Order, Payment, ReturnRequest


class BaseAdmin(ModelAdmin):
    list_filter_submit = True
    formfield_overrides = {
        models.TextField: {"widget": WysiwygWidget},
    }

class PaymentInline(TabularInline):
    model = Payment
    fields = ('payment_id', 'divider', 'status', 'payment_method', 'amount', 'payment_date')
    readonly_fields = ('divider', )
    extra = 0

    def divider(self, obj):
        return ":"
    divider.short_description = ''

@admin.register(Order)
class OrderAdmin(BaseAdmin):
    list_display = ('id', 'customer', 'created_at', 'status', 'buying_type', 'paid')
    search_fields = ('customer__user__username', 'phone', 'email', 'address')
    list_filter = (
        ('status', ChoicesDropdownFilter),
        ('buying_type', ChoicesDropdownFilter),
        'paid',
        ('customer', RelatedDropdownFilter),
        ('created_at', RangeDateFilter),
        ('order_date', RangeDateFilter),
    )
    inlines = [PaymentInline]
    fieldsets = (
        ('Основная информация', {
            'fields': (
                'customer',
                'cart',
                'status',
                'buying_type',
                'paid',  
            )
        }),
        ('Данные клиента', {
            'fields': (
                'first_name',
                'last_name',
                'phone',
                'email',
                'address',
            )
        }),
        ('Даты', {
            'fields': (
                'created_at',
                'order_date',
            ),
            'classes': ('collapse',),
        }),
        ('Комментарий', {
            'fields': ('comment',),
        }),
    )
    readonly_fields = ('created_at',)

@admin.register(Payment)
class PaymentAdmin(BaseAdmin):
    list_display = ('get_short_payment_id', 'order', 'amount', 'payment_date', 'status', 'payment_method')
    search_fields = ('payment_id', 'order__id', 'payment_method')
    list_filter = (
        ('status', ChoicesDropdownFilter),
        ('order', RelatedDropdownFilter),
        ('payment_date', RangeDateFilter),
    )
    fieldsets = (
        ('Основная информация', {
            'fields': (
                'order',
                'amount',
                'status',
            )
        }),
        ('Детали платежа', {
            'fields': (
                'payment_id',
                'payment_date',
                'payment_method',
            )
        }),
    )

    def get_short_payment_id(self, obj):
        if obj.payment_id:
            return f"{obj.payment_id[:25]}...{obj.payment_id[-4:]}"
        return "-"
    get_short_payment_id.short_description = 'ID платежа'

@admin.register(ReturnRequest)
class ReturnRequestAdmin(BaseAdmin):
    list_display = ('order', 'get_customer_username', 'status', 'reason', 'created_at')
    list_filter = (
        ('status', ChoicesDropdownFilter),
        ('reason', ChoicesDropdownFilter),
        ('created_at', RangeDateFilter),
    )
    search_fields = ('order__id', 'customer__user__username', 'details')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('Основная информация', {
            'fields': (
                'customer',
                'order',
                'status',
                'reason',
            )
        }),
        ('Детали', {
            'fields': (
                'products',
                'details',
                'file',
            )
        }),
        ('Даты', {
            'fields': (
                'created_at',
                'updated_at',
            ),
            'classes': ('collapse',),
        }),
    )

    def get_customer_username(self, obj):
        return obj.customer.user.username
    get_customer_username.short_description = 'Покупатель'