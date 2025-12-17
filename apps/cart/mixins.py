from django import views
from django.shortcuts import render, HttpResponse
from django.template.loader import render_to_string
from django.contrib.contenttypes.models import ContentType
from django.views.generic.base import ContextMixin

from .models import Cart, CartProduct
from apps.accounts.models import Customer

class CartMixin(ContextMixin, views.View):
    def dispatch(self, request, *args, **kwargs):
        """ Инициализация корзины пользователя """
        cart = None
        if request.user.is_authenticated:
            customer, created = Customer.objects.get_or_create(
                user=request.user,
                defaults={'phone': '', 'email': request.user.email or ''}
            )
            cart = Cart.objects.filter(owner=customer, in_order=False).first()
            if not cart:
                try:
                    cart = Cart.objects.create(owner=customer)
                except Exception:
                    cart = Cart.objects.filter(owner=customer).last()
        
        self.cart = cart
        if request.user.is_authenticated and 'customer' in locals():
             request.user.customer = customer
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['cart'] = self.cart
        if self.cart:
            context['cart_products'] = list(self.cart.products.all())
        return context
    
    def render_cart_response(self, request, product, source):
        """
        Универсальный метод ответа для HTMX
        Управляет рендерингом кнопок в корзине, каталоге, деталке и шторке
        """
        response = None

        if self.cart:
            self.cart.refresh_from_db() 

        # --- СЦЕНАРИЙ 1: Изменение кол-ва внутри страницы корзины ---
        if source == 'cart-item':
            product_ct = ContentType.objects.get_for_model(product)
            cart_item = CartProduct.objects.filter(
                cart=self.cart, object_id=product.id, content_type=product_ct
            ).first()
            
            # Если товар есть, рендерим кнопки +/- 
            if cart_item:
                response = render(request, 'cart/controls/item_actions.html', {
                    'item': cart_item, 
                    'request': request
                })
            else:
                # Если товар удалили (кол-во < 1), возвращаем пустоту, чтобы удалить строку
                response = HttpResponse("")

            # Обновляем блок "Итого" (Summary) 
            try:
                summary_html = render_to_string('cart/components/summary.html', {'cart': self.cart}, request=request)
                if 'id="cart-summary"' in summary_html and 'hx-swap-oob' not in summary_html:
                    summary_html = summary_html.replace('id="cart-summary"', 'id="cart-summary" hx-swap-oob="true"', 1)
                
                if response:
                    response.content += summary_html.encode('utf-8')
                else:
                    response = HttpResponse(summary_html)
            except Exception:
                pass 
            
        # --- СЦЕНАРИЙ 2: Полное обновление списка (если удалили товар целиком) ---
        elif not source and 'cart' in request.META.get('HTTP_REFERER', ''):
            response = render(request, 'cart/components/items.html', {
                'cart': self.cart,
                'request': request
            })
            # Также обновляем Итоги
            try:
                summary_html = render_to_string('cart/components/summary.html', {'cart': self.cart}, request=request)
                if 'hx-swap-oob' not in summary_html:
                    summary_html = summary_html.replace('id="cart-summary"', 'id="cart-summary" hx-swap-oob="true"', 1)
                response.content += summary_html.encode('utf-8')
            except Exception:
                pass
        
        # --- СЦЕНАРИЙ 3: Кнопки на сайте (Каталог / Детальная / Шторка) ---
        elif source in ['detail', 'drawer', 'catalog', None]:
            
            cart_item = None
            cart_album_ids = set()
            favorite_album_ids = set()
            wishlist_album_ids = set()
            is_in_favorite = False
            is_in_wishlist = False
            
            # А. Данные корзины
            if self.cart:
                product_ct = ContentType.objects.get_for_model(product)
                
                cart_item = CartProduct.objects.filter(
                    cart=self.cart, content_type=product_ct, object_id=product.id
                ).first()
                
                cart_album_ids = set(
                    CartProduct.objects.filter(cart=self.cart, content_type=product_ct)
                    .values_list('object_id', flat=True)
                )

            # Б. Данные пользователя 
            if request.user.is_authenticated and hasattr(request.user, 'customer'):
                customer = request.user.customer
                
                is_in_favorite = customer.favorite.filter(id=product.id).exists()
                is_in_wishlist = customer.wishlist.filter(id=product.id).exists()
  
                favorite_album_ids = set(customer.favorite.values_list('id', flat=True))
                wishlist_album_ids = set(customer.wishlist.values_list('id', flat=True))

            context = {
                'album': product,
                'request': request,
                'cart': self.cart,
                'cart_item': cart_item,
                'cart_album_ids': cart_album_ids,
                'favorite_album_ids': favorite_album_ids,
                'wishlist_album_ids': wishlist_album_ids,
                'is_in_favorite': is_in_favorite,
                'is_in_wishlist': is_in_wishlist,
            }

            # Выбор шаблонов
            main_template = ''
            mirror_template = ''
            mirror_id = ''

            if source == 'detail':
                main_template = 'album/controls/actions.html'  
                mirror_template = 'album/controls/drawer_actions.html'
                mirror_id = f'drawer-actions-{product.id}'
                
            elif source == 'drawer':
                main_template = 'album/controls/drawer_actions.html'
                mirror_template = 'album/controls/actions.html'
                mirror_id = f'detail-actions-{product.id}'
                
            else:
                main_template = 'catalog/controls/actions.html'
                mirror_template = None

            # Рендеринг основного куска
            response = render(request, main_template, context)

            # Рендеринг зеркального куска (OOB Swap)
            if mirror_template:
                try:
                    mirror_html = render_to_string(mirror_template, context, request=request)
                    if f'id="{mirror_id}"' in mirror_html and 'hx-swap-oob' not in mirror_html:
                        mirror_html = mirror_html.replace(
                            f'id="{mirror_id}"', 
                            f'id="{mirror_id}" hx-swap-oob="true"', 
                            1
                        )
                    response.content += mirror_html.encode('utf-8')
                except Exception:
                    pass

        # --- ФИНАЛ: Обновление бейджа корзины ---
        if not response:
            response = HttpResponse("")

        try:
            badge_context = {'cart': self.cart}
            badge_html = render_to_string('cart/controls/badge.html', badge_context, request=request)
            response.content += badge_html.encode('utf-8')
        except Exception:
            pass
        
        return response