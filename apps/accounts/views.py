from collections import defaultdict
from datetime import timedelta

from django import views
from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core.paginator import Paginator
from django.db import models
from django.db.models import Count, Prefetch, Sum
from django.db.models.functions import TruncDate
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.decorators import method_decorator

from apps.cart.mixins import CartMixin
from apps.catalog.models import Album, ImageGallery, PriceList
from apps.catalog.utils import get_visible_styles
from apps.catalog.views import annotate_prices
from apps.orders.models import Order, ReturnRequest

from .forms import LoginForm, ProfileEditForm, RegistrationForm
from .mixins import NotificationsMixin
from .models import Customer, Notifications


def get_optimized_customer(user):
    """Получает покупателя со всеми необходимыми предзагрузками для профиля"""
    try:
        active_pricelist = PriceList.objects.filter(is_active=True).first()
        
        # Предзагружаем Wishlist с ценами и артистами
        wishlist_qs = annotate_prices(Album.objects.all(), active_pricelist).select_related('artist')
        
        # Предзагружаем ReturnRequests с вложениями
        return_requests_qs = ReturnRequest.objects.select_related('order').prefetch_related('products')

        customer = Customer.objects.select_related('user').prefetch_related(
            Prefetch('wishlist', queryset=wishlist_qs),
            Prefetch('return_requests', queryset=return_requests_qs),
            'favorite' 
        ).get(user=user)
        return customer
    except Customer.DoesNotExist:
        return None

def get_optimized_orders_context(customer):
    """Возвращает список заказов с оптимизированными запросами и статусами возвратов"""
    if not customer:
        return []
    orders = Order.objects.filter(customer=customer).select_related('cart').prefetch_related(
        'cart__products__content_object__artist',
        'cart__products__content_object__styles',
    ).order_by('-created_at')

    # Принудительно вычисляем QuerySet, чтобы получить список объектов
    orders = list(orders) 

    if not orders:
        return []

    # Пакетная выгрузка заявок на возврат для этих заказов
    return_requests = ReturnRequest.objects.filter(order__in=orders).values('order_id', 'status')
    
    # Группируем статусы по заказам в памяти
    rr_map = defaultdict(set)
    for rr in return_requests:
        rr_map[rr['order_id']].add(rr['status'])

    orders_with_status = []
    for order in orders:
        statuses = rr_map[order.id]
        orders_with_status.append({
            'order': order,
            'has_pending_return': 'pending' in statuses,
            'has_approved_return': 'approved' in statuses,
            'has_canceled_return': 'canceled' in statuses,
            'has_paid_return': 'paid' in statuses
        })
    return orders_with_status

class AccountView(CartMixin, NotificationsMixin, views.View):
    def get(self, request, tab='account', *args, **kwargs):
        customer = get_optimized_customer(request.user)

        orders_with_status = get_optimized_orders_context(customer)

        last_paid_order = None
        if customer:
            for item in orders_with_status:
                if item['order'].paid:
                    last_paid_order = item['order']
                    break
        
        valid_tabs = ['account', 'orders', 'wishlist', 'returns']
        if tab not in valid_tabs:
            tab = 'account'

        highlighted_order_id = request.GET.get('order_id')
        form = ProfileEditForm(instance = request.user, customer = customer)

        total_spent = 0
        next_discount_threshold = 15000 
        current_discount = 0 
        
        if customer:
            total_spent_agg = customer.orders.filter(
                payments__status='success'
            ).aggregate(total=Sum('payments__amount'))
            
            total_spent = total_spent_agg['total'] or 0

            # Значения по умолчанию (0-15 000)
            current_discount = 0
            next_discount_threshold = 15000
            next_discount_percent = 3

            # Логика уровней (от самого высокого к низкому)
            if total_spent >= 500000:
                current_discount = 20
                next_discount_threshold = 0  
                next_discount_percent = 0
            elif total_spent >= 300000:
                current_discount = 15
                next_discount_threshold = 500000
                next_discount_percent = 20
            elif total_spent >= 100000:
                current_discount = 10
                next_discount_threshold = 300000
                next_discount_percent = 15
            elif total_spent >= 50000:
                current_discount = 5
                next_discount_threshold = 100000
                next_discount_percent = 10
            elif total_spent >= 15000:
                current_discount = 3
                next_discount_threshold = 50000
                next_discount_percent = 5
        
        # Расчет процентов для прогресс-бара
        if next_discount_threshold > 0:
            # Считаем процент заполнения
            progress_percent = min(100, (total_spent / next_discount_threshold) * 100)
            amount_left = max(0, next_discount_threshold - total_spent)
        else:
            # Если достигнут максимум (20%)
            progress_percent = 100
            amount_left = 0

            next_discount_threshold = total_spent 


        context = {
            'customer': customer,
            'cart': self.cart,
            'notifications': self.notifications(request.user),
            'orders_with_status': orders_with_status,
            'last_paid_order': last_paid_order,
            'active_tab': tab,
            'highlighted_order_id': highlighted_order_id,
            'form': form,
            'is_editing': False,

            'total_spent': total_spent,
            'next_discount_threshold': next_discount_threshold,
            'discount_percent': current_discount,
            'next_discount_percent': next_discount_percent, 
            'progress_percent': int(progress_percent),
            'amount_left': amount_left,
        }
        return render(request, 'profile/profile.html', context) 

class LoginView(views.View):
    """Проверяет введённые данные, аутентифицирует пользователя и выполняет вход"""
    def get(self, request, *args, **kwargs):
        form = LoginForm(request.POST or None)
        context = {
            'form': form
        }
        return render(request, 'auth/login.html', context)
    
    def post(self, request, *args, **kwargs):
        form = LoginForm(request.POST or None)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            user = authenticate(username = username, password = password)
            if user:
                login(request, user)
                return HttpResponseRedirect('/')
        context = {
            'form': form
        }
        return render(request, 'auth/login.html', context)
    
class RegistrationView(views.View):
    """Проверяет введённые данные, создаёт пользователя и выполняет вход"""
    def get(self, request, *args, **kwargs):
        form = RegistrationForm(request.POST or None)
        context = {
            'form': form
        }
        return render(request, 'auth/registration.html', context)
    
    def post(self, request, *args, **kwargs):
        form = RegistrationForm(request.POST or None)
        if form.is_valid():
            new_user = form.save(commit = False)
            new_user.username = form.cleaned_data['username']
            new_user.email = form.cleaned_data['email']
            new_user.first_name = form.cleaned_data['first_name']
            new_user.last_name = form.cleaned_data['last_name']
            new_user.save()
            new_user.set_password(form.cleaned_data['password'])
            new_user.save()
            Customer.objects.create(
                user = new_user,
                phone = form.cleaned_data['phone'],
                email = form.cleaned_data['email']
            )
            user = authenticate(username = form.cleaned_data['username'], password = form.cleaned_data['password'])
            login(request, user)
            return HttpResponseRedirect('/')
        context = {
            'form': form
        }
        return render(request, 'auth/registration.html', context)
    
@method_decorator(login_required, name = 'dispatch') # Декоратор проверки авторизации 
class UpdateProfileView(CartMixin, NotificationsMixin, views.View):
    
    def get(self, request, *args, **kwargs):
        customer = get_optimized_customer(request.user)
        if not customer: 
             customer, _ = Customer.objects.get_or_create(user=request.user)

        is_editing = request.GET.get('edit', False)
        form = ProfileEditForm(instance = request.user, customer = customer)
        orders_with_status = get_optimized_orders_context(customer)

        return render(request, 'profile/profile.html', {
            'form': form,
            'customer': customer,
            'is_editing': is_editing,
            'active_tab': 'account',
            'cart': self.cart,
            'notifications': self.notifications(request.user),
            'orders_with_status': orders_with_status,
        })

    def post(self, request, *args, **kwargs):
        customer = get_optimized_customer(request.user)
        if not customer:
             customer, _ = Customer.objects.get_or_create(user=request.user)

        form = ProfileEditForm(request.POST, instance=request.user, customer=customer)
        orders_with_status = get_optimized_orders_context(customer)
        
        if form.is_valid():
            if 'avatar' in request.FILES:
                # Берем файл из запроса
                image_file = request.FILES['avatar']

                customer.avatar = image_file
                customer.save()
            form.save()
            messages.success(request, 'Профиль успешно обновлён!')
            return redirect('account_tab', tab='account')
        else:
            messages.error(request, 'Пожалуйста, исправьте ошибки в форме.')

        return render(request, 'profile/profile.html', {
            'form': form,
            'customer': customer,
            'is_editing': True,
            'active_tab': 'account',
            'cart': self.cart,
            'notifications': self.notifications(request.user),
            'orders_with_status': orders_with_status,
        })

class FavoritesView(CartMixin, NotificationsMixin, views.View):
    """Представление для отображения избранных альбомов пользователя"""
    def get(self, request, *args, **kwargs):
        customer = request.user.customer
        albums_qs = customer.favorite.all()

        active_pricelist = PriceList.objects.filter(is_active = True).first()
        albums_qs = annotate_prices(albums_qs, active_pricelist)
        
        # Фильтры
        filters = {
            'sort': request.GET.get('sort', ''),
            'in_stock': request.GET.get('in_stock') == '1'
        }

        if filters['in_stock']:
            albums_qs = albums_qs.filter(stock__gt=0)
        
        sort_param = filters['sort']

        # Логика сортировки
        ordering_map = {
            'price_desc': '-annotated_discounted_price',
            'price_asc': 'annotated_discounted_price',
            'name_asc': 'name',
            'name_desc': '-name',
        }

        sort_field = ordering_map.get(sort_param, '-id')
        albums_qs = albums_qs.order_by(sort_field)

        # Пагинация
        paginator = Paginator(albums_qs, 15)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        for album in page_obj:
            album.visible_styles = get_visible_styles(album)
            album.remaining_styles_count = max(0, album.styles.count() - len(album.visible_styles))

        sort_label = {
            '': 'Сначала новые',
            'price_desc': 'По убыванию цены',
            'price_asc': 'По возрастанию цены',
            'name_asc': 'По названию: от А до Я',
            'name_desc': 'По названию: от Я до А'
        }.get(sort_param, 'Сначала новые')
        

        context = {
            'page_obj': page_obj,
            'albums': page_obj,
            'cart': self.cart,
            'notifications': self.notifications(request.user),
            'is_fav_page': True,
            'favorite_album_ids': {album.id for album in page_obj},

            'sort_label': sort_label,
            'filters': filters, 
        }

        if request.headers.get('HX-Request') and request.headers.get('HX-Target') == 'favorites-grid':
            return render(request, 'favorites/components/items_list.html', context)
        
        return render(request, 'favorites/favorites.html', context)

class AddToWishlist(CartMixin, views.View):
    """Добавляет альбом в список ожидания пользователя"""
    def get(self, request, *args, **kwargs):
        album = get_object_or_404(Album, id=kwargs['album_id'])
        customer = Customer.objects.get(user=request.user)
        customer.wishlist.add(album)
        
        if request.headers.get('HX-Request') == 'true':
            return self.render_cart_response(request, album, request.headers.get('X-Source'))
            
        return HttpResponseRedirect(request.META['HTTP_REFERER'])

class RemoveFromWishlist(CartMixin, views.View):
    """Удаляет альбом из списка ожидания пользователя"""
    def get(self, request, *args, **kwargs):
        album = get_object_or_404(Album, id=kwargs['album_id'])
        customer = Customer.objects.get(user=request.user)
        customer.wishlist.remove(album)
        
        if request.headers.get('HX-Request') == 'true':
            return self.render_cart_response(request, album, request.headers.get('X-Source'))
        return HttpResponseRedirect(request.META['HTTP_REFERER'])

class AddToFavorite(CartMixin, views.View):
    """Добавляет альбом в избранное пользователя"""
    def get(self, request, *args, **kwargs):
        album = get_object_or_404(Album, id=kwargs['album_id'])
        customer = Customer.objects.get(user=request.user)
        customer.favorite.add(album)
        
        if request.headers.get('HX-Request') == 'true':
            return self.render_cart_response(request, album, request.headers.get('X-Source'))

        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

class RemoveFromFavorite(CartMixin, views.View):
    """Удаляет альбом из избранного"""
    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return HttpResponseRedirect('/login/')
            
        album = get_object_or_404(Album, id=kwargs['album_id'])
        customer = Customer.objects.get(user=request.user)
        customer.favorite.remove(album)
        
        # Считаем остаток
        fav_count = customer.favorite.count()
        
        if request.headers.get('HX-Request') == 'true':
            is_fav_page = 'favorites' in request.META.get('HTTP_REFERER', '')

            # СЦЕНАРИЙ 1: Мы на странице "Избранное" и список опустел
            if is_fav_page and fav_count == 0:
                empty_list_html = render_to_string('favorites/states/empty_state.html', request = request)
                counter_html = '<span id="fav-counter" hx-swap-oob="true" class="hidden"></span>'
                return HttpResponse(empty_list_html + counter_html)
            
            # СЦЕНАРИЙ 2: Мы на странице "Избранное", список не пуст (обновляем только карточку)
            elif is_fav_page:
                response = render(request, 'catalog/controls/actions.html', {
                    'album': album,
                    'request': request,
                    'cart': self.cart
                })
                
                oob_counter = f"""
                <span id="fav-counter" hx-swap-oob="true" class="absolute -top-1 -right-2.5 text-3xl text-blue-600 opacity-25 font-bold font-geologica tracking-wide blur-xs">
                    {fav_count}
                </span>
                """
                response.content += oob_counter.encode('utf-8')
                return response

            # СЦЕНАРИЙ 3: Обычный клик (Каталог, Детальная страница и т.д.)
            else:
                return self.render_cart_response(request, album, request.headers.get('X-Source'))
        
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
        
class ClearNotificationsView(views.View):
    """Помечает все непрочитанные уведомления как прочитанные"""
    @staticmethod
    def get(request, *args, **kwargs):
        Notifications.objects.mark_unread_as_read(request.user.customer)
        return HttpResponseRedirect(request.META['HTTP_REFERER'])

def dashboard_callback(request, context):
    """Callback для информационной панели Unfold Admin"""
    
    # Диапазон дат: последние 14 дней
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=13)  # 14 дней включительно

    # --- Данные для графика регистраций ---
    registrations = (
        User.objects
        .filter(date_joined__date__range=[start_date, end_date])
        .annotate(day=TruncDate('date_joined'))
        .values('day')
        .annotate(count=Count('id'))
        .order_by('day')
    )
    
    # Преобразуем в словарь для быстрого доступа
    reg_dict = {item['day']: item['count'] for item in registrations}

    # --- Данные для графика заказов ---
    orders = (
        Order.objects
        .filter(created_at__date__range=[start_date, end_date])
        .annotate(day=TruncDate('created_at'))
        .values('day')
        .annotate(count=Count('id'))
        .order_by('day')
    )
    
    order_dict = {item['day']: item['count'] for item in orders}

    # --- Формируем массивы для графиков ---
    registration_labels = []
    registration_counts = []
    order_labels = []
    order_counts = []

    current_date = start_date
    while current_date <= end_date:
        # Формат даты для отображения
        label = current_date.strftime('%d.%m')
        
        registration_labels.append(label)
        registration_counts.append(reg_dict.get(current_date, 0))
        
        order_labels.append(label)
        order_counts.append(order_dict.get(current_date, 0))
        
        current_date += timedelta(days=1)

    # --- Последние добавленные альбомы ---
    latest_albums = (
        Album.objects
        .select_related('artist')
        .order_by('-id')[:5]
    )

    # Обновляем контекст
    context.update({
        "registration_data": {
            "labels": registration_labels,
            "counts": registration_counts
        },
        "order_data": {
            "labels": order_labels,
            "counts": order_counts
        },
        "latest_albums": latest_albums,
    })

    return context