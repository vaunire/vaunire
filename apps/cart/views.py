from django import views
from django.contrib import messages
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.db.models import Prefetch
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe

from apps.accounts.mixins import NotificationsMixin
from apps.accounts.models import Customer
from apps.catalog.models import Album, PriceList, Style
from apps.catalog.views import annotate_prices
from apps.orders.forms import OrderForm
from apps.promotions.models import PromoCode

from .mixins import CartMixin
from .models import Cart, CartProduct


# ==========================================
# БЛОК 1: ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==========================================

def get_cached_pricelist():
    """ Получает активный прайс-лист """
    return cache.get_or_set(
        'active_pricelist',
        lambda: PriceList.objects.filter(is_active=True).first(),
        3600
    )

def prefetch_albums_for_products(products_list):
    """ Загружает альбомы с ценами """
    if not products_list:
        return

    album_ct = ContentType.objects.get_for_model(Album)
    
    # Сбор ID без запросов
    album_ids = {
        p.object_id for p in products_list 
        if p.content_type_id == album_ct.id
    }
            
    if not album_ids:
        return

    active_pricelist = get_cached_pricelist()
    
    optimized_albums_qs = Album.objects.filter(id__in=album_ids)
    optimized_albums_qs = annotate_prices(optimized_albums_qs, active_pricelist)
    optimized_albums_qs = optimized_albums_qs.select_related('artist', 'genre')
    optimized_albums_qs = optimized_albums_qs.prefetch_related(
        'image_gallery',
        Prefetch('styles', queryset=Style.objects.select_related('genre'))
    )

    albums_map = optimized_albums_qs.in_bulk()

    # Подмена объектов в памяти
    for product in products_list:
        if product.content_type_id == album_ct.id and product.object_id in albums_map:
            product.content_object = albums_map[product.object_id]


def optimize_cart_products(cart):
    """Применяет оптимизацию к объекту корзины"""
    if not cart:
        return
    
    # Вычисляем QS в список с подгрузкой ContentType
    products = list(cart.products.select_related('content_type').all())
    prefetch_albums_for_products(products)
    
    # Кладем обратно в кэш префетча Django
    cart.products._result_cache = products
    cart.products._prefetch_done = True


# ==========================================
# БЛОК 2: ПРОСМОТР И ОФОРМЛЕНИЕ
# ==========================================

class CartView(CartMixin, NotificationsMixin, views.View):
    """Отображает страницу корзины"""
    def get(self, request, *args, **kwargs):
        # Оптимизируем товары перед рендерингом
        optimize_cart_products(self.cart)

        if request.headers.get('HX-Request') == 'true' and request.GET.get('load_cart'):
            initial_data = {}
            if request.user.is_authenticated:
                try:
                    customer = Customer.objects.get(user=request.user)
                    initial_data = {
                        'first_name': customer.user.first_name or "",
                        'last_name': customer.user.last_name or "",
                        'phone': customer.phone,
                        'address': customer.address,
                    }
                except Customer.DoesNotExist:
                    initial_data = {
                        'first_name': request.user.first_name,
                        'last_name': request.user.last_name,
                    }
            
            form = OrderForm(initial=initial_data)

            context = {
                'cart': self.cart,
                'form': form, 
            }
            return render(request, 'cart/cart_content.html', context)

        context = {
            'cart': self.cart, 
            'notifications': self.notifications(request.user)
        }
        return render(request, 'cart/cart.html', context)


class CheckoutView(CartMixin, NotificationsMixin, views.View):
    """Отображает страницу оформления заказа"""
    def get(self, request, *args, **kwargs):
        optimize_cart_products(self.cart)

        initial_data = {}
        if request.user.is_authenticated:
            try:
                customer = Customer.objects.get(user = request.user)
                initial_data = {
                    'first_name': customer.user.first_name or customer.first_name,
                    'last_name': customer.user.last_name or customer.last_name,
                    'phone': customer.phone,
                    'address': customer.address,
                }
            except Customer.DoesNotExist:
                initial_data = {
                    'first_name': request.user.first_name,
                    'last_name': request.user.last_name,
                }

        form = OrderForm(initial = initial_data)
        context = {
            'cart': self.cart,
            'form': form,
            'notifications': self.notifications(request.user),
        }
        return render(request, 'cart/cart.html', context)


# ==========================================
# БЛОК 3: ДЕЙСТВИЯ С КОРЗИНОЙ
# ==========================================

class AddToCartView(CartMixin, views.View):
    """Добавляет товар в корзину"""
    def get(self, request, *args, **kwargs):
        ct_model, product_slug = kwargs.get('ct_model'), kwargs.get('slug')
        content_type = ContentType.objects.get(model=ct_model)
        product = content_type.model_class().objects.get(slug=product_slug)

        try:
            qty = int(request.GET.get('qty', 1))
        except (ValueError, TypeError):
            qty = 1
        
        cart_product, created = CartProduct.objects.get_or_create(
            user=self.cart.owner,
            cart=self.cart,
            content_type=content_type,
            object_id=product.id,
            defaults={'quantity': qty}
        )
        if not created:
            cart_product.quantity += qty
            cart_product.save() 
        
        self.cart.update_totals()
        self.cart.save()

        if request.headers.get('HX-Request') == 'true':
             return self.render_cart_response(request, product, request.headers.get('X-Source'))

        return HttpResponseRedirect(request.META['HTTP_REFERER'])


class RemoveFromCartView(CartMixin, views.View):
    """Удаляет товар из корзины"""
    def get(self, request, *args, **kwargs):
        ct_model, product_slug = kwargs.get('ct_model'), kwargs.get('slug')
        content_type = ContentType.objects.get(model=ct_model)
        product = content_type.model_class().objects.get(slug=product_slug)

        cart_product = CartProduct.objects.filter(
            user=self.cart.owner,
            cart=self.cart,
            content_type=content_type,
            object_id=product.id
        ).first()

        if cart_product:
            cart_product.delete()
            self.cart.update_totals()
            self.cart.save()
            self.cart.refresh_from_db()

        if request.headers.get('HX-Request') == 'true':
            return self.render_cart_response(request, product, request.headers.get('X-Source'))

        return HttpResponseRedirect(request.META['HTTP_REFERER'])


class ChangeQuantityView(CartMixin, views.View):
    """Изменяет количество (+/-) """
    def post(self, request, *args, **kwargs):
        ct_model, product_slug = kwargs.get('ct_model'), kwargs.get('slug')
        content_type = ContentType.objects.get(model=ct_model)
        product = content_type.model_class().objects.get(slug=product_slug)

        cart_product = CartProduct.objects.filter(
            user=self.cart.owner,
            cart=self.cart,
            content_type=content_type,
            object_id=product.id
        ).first()

        if cart_product:
            action = request.POST.get('action')
            if action == 'decrease':
                cart_product.quantity -= 1
            elif action == 'increase':
                cart_product.quantity += 1
            
            if cart_product.quantity < 1:
                cart_product.delete()
            else:
                cart_product.save()

            self.cart.update_totals()
            self.cart.save()

        if request.headers.get('HX-Request') == 'true':
            return self.render_cart_response(request, product, request.headers.get('X-Source'))

        return HttpResponseRedirect(request.META['HTTP_REFERER'])


class ClearCartView(CartMixin, views.View):
    """Очищает корзину пользователя"""
    def get(self, request, *args, **kwargs):
        CartProduct.objects.filter(cart = self.cart).delete()
        self.cart.applied_promocode = None 
        self.cart.update_totals()
        self.cart.save()
        return HttpResponseRedirect(request.META['HTTP_REFERER'])


class ApplyPromoCodeView(CartMixin, views.View):
    def post(self, request, *args, **kwargs):
        if not self.cart:
            messages.error(request, 'Корзина пуста.')
            return HttpResponseRedirect(reverse('cart'))

        code = request.POST.get('promo_code', '').strip()
        if not code:
            return HttpResponseRedirect(reverse('cart'))

        try:
            promocode = PromoCode.objects.get(code=code)
            
            optimize_cart_products(self.cart)

            current_cart_amount = sum(
                item.quantity * item.content_object.discounted_price 
                for item in self.cart.products.all()
            )

            # Проверка промокода
            success, message = promocode.check_applicability(current_cart_amount)

            if success:
                self.cart.applied_promocode = promocode
                self.cart.save() 
                messages.success(request, mark_safe(f'Промокод «<span class="font-bold">{promocode.code}</span>» применен!'))
            else:
                messages.error(request, message)

        except PromoCode.DoesNotExist:
            messages.error(request, 'Промокод не найден.')

        return HttpResponseRedirect(reverse('cart'))