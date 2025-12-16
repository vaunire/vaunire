from datetime import timedelta

import stripe
from django import views
from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.db.models import F
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

from apps.accounts.models import Customer
from apps.cart.mixins import CartMixin
from apps.cart.models import Cart, CartProduct
from apps.catalog.models import Album

from .forms import OrderForm
from .models import Order, Payment, ReturnRequest

# Настройка Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY

# Обновляем количество проданных альбомов
def process_successful_order(order):
    """
    Выполняется 1 раз при успешной оплате:
    1. Увеличивает продажи
    2. Списывает остатки
    3. Фиксирует использование промокода
    """
    # Защита от повторного выполнения
    if hasattr(order, '_processed') or order.status != 'created':
        # Если статус уже 'paid' или 'in_progress', значит уже обработали
        if order.paid: 
            return

    # 1. Списание остатков и увеличение продаж
    for item in order.cart.products.all():
        product = item.content_object
        
        # Списываем со склада (только по факту оплаты)
        if product.stock >= item.quantity:
            product.stock = F('stock') - item.quantity
        else:
            # Если купили больше, чем есть, то уходим в минус
            product.stock = F('stock') - item.quantity 
        
        if item.content_type.model == 'album':
            product.total_sold = F('total_sold') + item.quantity
        
        product.save()

    # 2. Фиксация промокода
    cart = order.cart
    if cart.applied_promocode:
        cart.applied_promocode.times_used = F('times_used') + 1
        cart.applied_promocode.save()
    
    # Помечаем объект (для текущего запроса), что он обработан
    order._processed = True

class MakeOrderView(CartMixin, views.View):
    """Создаёт новый заказ, проверяет наличие и создает платеж в Stripe"""
    @transaction.atomic 
    def post(self, request, *args, **kwargs):
        form = OrderForm(request.POST or None)
        customer = Customer.objects.get(user = request.user)
        if form.is_valid():
            # --- 1. Проверка наличия товаров ---
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
            # Начальный статус
            new_order.status = 'created'
            new_order.save()

            # Обновление данных покупателя
            customer.first_name = form.cleaned_data['first_name']
            customer.last_name = form.cleaned_data['last_name']
            customer.phone = form.cleaned_data['phone']
            customer.address = form.cleaned_data['address']
            customer.save()
            
            # --- 3. Создание Stripe сессии ---
            try:
                line_items = []
                calculated_items_amount = 0

                # 1. Собираем ВСЕ товары в список
                for item in self.cart.products.all():
                    # Формируем данные товара
                    product_name = f"{item.content_object.artist.name} - {item.content_object.name}"
                    desc = f"Артикул: {item.content_object.article} | {item.content_object.get_format() or 'Standart'}"
                    img_url = 'https://via.placeholder.com/150'
                    if item.content_object.image:
                        img_url = request.build_absolute_uri(item.content_object.image.url)

                    # Цена одной штуки (с учетом скидок альбома, но БЕЗ промокода)
                    unit_price_cents = int(item.content_object.discounted_price * 100)
                    
                    # Добавляем в список для Stripe
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
                    
                    # Считаем сумму товаров вручную, чтобы понять размер скидки
                    calculated_items_amount += item.content_object.discounted_price * item.quantity

                # 2. Обработка ПРОМОКОДА (создание купона)
                discounts = []
                
                # Если в корзине применен промокод, итоговая цена (final_price) меньше суммы товаров
                if self.cart.applied_promocode:
                    # calculated_items_amount - это сумма товаров
                    # self.cart.final_price - это сколько клиент должен заплатить
                    discount_amount = calculated_items_amount - self.cart.final_price
                    
                    if discount_amount > 0:
                        coupon = stripe.Coupon.create(
                            amount_off=int(discount_amount * 100), 
                            currency='rub',
                            duration='once', # Одноразовая скидка на этот чек
                            name=f"Промокод {self.cart.applied_promocode.code}"
                        )
                        # Добавляем купон в параметры сессии
                        discounts = [{'coupon': coupon.id}]

                # 3. Создаем сессию
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
                # Откат в случае ошибки
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
            order = Order.objects.get(id=order_id)

            if not order.paid:
                order.paid = True
                order.status = 'in_progress'
                order.save()

                process_successful_order(order)

                payment = Payment.objects.get(payment_id = session_id)
                payment.status = 'success'
                payment.payment_date = timezone.now()
                payment.save()
                
                cart_products = order.cart.products.all()
                context = {
                    'order': order,
                    'cart_products': cart_products,
                    'total_price': order.cart.final_price,
                }
                return render(request, 'partials/cart/states/paid_success.html', context)

        except (stripe.error.StripeError, Order.DoesNotExist, Payment.DoesNotExist) as e:
            messages.error(request, 'Ошибка при обработке платежа.')
            return redirect('/')


class PaymentCancelView(views.View):
    def get(self, request, *args, **kwargs):
        order_id = request.GET.get('order_id')
        if order_id:
            try:
                # Ищем заказ, который принадлежит текущему пользователю и еще НЕ оплачен
                order = Order.objects.get(id = order_id, customer__user = request.user, paid = False)
                
                # Освобождаем корзину
                cart = order.cart
                cart.in_order = False
                cart.save()

                # Удаляем сам черновик заказа (так как оплата не прошла, он нам не нужен, пользователь создаст новый при следующей попытке)
                order.delete()
                messages.warning(request, 'Оплата была отменена. Вы можете попробовать снова.')
            except Order.DoesNotExist:
                 # Если заказ не найден (или уже удален/оплачен)
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
                order = Order.objects.get(id = order_id)
                if not order.paid:
                    order.paid = True
                    order.status = 'in_progress'
                    order.save()
                    
                    # Дублируем логику успеха (на случай, если пользователь закрыл браузер до редиректа)
                    process_successful_order(order)

                    payment = Payment.objects.get(payment_id=session['id'])
                    payment.status = 'success'
                    payment.payment_date = timezone.now()
                    payment.save()
            except (Order.DoesNotExist, Payment.DoesNotExist):
                pass

        return HttpResponse(status=200)

class SubmitReturnView(views.View):
    """Обрабатывает запрос на возврат товара"""
    def post(self, request, order_id, *args, **kwargs):
        try:
            order = Order.objects.get(id = order_id, customer__user = request.user)
            customer = order.customer
        except Order.DoesNotExist:
            messages.error(request, 'Заказ не найден или вы не имеете к нему доступа.')
            return HttpResponseRedirect(request.META['HTTP_REFERER'])

        # Проверка срока подачи возврата (14 дней с даты получения)
        if order.order_date < timezone.now() - timedelta(days = 14):
            messages.error(request, 'Срок для подачи запроса на возврат истек.')
            return HttpResponseRedirect(request.META['HTTP_REFERER'])

        # Получение данных из формы
        product_ids = request.POST.getlist('return-products')
        reason = request.POST.get('return-reason')
        details = request.POST.get('return-details', '')
        file = request.FILES.get('return-file')

        # Проверка, что товары принадлежат заказу
        products = CartProduct.objects.filter(id__in = product_ids, cart = order.cart)
        if not products.exists():
            messages.error(request, 'Выбранные товары не относятся к этому заказу.')
            return HttpResponseRedirect(request.META['HTTP_REFERER'])
        # Создание запроса на возврат
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