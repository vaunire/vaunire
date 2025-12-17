from django.contrib import admin
from django.db import models
from django.db.models import F, Window
from django.db.models.functions import RowNumber
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline
from unfold.contrib.filters.admin import RelatedDropdownFilter
from unfold.contrib.forms.widgets import WysiwygWidget

from .models import Cart, CartProduct


class BaseAdmin(ModelAdmin):
    list_filter_submit = True  
    formfield_overrides = {
        models.TextField: {"widget": WysiwygWidget},  
    }

class CartProductInline(TabularInline):
    model = CartProduct
    fields = ('item_number', 'divider', 'display_name', 'album_link', 'original_price', 'price_list_link', 'discount_info', 'quantity', 'final_price_custom')
    readonly_fields = ('price_list_link', 'album_link', 'display_name', 'divider', 'item_number', 'original_price', 'discount_info', 'final_price_custom')  
    extra = 0

    def divider(self, obj):
        return ":"
    divider.short_description = ''

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(
            row_number=Window(
                expression=RowNumber(),
                order_by=F('id').asc() 
            )
        )

    def item_number(self, obj):
        if not obj.pk:
            return "-"
        return getattr(obj, 'row_number', '?')
    item_number.short_description = '№' 

    def display_name(self, obj):
        return obj.display_name
    display_name.short_description = 'Товар'

    def album_link(self, obj):
        """Отображает ссылку на сам Альбом (content_object)"""
        if obj.content_object and obj.content_type.model == 'album':
            url = reverse('admin:catalog_album_change', args=[obj.content_object.id])
            return format_html('<a href="{}" style="text-decoration: underline;">Нажмите, чтобы перейти</a>', url)
        return "-"
    album_link.short_description = 'Товар (ссылка)'

    def price_list_link(self, obj):
        """Отображает ссылку на активный прайс-лист, связанный с альбомом"""
        if obj.content_object and obj.content_type.model == 'album':
            price_list_item = obj.content_object.items.filter(price_list__is_active=True).first()
            if price_list_item:
                url = reverse('admin:catalog_pricelist_change', args=[price_list_item.price_list.id])
                return format_html('<a href="{}" style="text-decoration: underline;">Нажмите, чтобы перейти</a>', url)
        return "-"  
    price_list_link.short_description = 'Прайс - лист'


    def original_price(self, obj):
        """Возвращает оригинальную цену альбома из активного прайс-листа"""
        if obj.content_object and obj.content_type.model == 'album':
            price_list_item = obj.content_object.items.filter(price_list__is_active=True).first()
            if price_list_item:
                return f"{price_list_item.price:.2f}"
        return "-"
    original_price.short_description = 'Цена за ед.'

    def discount_info(self, obj):
        """Ищет активную акцию. Выводит просто цифру с процентом (10%)"""
        if not (obj.content_object and obj.content_type.model == 'album'):
            return "0%"
        
        album = obj.content_object
        now = timezone.now()
        
        active_promos = album.promotions.filter(
            is_active=True,
            start_date__lte=now,
            end_date__gte=now
        ).order_by('-discount_percentage')

        if active_promos.exists():
            promo = active_promos.first()
            return f"{promo.discount_percentage:.0f}%"
        
        return "0%"
    discount_info.short_description = 'Скидка'

    def final_price_custom(self, obj):
        return obj.final_price
    final_price_custom.short_description = 'Финальная цена'

@admin.register(Cart)
class CartAdmin(BaseAdmin):
    list_display = ('id', 'owner', 'total_products', 'final_price', 'in_order')
    search_fields = ('id', 'owner__user__username') 
    list_filter = (
        ('owner', RelatedDropdownFilter), 
        'in_order',  
    )
    inlines = [CartProductInline]
    fieldsets = (
        ('Основная информация', {
            'fields': (
                'owner',
                'in_order',
            )
        }),
        ('Итоги', {
            'fields': (
                'total_products',
                'final_price',
            ),
            'classes': ('collapse',),
        }),
    )
    readonly_fields = ('total_products', 'final_price')

    def total_products(self, obj):
        return obj.total_products
    total_products.short_description = 'Количество товаров'

    def final_price(self, obj):
        return f"{obj.final_price} ₽"
    final_price.short_description = 'Итоговая цена'

@admin.register(CartProduct)
class CartProductAdmin(BaseAdmin):
    list_display = ('display_name', 'cart', 'quantity', 'final_price')
    search_fields = ('cart__id',)  
    list_filter = (
        ('cart', RelatedDropdownFilter),
        ('user', RelatedDropdownFilter),
    )
    fieldsets = (
        ('Основная информация', {
            'fields': (
                'user',
                'cart',
                'content_type',
                'object_id',
            )
        }),
        ('Детали', {
            'fields': (
                'quantity',
                'final_price',
            )
        }),
    )
    readonly_fields = ('final_price',)  

    def display_name(self, obj):
        return obj.display_name
    display_name.short_description = 'Продукт'