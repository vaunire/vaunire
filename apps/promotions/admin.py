from django.contrib import admin
from django.db import models
from unfold.admin import ModelAdmin, TabularInline
from unfold.contrib.filters.admin import RangeDateFilter
from unfold.contrib.forms.widgets import WysiwygWidget

from .models import PromoCode, Promotion


class BaseAdmin(ModelAdmin):
    list_filter_submit = True
    formfield_overrides = {
        models.TextField: {"widget": WysiwygWidget},
    }

class PromotionAlbumInline(TabularInline):
    model = Promotion.albums.through
    fields = ('album',)
    extra = 1


@admin.register(Promotion)
class PromotionAdmin(BaseAdmin):
    list_display = ('name', 'discount_percentage', 'start_date', 'end_date', 'is_active')
    search_fields = ('name', 'description')
    list_filter = (
        'is_active',
        ('start_date', RangeDateFilter),
        ('end_date', RangeDateFilter),
    )
    inlines = [PromotionAlbumInline]
    fieldsets = (
        ('Основная информация', {
            'fields': (
                'name',
                'description',
                'discount_percentage',
                'is_active',
            )
        }),
        ('Даты акции', {
            'fields': (
                'start_date',
                'end_date',
            )
        }),
    )

@admin.register(PromoCode)
class PromoCodeAdmin(BaseAdmin):
    list_display = ('code', 'discount_amount', 'valid_from', 'valid_until', 'is_active', 'times_used')
    search_fields = ('code',)
    list_filter = (
        'is_active',
        ('valid_from', RangeDateFilter),
        ('valid_until', RangeDateFilter),
    )
    fieldsets = (
        ('Основная информация', {
            'fields': (
                'code',
                'discount_amount',
                'is_active',
                'min_purchase_amount',
            )
        }),
        ('Ограничения', {
            'fields': (
                'valid_from',
                'valid_until',
                'max_uses',
                'times_used',
            )
        }),
    )
    readonly_fields = ('times_used',)