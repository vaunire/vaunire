from datetime import timedelta

import stripe
from django import views
from django.conf import settings
from django.contrib import messages
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.db import transaction
from django.db.models import F, Prefetch
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

from apps.accounts.models import Customer
from apps.cart.mixins import CartMixin
from apps.cart.models import Cart, CartProduct
from apps.catalog.models import Album, PriceList, Style
from apps.catalog.views import annotate_prices
from apps.orders.forms import OrderForm
from apps.orders.models import Order, Payment, ReturnRequest

# Настройка Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY


# ==========================================
# БЛОК 1: ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==========================================

def get_cached_pricelist():
    """Получает активный прайс-лист из кэша"""
    return cache.get_or_set(
        'active_pricelist',
        lambda: PriceList.objects.filter(is_active=True).first(),
        3600
    )

def prefetch_albums_for_products(products_list):
    """ Загружает альбомы """
    if not products_list:
        return

    album_ct = ContentType.objects.get_for_model(Album)
    
    # Сбор ID без лишних запросов
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
    """Применяет оптимизацию к объекту корзины."""
    if not cart:
        return
    
    # Загружаем продукты с ContentType
    products = list(cart.products.select_related('content_type').all())
    prefetch_albums_for_products(products)
    
    # Обновляем кэш префетча
    cart.products._result_cache = products
    cart.products._prefetch_done = True


# ==========================================
# БЛОК 2: ЛОГИКА ЗАКАЗОВ
# ==========================================

def process_successful_order(order):
    """
    Выполняется 1 раз при успешной оплате:
    1. Увеличивает продажи
    2. Списывает остатки
    3. Фиксирует использование промокода
    """
    # Защита от повторного выполнения
    if hasattr(order, '_processed') or order.status != 'created':
        if order.paid: 
            return

    items = list(order.cart.products.select_related('content_type').all())
    prefetch_albums_for_products(items)

    for item in items:
        product = item.content_object
        if product.stock >= item.quantity:
            product.stock = F('stock') - item.quantity
        else:
            product.stock = F('stock') - item.quantity 
        
        if item.content_type.model == 'album':
            product.total_sold = F('total_sold') + item.quantity
        
        product.save()

    cart = order.cart
    if cart.applied_promocode:
        cart.applied_promocode.times_used = F('times_used') + 1
        cart.applied_promocode.save()
    
    order._processed = True


class MakeOrderView(CartMixin, views.View):
    """Создаёт новый заказ, проверяет наличие и создает платеж в Stripe"""
    @transaction.atomic 
    def post(self, request, *args, **kwargs):
        form = OrderForm(request.POST or None)
        
        try:
            customer = Customer.objects.select_related('user').get(user=request.user)
        except Customer.DoesNotExist:
            customer, _ = Customer.objects.get_or_create(user=request.user)

        if form.is_valid():
            optimize_cart_products(self.cart)

            out_of_stock = []
            more_than_on_stock = []

            for item in self.cart.products.all():
                if not item.content_object.stock:
                    out_of_stock.append(f"{item.content_object.artist.name} - {item.content_object.name}")
                elif item.content_object.stock < item.quantity: 
                    more_than_on_stock.append({
                        'product': f"{item.content_object.artist.name} - {item.content_object.name}",
                        'stock': item.content_object.stock, 
                        'quantity': item.quantity
                    })

            error_message = ""
            if out_of_stock:
                error_message += f"Следующих товаров нет в наличии: {', '.join(out_of_stock)}. Пожалуйста, удалите их из корзины или дождитесь пополнения запасов.\n"
            if more_than_on_stock:
                for item in more_than_on_stock:
                    error_message += f"Товар '{item['product']}': доступно {item['stock']} шт., заказано {item['quantity']}. Пожалуйста, скорректируйте количество. \n"

            if error_message:
                messages.warning(request, error_message)
                return redirect('checkout')
            
            # --- 2. Создание заказа ---
            new_order = form.save(commit = False)
            new_order.customer = customer
            new_order.cart = self.cart
            new_order.first_name = form.cleaned_data['first_name']
            new_order.last_name = form.cleaned_data['last_name']
            new_order.phone = form.cleaned_data['phone']
            new_order.address = form.cleaned_data['address']
            new_order.buying_type = form.cleaned_data['buying_type']
            new_order.order_date = form.cleaned_data['order_date']
            new_order.comment = form.cleaned_data['comment']
            new_order.status = 'created'
            new_order.save()

            customer.first_name = form.cleaned_data['first_name']
            customer.last_name = form.cleaned_data['last_name']
            customer.phone = form.cleaned_data['phone']
            customer.address = form.cleaned_data['address']
            customer.save()
            
            # --- 3. Создание Stripe сессии ---
            try:
                line_items = []
                calculated_items_amount = 0

                for item in self.cart.products.all():
                    product_name = f"{item.content_object.artist.name} - {item.content_object.name}"
                    desc = f"Артикул: {item.content_object.article} | {item.content_object.get_format() or 'Standart'}"
                    img_url = 'https://via.placeholder.com/150'
                    if item.content_object.image:
                        img_url = request.build_absolute_uri(item.content_object.image.url)

                    unit_price_cents = int(item.content_object.discounted_price * 100)
                    
                    line_items.append({
                        'price_data': {
                            'currency': 'rub',
                            'product_data': {
                                'name': product_name,
                                'description': desc,
                                'images': [img_url],
                            },
                            'unit_amount': unit_price_cents,
                        },
                        'quantity': item.quantity,
                    })
                    
                    calculated_items_amount += item.content_object.discounted_price * item.quantity

                discounts = []
                
                if self.cart.applied_promocode:
                    discount_amount = calculated_items_amount - self.cart.final_price
                    
                    if discount_amount > 0:
                        coupon_name = self.cart.applied_promocode.code
                        
                        coupon = stripe.Coupon.create(
                            amount_off=int(discount_amount * 100), 
                            currency='rub',
                            duration='once',
                            name=coupon_name 
                        )
                        discounts = [{'coupon': coupon.id}]

                checkout_session = stripe.checkout.Session.create(
                    payment_method_types=['card'],
                    line_items=line_items,
                    discounts=discounts, 
                    locale='ru',
                    mode='payment',
                    success_url=request.build_absolute_uri(reverse('payment_success')) + '?session_id={CHECKOUT_SESSION_ID}',
                    cancel_url=request.build_absolute_uri(reverse('payment_cancel')) + f'?order_id={new_order.id}',
                    metadata={'order_id': new_order.id},
                )

                Payment.objects.create(
                    order=new_order,
                    amount=self.cart.final_price,
                    payment_id=checkout_session.id,
                    status='pending',
                    payment_method='Stripe'
                )

                self.cart.in_order = True
                self.cart.save()
                customer.orders.add(new_order)

                return redirect(checkout_session.url, code=303)

            except stripe.error.StripeError as e:
                new_order.delete()
                self.cart.in_order = False
                self.cart.save()
                messages.error(request, f'Ошибка платежной системы: {str(e)}')
                return redirect('checkout')

        else:
            messages.error(request, 'Пожалуйста, исправьте ошибки в форме.')
        return redirect('cart')
    
class PaymentSuccessView(views.View):
    def get(self, request, *args, **kwargs):
        session_id = request.GET.get('session_id')
        if not session_id:
            messages.error(request, 'Ошибка: сессия оплаты не найдена.')
            return redirect('/')
        
        try:
            session = stripe.checkout.Session.retrieve(session_id)
            order_id = session.metadata.get('order_id')
            order = Order.objects.select_related('cart').get(id=order_id)

            if not order.paid:
                order.paid = True
                order.status = 'in_progress'
                order.save()

                process_successful_order(order)

                payment = Payment.objects.get(payment_id = session_id)
                payment.status = 'success'
                payment.payment_date = timezone.now()
                payment.save()
                
            cart_products = list(order.cart.products.select_related('content_type').all())
            prefetch_albums_for_products(cart_products)
            
            context = {
                'order': order,
                'cart_products': cart_products,
                'total_price': order.cart.final_price,
            }
            return render(request, 'cart/states/paid_success.html', context)

        except (stripe.error.StripeError, Order.DoesNotExist, Payment.DoesNotExist) as e:
            messages.error(request, 'Ошибка при обработке платежа.')
            return redirect('/')


class PaymentCancelView(views.View):
    def get(self, request, *args, **kwargs):
        order_id = request.GET.get('order_id')
        if order_id:
            try:
                order = Order.objects.get(id = order_id, customer__user = request.user, paid = False)
                
                cart = order.cart
                cart.in_order = False
                cart.save()

                order.delete()
                messages.warning(request, 'Оплата была отменена. Вы можете попробовать снова.')
            except Order.DoesNotExist:
                messages.error(request, 'Заказ не найден.')
        else:
            messages.error(request, 'Некорректный запрос отмены.')

        return redirect('cart')

class StripeWebhookView(views.View):
    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def post(self, request, *args, **kwargs):
        payload = request.body
        sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
        endpoint_secret = settings.STRIPE_WEBHOOK_SECRET

        try:
            event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
        except (ValueError, stripe.error.SignatureVerificationError):
            return HttpResponse(status = 400)

        if event['type'] == 'checkout.session.completed':
            session = event['data']['object']
            order_id = session.get('metadata', {}).get('order_id')
            if not order_id:
                return HttpResponse(status=200)

            try:
                order = Order.objects.select_related('cart').get(id = order_id)
                if not order.paid:
                    order.paid = True
                    order.status = 'in_progress'
                    order.save()
                    
                    process_successful_order(order)

                    payment = Payment.objects.get(payment_id=session['id'])
                    payment.status = 'success'
                    payment.payment_date = timezone.now()
                    payment.save()
            except (Order.DoesNotExist, Payment.DoesNotExist):
                pass

        return HttpResponse(status=200)


# ==========================================
# БЛОК 3: ВОЗВРАТЫ
# ==========================================

class SubmitReturnView(views.View):
    """Обрабатывает запрос на возврат товара"""
    def post(self, request, order_id, *args, **kwargs):
        try:
            order = Order.objects.get(id = order_id, customer__user = request.user)
            customer = order.customer
        except Order.DoesNotExist:
            messages.error(request, 'Заказ не найден или вы не имеете к нему доступа.')
            return HttpResponseRedirect(request.META['HTTP_REFERER'])

        if order.order_date < timezone.now() - timedelta(days = 14):
            messages.error(request, 'Срок для подачи запроса на возврат истек.')
            return HttpResponseRedirect(request.META['HTTP_REFERER'])

        product_ids = request.POST.getlist('return-products')
        reason = request.POST.get('return-reason')
        details = request.POST.get('return-details', '')
        file = request.FILES.get('return-file')

        products = CartProduct.objects.filter(id__in = product_ids, cart = order.cart)
        if not products.exists():
            messages.error(request, 'Выбранные товары не относятся к этому заказу.')
            return HttpResponseRedirect(request.META['HTTP_REFERER'])
        
        return_request = ReturnRequest.objects.create(
            customer = customer,
            order = order,
            reason = reason,
            details = details,
            file = file if file else None
        )
        return_request.products.set(products)

        messages.success(request, 'Запрос на возврат успешно отправлен. Мы свяжемся с вами в ближайшее время.')
        return HttpResponseRedirect(request.META['HTTP_REFERER'])

class CancelReturnView(views.View):
    """Отменяет/Удаляет заявку на возврат"""
    def get(self, request, return_id, *args, **kwargs):
        try:
            return_request = ReturnRequest.objects.get(
                id = return_id,
                order__customer__user = request.user,
                status = 'pending'
            )
            return_request.delete() 
            messages.success(request, 'Заявка на возврат успешно отменена.')
        except ReturnRequest.DoesNotExist:
            messages.error(request, 'Заявка не найдена или не может быть отменена.')
        return HttpResponseRedirect(request.META['HTTP_REFERER'])