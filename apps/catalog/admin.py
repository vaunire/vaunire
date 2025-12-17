from django.contrib import admin
from django.contrib.contenttypes.admin import GenericTabularInline
from django.db import models

from unfold.admin import ModelAdmin, TabularInline
from unfold.contrib.filters.admin import (
    MultipleRelatedDropdownFilter,  
    RangeDateFilter,              
    RelatedDropdownFilter          
)
from unfold.contrib.forms.widgets import WysiwygWidget

from .models import (Album, Artist, Genre, ImageGallery, MediaType, Member,
                     PriceList, PriceListItem, Style, Country, Label, PromoGroup)

class BaseAdmin(ModelAdmin):
    list_filter_submit = True 
    formfield_overrides = {
        models.TextField: {"widget": WysiwygWidget},  
    }

class PriceListItemInLine(TabularInline):
    model = PriceListItem
    fields = ('album', 'price')
    extra = 1

class MembersInLine(TabularInline):
    model = Artist.members.through  
    extra = 1 

class ImageGalleryInLine(GenericTabularInline):
    model = ImageGallery 
    readonly_fields = ('image_url',)  

@admin.register(MediaType)
class MediaTypeAdmin(BaseAdmin):
    list_display = ('name',)  
    search_fields = ('name',) 
    list_filter = ()  

@admin.register(Genre)
class GenreAdmin(BaseAdmin):
    list_display = ('name',)  
    search_fields = ('name',) 
    list_filter = () 

@admin.register(Style)
class StyleAdmin(BaseAdmin):
    list_display = ('name', 'genre')  
    search_fields = ('name', 'genre__name') 
    list_filter = (
        ('genre', RelatedDropdownFilter),  
    )

@admin.register(Country)
class CountryAdmin(BaseAdmin):
    list_display = ('name',)  
    search_fields = ('name',) 
    list_filter = ()  
    ordering = ('name',)  

@admin.register(Label)
class LabelAdmin(BaseAdmin):
    list_display = ('name', 'country', 'founded_year')  
    search_fields = ('name', 'country__name') 
    list_filter = (
        ('country', RelatedDropdownFilter),  
    )
    fieldsets = (
        ('Основная информация', {
            'fields': (
                'name',
                'country',
                'founded_year',
                'description',
                'slug',
            )
        }),
    )

@admin.register(Artist)
class ArtistAdmin(BaseAdmin):
    list_display = ('name', 'genre', 'country') 
    search_fields = ('name', 'genre__name') 
    list_filter = (
        ('genre', RelatedDropdownFilter), 
        ('country', RelatedDropdownFilter), 
        ('members', MultipleRelatedDropdownFilter), 
    )
    inlines = [MembersInLine, ImageGalleryInLine]
    exclude = ('members',)  

@admin.register(Member)
class MemberAdmin(BaseAdmin):
    list_display = ('__str__', 'birth_date', 'get_artists', 'role') 
    search_fields = ('first_name', 'last_name', 'artist__name') 
    list_filter = (
        ('artist', MultipleRelatedDropdownFilter),  
    )

    def get_artists(self, obj):
        through_model = Artist.members.through
        artist_members = through_model.objects.filter(member=obj)
        artists = Artist.objects.filter(id__in=artist_members.values('artist_id'))
        if artists:
            return ", ".join(artist.name for artist in artists)
        return "-"
    get_artists.short_description = 'Исполнитель/Группа' 


@admin.register(Album)
class AlbumAdmin(BaseAdmin):
    list_display = ('name', 'artist', 'release_date', 'get_current_price', 'stock', 'total_sold', 'has_autograph')  
    
    search_fields = ('name', 'artist__name', 'article')  
    readonly_fields = ('total_sold',)
    
    list_filter = (
        ('release_date', RangeDateFilter),
        ('artist', RelatedDropdownFilter), 
        ('genre', RelatedDropdownFilter),  
        ('media_type', RelatedDropdownFilter),  
        ('styles', MultipleRelatedDropdownFilter),  
        ('country', RelatedDropdownFilter),
        ('label', RelatedDropdownFilter),
        'condition',
        'has_autograph', 
        'package_type', 
        'is_explicit',  
        'out_of_stock', 
        'total_sold',
        'offer_of_the_week',  
    )
    inlines = [ImageGalleryInLine]

    fieldsets = (
        ('Основная информация', {
            'fields': (
                'name',
                'artist',
                'release_date',
                'label',
                'country',
                'media_type',
                'is_explicit', 
                'has_autograph', 
            )
        }),
        ('Жанр и стили', {
            'fields': (
                'genre',
                'styles',
            )
        }),
        ('Формат альбома', {
            'fields': (
                'format_type',
                'format_color',
                'format_edition',
                'format_quantity',
                'package_type', 
            )
        }),
        ('Физические характеристики', {
            'fields': (
                'weight',
                ('width', 'height', 'depth'), 
            )
        }),
        ('Описание и треклист', {
            'fields': (
                'description',
                'tracklist',
            )
        }),
        ('Наличие', {
            'fields': (
                'condition',
                'stock',
                'offer_of_the_week', 
                'total_sold',
            )
        }),
        ('Дополнительная информация', {
            'fields': (
                'article',
                'image',
                'slug',
            )
        }),
    )

    def get_current_price(self, obj):
        return obj.current_price
    get_current_price.short_description = 'Текущая цена'

@admin.register(PriceList)
class PriceListAdmin(BaseAdmin):
    list_display = ('number', 'start_date', 'end_date', 'is_active')  
    search_fields = ('number',)  
    list_filter = (
        'is_active',
        ('start_date', RangeDateFilter),
    )
    inlines = [PriceListItemInLine]


@admin.register(PriceListItem)
class PriceListItemAdmin(BaseAdmin):
    list_display = ('album', 'price_list', 'price')
    search_fields = ('album__name', 'price_list__number')  
    list_filter = (
        ('price_list', RelatedDropdownFilter),
        ('album__artist', RelatedDropdownFilter),
    )
    fieldsets = (
        ('Основная информация', {
            'fields': (
                'price_list',
                'album',
                'price',
            )
        }),
    )

@admin.register(ImageGallery)
class ImageGalleryAdmin(BaseAdmin):
    list_display = ('content_object', 'use_in_slider')  
    list_filter = ('use_in_slider',)

@admin.register(PromoGroup)
class PromoGroupAdmin(BaseAdmin):
    list_display = ('name', 'slug')
    search_fields = ('name', 'slug')
    inlines = [ImageGalleryInLine]