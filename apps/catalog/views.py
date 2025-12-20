from decimal import Decimal, InvalidOperation

from django import views
from django.views.generic import TemplateView
from django.contrib.contenttypes.models import ContentType
from django.core.paginator import Paginator
from django.db.models import Max, Min, Prefetch, Q
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from apps.accounts.mixins import NotificationsMixin
from apps.cart.mixins import CartMixin
from apps.cart.models import CartProduct

from .models import Album, Artist, Genre, PromoGroup, Style
from .utils import get_active_pricelist, annotate_prices, get_visible_styles


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


# ==========================================
# БЛОК 2: КАТАЛОГ (BaseView)
# ==========================================

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
        active_pricelist = get_active_pricelist()
        
        # Получаем базовый QS с ценами
        qs = annotate_prices(Album.objects.all(), active_pricelist)

        # Агрегация статистики (без кэша, для упрощения и актуальности)
        # Если нужна производительность, можно вернуть cache.get_or_set сюда
        global_stats = qs.aggregate(
            min_price=Min('annotated_discounted_price'),
            max_price=Max('annotated_discounted_price'),
            min_year=Min('release_date__year'),
            max_year=Max('release_date__year')
        )
        
        defaults = {
            'min_price': int(global_stats['min_price'] or 0),
            'max_price': int(global_stats['max_price'] or 10000),
            'min_year': int(global_stats['min_year'] or 1900),
            'max_year': int(global_stats['max_year'] or timezone.now().year)
        }

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

        ordering_map = {
            'price_desc': '-annotated_discounted_price',
            'price_asc': 'annotated_discounted_price',
            'name_asc': 'name',
            'name_desc': '-name',
        }
        qs = qs.order_by(ordering_map.get(filters['sort'], '-id'))

        paginator = Paginator(qs, filters['per_page'])
        page_obj = paginator.get_page(request.GET.get('page'))

        page_obj.object_list = page_obj.object_list.select_related(
            'artist', 'genre', 'media_type'
        ).prefetch_related(
            Prefetch('styles', queryset=Style.objects.select_related('genre')),
            'image_gallery',
        )

        # Вычисляем стили для отображения
        for album in page_obj:
            album.visible_styles = get_visible_styles(album)
            all_styles_len = len(album.styles.all())
            album.remaining_styles_count = max(0, all_styles_len - len(album.visible_styles))

        page_album_ids = [album.id for album in page_obj]

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

        favorite_album_ids = set()
        wishlist_album_ids = set()  

        if request.user.is_authenticated:
            customer = getattr(request.user, 'customer', None)
            if customer:
                favorite_album_ids = set(
                    customer.favorite.filter(id__in=page_album_ids)
                    .values_list('id', flat=True)
                )
                wishlist_album_ids = set(
                    customer.wishlist.filter(id__in=page_album_ids)
                    .values_list('id', flat=True)
                )

        is_htmx = request.headers.get('HX-Request')
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

        # Используем обычные запросы вместо кэша для жанров и стилей
        genres = list(Genre.objects.all())
        styles = list(Style.objects.select_related('genre').all())

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
            'wishlist_album_ids': wishlist_album_ids,
        }

        template = 'catalog/sections/content.html' if is_htmx else 'core/base.html'
        return render(request, template, context)


# ==========================================
# БЛОК 3: ДЕТАЛЬНЫЕ СТРАНИЦЫ
# ==========================================

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
        # Аннотируем цены
        qs = annotate_prices(qs)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        album = self.object
        request = self.request

        album.visible_styles = get_visible_styles(album)
        all_styles_len = len(album.styles.all())
        album.remaining_styles_count = max(0, all_styles_len - len(album.visible_styles))

        recently_viewed_ids = request.session.get('recently_viewed', [])
        recently_viewed_albums = []
        
        if recently_viewed_ids:
            ids_to_fetch = [id for id in recently_viewed_ids if id != album.id][:15]
            
            if ids_to_fetch:
                recently_rec_qs = Album.objects.filter(id__in=ids_to_fetch)\
                    .select_related('artist', 'genre', 'media_type')\
                    .prefetch_related('image_gallery', 'styles__genre')
                
                # Используем хелпер для цен, без явного получения pricelist
                recently_rec_qs = annotate_prices(recently_rec_qs)

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

        cart_item = None
        cart_album_ids = set()

        if self.cart:
            cart_products = context.get('cart_products', self.cart.products.all())
            
            album_ct = ContentType.objects.get_for_model(Album)
            
            for cp in cart_products:
                if cp.content_type_id == album_ct.id:
                    if cp.object_id == album.id:
                        cart_item = cp
                    cart_album_ids.add(cp.object_id)
        
        context['cart_item'] = cart_item
        context['cart_album_ids'] = cart_album_ids

        # 3. Избранное и Вишлист
        is_in_favorite = False
        is_in_wishlist = False
        favorite_album_ids = set()
        wishlist_album_ids = set()

        if request.user.is_authenticated:
            customer = getattr(request.user, 'customer', None)
            if customer:
                is_in_favorite = customer.favorite.filter(pk=album.pk).exists()
                is_in_wishlist = customer.wishlist.filter(pk=album.pk).exists()
                
                all_ids = [album.id] + [a.id for a in context.get('recently_viewed_albums', [])]
                favorite_album_ids = set(customer.favorite.filter(id__in=all_ids).values_list('id', flat=True))
                wishlist_album_ids = set(customer.wishlist.filter(id__in=all_ids).values_list('id', flat=True))

        context['is_in_favorite'] = is_in_favorite
        context['is_in_wishlist'] = is_in_wishlist
        context['favorite_album_ids'] = favorite_album_ids
        context['wishlist_album_ids'] = wishlist_album_ids
        
        return context
    
class OfferView(TemplateView):
    template_name = 'core/footer/components/offer.html'

class PrivacyPolicyView(TemplateView):
    template_name = 'core/footer/components/privacy_policy.html'

class CookiesView(TemplateView):
    template_name = 'core/footer/components/cookies.html'