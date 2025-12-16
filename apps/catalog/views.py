from decimal import Decimal, InvalidOperation

from django import views
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import (Case, DecimalField, F, Max, Min, OuterRef,
                              Prefetch, Q, Subquery, Value, When)
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from apps.accounts.mixins import NotificationsMixin
from apps.cart.mixins import CartMixin
from apps.cart.models import CartProduct
from apps.promotions.models import Promotion

from .models import (Album, Artist, Genre, PriceList, PriceListItem,
                     PromoGroup, Style)
from .utils import get_visible_styles


def search_view(request):
    query = request.GET.get('q', '').strip()
    if not query:
        return HttpResponse('')

    albums = Album.objects.filter(
        Q(name__icontains=query) | Q(artist__name__icontains=query)
    ).select_related('artist').prefetch_related('image_gallery')[:5]
    
    artists = Artist.objects.filter(
        name__icontains=query
    ).prefetch_related('image_gallery')[:5]

    return render(request, 'core/navbar/components/search_results.html', {
        'albums': albums,
        'artists': artists,
        'query': query
    })


def annotate_prices(queryset, active_pricelist):
    if not active_pricelist:
        return queryset.annotate(
            annotated_current_price=Value(0, output_field=DecimalField()),
            annotated_discounted_price=Value(0, output_field=DecimalField()),
            annotated_discount_percentage=Value(0, output_field=DecimalField())
        )
    
    price_subquery = PriceListItem.objects.filter(
        album_id=OuterRef('pk'),
        price_list=active_pricelist
    ).values('price')[:1]

    discount_subquery = Promotion.objects.filter(
        albums=OuterRef('pk'),
        is_active=True,
        start_date__lte=timezone.now(),
        end_date__gte=timezone.now()
    ).order_by('-discount_percentage').values('discount_percentage')[:1] 

    return queryset.annotate(
        annotated_current_price=Coalesce(
            Subquery(price_subquery, output_field=DecimalField()), 
            Value(0, output_field=DecimalField())
        ),
        annotated_discount_percentage=Subquery(discount_subquery, output_field=DecimalField()),
        annotated_discounted_price=Case(
            When(annotated_discount_percentage__isnull=False,
                 then=F('annotated_current_price') * (1 - F('annotated_discount_percentage') / 100.0)),
            default=F('annotated_current_price'),
            output_field=DecimalField()
        )
    )


class BaseView(CartMixin, NotificationsMixin, views.View):
    def get_param(self, request, param, default=None, cast_type=str):
        val = request.GET.get(param)
        if val in [None, '', 'all']:
            return default
        try:
            if cast_type == Decimal and isinstance(val, str):
                val = val.replace(',', '.')
            return cast_type(val)
        except (ValueError, TypeError, InvalidOperation):
            return default

    def get(self, request, *args, **kwargs):
        # 1. Кэширование прайс-листа
        active_pricelist = cache.get_or_set(
            'active_pricelist',
            lambda: PriceList.objects.filter(is_active=True).first(),
            3600
        )
        
        # 2. Базовый QuerySet с ценами
        qs = annotate_prices(Album.objects.all(), active_pricelist)

        # 3. Кэширование статистики (Min/Max)
        global_stats = cache.get('album_global_stats')
        if global_stats is None:
            global_stats = qs.aggregate(
                min_price=Min('annotated_discounted_price'),
                max_price=Max('annotated_discounted_price'),
                min_year=Min('release_date__year'),
                max_year=Max('release_date__year')
            )
            cache.set('album_global_stats', global_stats, 3600)
        
        defaults = {
            'min_price': int(global_stats['min_price'] or 0),
            'max_price': int(global_stats['max_price'] or 10000),
            'min_year': int(global_stats['min_year'] or 1900),
            'max_year': int(global_stats['max_year'] or timezone.now().year)
        }

        # 4. Фильтры
        filters = {
            'media_type': self.get_param(request, 'media_type', cast_type=int),
            'min_price': self.get_param(request, 'min_price', defaults['min_price'], Decimal),
            'max_price': self.get_param(request, 'max_price', defaults['max_price'], Decimal),
            'min_year': self.get_param(request, 'min_year', defaults['min_year'], int),
            'max_year': self.get_param(request, 'max_year', defaults['max_year'], int),
            'genres': request.GET.getlist('genres'),
            'styles': request.GET.getlist('styles'),
            'in_stock': request.GET.get('in_stock') == '1',
            'offer_of_the_week': request.GET.get('offer_of_the_week') == '1',
            'sort': request.GET.get('sort', ''),
            'per_page': self.get_param(request, 'per_page', 8, int),
            'view_type': request.GET.get('view', 'grid')
        }

        if filters['media_type']:
            qs = qs.filter(media_type__id=filters['media_type'])
        if filters['min_price'] > defaults['min_price']:
            qs = qs.filter(annotated_discounted_price__gte=filters['min_price'])
        if filters['max_price'] < defaults['max_price']:
            qs = qs.filter(annotated_discounted_price__lte=filters['max_price'])
        if filters['min_year'] > defaults['min_year']:
            qs = qs.filter(release_date__year__gte=filters['min_year'])
        if filters['max_year'] < defaults['max_year']:
            qs = qs.filter(release_date__year__lte=filters['max_year'])
        if filters['genres']:
            qs = qs.filter(genre__id__in=filters['genres'])
        if filters['styles']:
            qs = qs.filter(styles__id__in=filters['styles']).distinct()
        if filters['in_stock']:
            qs = qs.filter(stock__gt=0)
        if filters['offer_of_the_week']:
            qs = qs.filter(offer_of_the_week=True)

        # 5. Сортировка
        ordering_map = {
            'price_desc': '-annotated_discounted_price',
            'price_asc': 'annotated_discounted_price',
            'name_asc': 'name',
            'name_desc': '-name',
        }
        qs = qs.order_by(ordering_map.get(filters['sort'], '-id'))

        # 6. Пагинация и выборка
        paginator = Paginator(qs, filters['per_page'])
        page_obj = paginator.get_page(request.GET.get('page'))

        # Оптимизация запросов для текущей страницы
        page_obj.object_list = page_obj.object_list.select_related(
            'artist', 'genre', 'media_type'
        ).prefetch_related(
            Prefetch('styles', queryset=Style.objects.select_related('genre')),
            'image_gallery',
        )

        for album in page_obj:
            album.visible_styles = get_visible_styles(album)
            all_styles_len = len(album.styles.all())
            album.remaining_styles_count = max(0, all_styles_len - len(album.visible_styles))

        page_album_ids = [album.id for album in page_obj]

        # 1. Быстрая проверка корзины (через ContentType, так как связь универсальная)
        cart_album_ids = set()
        if self.cart:
            album_ct = ContentType.objects.get_for_model(Album)
            
            cart_album_ids = set(
                CartProduct.objects.filter(
                    cart=self.cart, 
                    content_type=album_ct,      
                    object_id__in=page_album_ids 
                ).values_list('object_id', flat=True)
            )

        # 2. Быстрая проверка избранного
        favorite_album_ids = set()
        if request.user.is_authenticated:
            customer = getattr(request.user, 'customer', None)
            if customer:
                favorite_album_ids = set(
                    customer.favorite.filter(id__in=page_album_ids)
                    .values_list('id', flat=True)
                )

        is_htmx = request.headers.get('HX-Request')
        
        # Ленивая загрузка
        month_bestseller = None
        offer_of_the_week_album = None
        slides = []

        if not is_htmx or request.headers.get('HX-Target') != 'catalog-content':
             bestseller_qs = Album.objects.exclude(total_sold=0)
             month_bestseller = annotate_prices(bestseller_qs, active_pricelist)\
                .select_related('artist', 'genre')\
                .prefetch_related('styles', 'image_gallery')\
                .order_by('-total_sold').first()
             
             if month_bestseller:
                 month_bestseller.visible_styles = get_visible_styles(month_bestseller)
                 all_styles_len = len(month_bestseller.styles.all())
                 month_bestseller.remaining_styles_count = max(0, all_styles_len - len(month_bestseller.visible_styles))
            
             offer_qs = Album.objects.filter(offer_of_the_week=True)
             offer_of_the_week_album = annotate_prices(offer_qs, active_pricelist)\
                .select_related('artist', 'genre')\
                .prefetch_related('styles', 'image_gallery').first()

             try:
                 slides = PromoGroup.objects.get(slug='home_main').get_images().filter(use_in_slider=True)
             except PromoGroup.DoesNotExist:
                 pass

        genres = cache.get_or_set('all_genres', lambda: list(Genre.objects.all()), 3600)
        styles = cache.get_or_set('all_styles', lambda: list(Style.objects.select_related('genre').all()), 3600)

        context = {
            'page_obj': page_obj,
            'albums': page_obj, 
            'paginator': paginator,
            'genres': genres,
            'styles': styles,
            'filters': filters,
            'defaults': defaults,
            'view_type': filters['view_type'],
            'sort_label': {
                '': 'Сначала новые',
                'price_desc': 'По убыванию цены',
                'price_asc': 'По возрастанию цены'
            }.get(filters['sort'], 'Сначала новые'),
            'slides': slides,
            'month_bestseller': month_bestseller,
            'offer_of_the_week_album': offer_of_the_week_album,
            'cart': self.cart,
            'notifications': self.notifications(request.user),
            
            'cart_album_ids': cart_album_ids,
            'favorite_album_ids': favorite_album_ids,
        }

        template = 'catalog/sections/content.html' if is_htmx else 'core/base.html'
        return render(request, template, context)
        

class ArtistDetailView(CartMixin, views.generic.DetailView, NotificationsMixin):
    model = Artist
    template_name = 'artist/artist.html'
    slug_url_kwarg = 'artist_slug'
    context_object_name = 'artist'

class AlbumDetailView(CartMixin, views.generic.DetailView, NotificationsMixin):
    model = Album
    template_name = 'album/album.html'
    slug_url_kwarg = 'album_slug'
    context_object_name = 'album'

    def get_queryset(self):
        qs = super().get_queryset()
        qs = qs.select_related('artist', 'genre', 'label', 'country', 'media_type')
        qs = qs.prefetch_related(
            Prefetch('styles', queryset=Style.objects.select_related('genre')),
            'image_gallery'
        )
        
        active_pricelist = cache.get_or_set(
            'active_pricelist',
            lambda: PriceList.objects.filter(is_active=True).first(),
            3600
        )
        qs = annotate_prices(qs, active_pricelist)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        album = self.object
        request = self.request

        album.visible_styles = get_visible_styles(album)
        all_styles_len = len(album.styles.all())
        album.remaining_styles_count = max(0, all_styles_len - len(album.visible_styles))

        cart_item = None
        if self.cart:
            cart_products = context.get('cart_products', [])
            
            album_model_name = Album._meta.model_name
            for cp in cart_products:
                if cp.content_type.model == album_model_name and cp.object_id == album.id:
                    cart_item = cp
                    break
        
        context['cart_item'] = cart_item
        context['is_in_cart'] = cart_item is not None

        is_in_favorite = False
        is_in_wishlist = False
        
        if request.user.is_authenticated:
            customer = getattr(request.user, 'customer', None)
            if customer:
                is_in_favorite = customer.favorite.filter(pk=album.pk).exists()
                is_in_wishlist = customer.wishlist.filter(pk=album.pk).exists()

        context['is_in_favorite'] = is_in_favorite
        context['is_in_wishlist'] = is_in_wishlist

        recently_viewed_ids = request.session.get('recently_viewed', [])
        
        recently_viewed_albums = []
        if recently_viewed_ids:
            ids_to_fetch = [id for id in recently_viewed_ids if id != album.id][:15]
            
            if ids_to_fetch:
                recently_rec_qs = Album.objects.filter(id__in=ids_to_fetch).select_related('artist', 'genre', 'media_type').prefetch_related('image_gallery', 'styles__genre')
                
                active_pricelist = PriceList.objects.filter(is_active=True).first()
                recently_rec_qs = annotate_prices(recently_rec_qs, active_pricelist)

                recently_viewed_albums = list(recently_rec_qs)
                recently_viewed_albums.sort(key=lambda x: ids_to_fetch.index(x.id))

                for r_album in recently_viewed_albums:
                     r_album.visible_styles = get_visible_styles(r_album)
                     r_album.remaining_styles_count = max(0, r_album.styles.count() - len(r_album.visible_styles))
        
        context['recently_viewed_albums'] = recently_viewed_albums

        if album.id in recently_viewed_ids:
            recently_viewed_ids.remove(album.id)
        
        recently_viewed_ids.insert(0, album.id)
        
        recently_viewed_ids = recently_viewed_ids[:10]
        
        request.session['recently_viewed'] = recently_viewed_ids
        request.session.modified = True

        return context
