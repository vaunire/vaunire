from typing import List

from django.contrib.contenttypes.models import ContentType
from django.db.models import Case, DecimalField, F, OuterRef, Prefetch, Subquery, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.promotions.models import Promotion
from .models import Album, PriceList, PriceListItem, Style


def get_visible_styles(album: Album, max_total_width_px: int = 180,) -> List[Style]:
    """
    Умный выбор 0–2 стилей для карточки альбома.

    Делает так, чтобы второй стиль гарантированно влезал целиком и без переноса.
    Если второй стиль «вылезает» — он вообще не показывается, сразу показываем +N.
    """

    PX_PER_CHAR = 6
    CHIP_PADDING = 16
    GAP_BETWEEN_CHIPS = 1  
    PLUS_CHIP_WIDTH = 1    

    try:
        all_styles = list(album.styles.all())
    except:
        all_styles = list(album.styles.all()[:12])

    if not all_styles:
        return []

    # Сначала короткие — шанс влезть выше
    all_styles.sort(key=lambda s: len(s.name))

    selected: List[Style] = []
    used_width = 0

    for style in all_styles:
        chip_width = len(style.name) * PX_PER_CHAR + CHIP_PADDING

        # Сколько места потребуется с учётом уже выбранных
        needed = used_width + chip_width
        if selected:
            needed += GAP_BETWEEN_CHIPS

        # Если это второй стиль — прибавляем место под будущий "+N"
        if len(selected) == 1:
            needed += GAP_BETWEEN_CHIPS + PLUS_CHIP_WIDTH

        if needed <= max_total_width_px:
            selected.append(style)
            used_width += chip_width + (GAP_BETWEEN_CHIPS if selected else 0)
        else:
            break

    return selected


def get_active_pricelist():
    """Получает активный прайс-лист"""
    return PriceList.objects.filter(is_active=True).first()


def annotate_prices(queryset, active_pricelist=None):
    """
    Аннотирует QuerySet ценами и скидками.
    Если active_pricelist не передан, попробуем получить его сами.
    """
    if active_pricelist is None:
        active_pricelist = get_active_pricelist()

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


def prefetch_albums_for_products(products_list):
    """
    Загружает альбомы с ценами для списка продуктов (например, из корзины).
    """
    if not products_list:
        return

    album_ct = ContentType.objects.get_for_model(Album)
    
    # Сбор ID альбомов из списка продуктов
    album_ids = {
        p.object_id for p in products_list 
        if p.content_type_id == album_ct.id
    }
            
    if not album_ids:
        return

    # Загружаем альбомы с аннотацией цен
    active_pricelist = get_active_pricelist()
    optimized_albums_qs = Album.objects.filter(id__in=album_ids)
    optimized_albums_qs = annotate_prices(optimized_albums_qs, active_pricelist)
    
    # Подгружаем связанные данные
    optimized_albums_qs = optimized_albums_qs.select_related('artist', 'genre')
    optimized_albums_qs = optimized_albums_qs.prefetch_related(
        'image_gallery',
        Prefetch('styles', queryset=Style.objects.select_related('genre'))
    )

    albums_map = optimized_albums_qs.in_bulk()

    # Подменяем объекты content_object в исходном списке products_list
    for product in products_list:
        if product.content_type_id == album_ct.id and product.object_id in albums_map:
            product.content_object = albums_map[product.object_id]


def optimize_cart_products(cart):
    """
    Применяет оптимизацию (префетч альбомов и цен) к объекту корзины.
    """
    if not cart:
        return
    
    # Получаем все продукты корзины
    products = list(cart.products.select_related('content_type').all())
    
    # Подгружаем для них данные альбомов
    prefetch_albums_for_products(products)
    
    cart.products._result_cache = products
    cart.products._prefetch_done = True