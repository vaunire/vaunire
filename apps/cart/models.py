import operator
from decimal import Decimal

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone

from apps.promotions.models import PromoCode

# ❒ Модель для хранения корзины пользователя
class Cart(models.Model):
    owner = models.ForeignKey('accounts.Customer', verbose_name = 'Покупатель', on_delete = models.CASCADE)
    total_products = models.IntegerField(default = 0, verbose_name = 'Общее кол-во товара')
    final_price = models.DecimalField(max_digits = 10, decimal_places = 2, verbose_name = 'Финальная цена', null = True, blank = True)
    original_price = models.DecimalField(max_digits = 10, decimal_places = 2, verbose_name = 'Первоначальная цена', null = True, blank = True)
    applied_promocode = models.ForeignKey(PromoCode, verbose_name = 'Примененный промокод', null = True, blank = True, on_delete = models.SET_NULL)
    in_order = models.BooleanField(default = False, verbose_name = 'В заказе')
    anonymous_user = models.BooleanField(default = False, verbose_name = 'Анонимный пользователь')

    def __str__(self):
        return str(self.id)

    class Meta:
            verbose_name = 'Корзина'
            verbose_name_plural = 'Корзины'

    def update_totals(self):
        """Полностью пересчитывает итоги корзины"""
        # Если объекта еще нет в БД, нет смысла считать
        if not self.pk:
            self.original_price = Decimal('0.00')
            self.final_price = Decimal('0.00')
            return

        cart_products = self.products.all()
        
        # 1. Считаем количество и базовые цены товаров
        self.total_products = sum(cp.quantity for cp in cart_products) or 0
        
        # Первоначальная цена (сумма без скидок)
        self.original_price = sum(
            cp.quantity * cp.content_object.current_price 
            for cp in cart_products
        ) or Decimal('0.00')
        
        # Цена с учетом скидок на товары (акции альбомов)
        products_price = sum(
            cp.quantity * cp.content_object.discounted_price 
            for cp in cart_products
        ) or Decimal('0.00')

        # 2. Применяем промокод
        self.final_price = products_price

        if self.applied_promocode:
            promocode = self.applied_promocode
            is_valid = True
            
            now = timezone.now()
            if not promocode.is_active:
                is_valid = False
            elif now < promocode.valid_from or now > promocode.valid_until:
                is_valid = False
            elif promocode.max_uses > 0 and promocode.times_used >= promocode.max_uses:
                is_valid = False
            elif self.final_price < promocode.min_purchase_amount:
                is_valid = False
            
            if is_valid:
                self.final_price = products_price - promocode.discount_amount
            else:
                self.applied_promocode = None

        # Защита от отрицательной цены
        if self.final_price < 0:
            self.final_price = Decimal('0.00')

    def save(self, *args, **kwargs):
        # 1. Если это создание, сначала сохраняем, чтобы получить ID
        if not self.pk:
            super().save(*args, **kwargs)
            
        # 2. Пересчитываем цифры (но не сохраняем внутри update_totals)
        self.update_totals()
        
        # 3. Сохраняем окончательно с новыми цифрами
        super().save(*args, **kwargs)

    @property
    def products_in_cart(self):
        return [cart_product.content_object for cart_product in self.products.all()]

    @property
    def discount(self):
        if self.original_price and self.final_price and self.original_price > self.final_price:
            return self.original_price - self.final_price
        return 0
    
    @property
    def cart_item_ids(self):
        """Возвращает список ID всех товаров в корзине"""
        return list(self.products.values_list('object_id', flat = True))
    
# ❒ Промежуточная модель для хранения товаров в корзине
class CartProduct(models.Model):
    # Если магазин расширится и начнет продавать не только альбомы, но и, например, услуги, модель CartProduct можно легко адаптировать:
    MODEL_CART_PRODUCT_DISPLAY_NAME_MAP = {
         "Album" : {"is_constructable": True, "fields": ["name", "artist.name"], "separator": ' – '}
         # "Service": {"is_constructable": False, "field": "name"},
         # "RecordPlayer": {"is_constructable": True, "fields": ["brand", "model"], "separator": ' '},
    }

    user = models.ForeignKey('accounts.Customer', verbose_name = 'Покупатель', on_delete = models.CASCADE)
    cart = models.ForeignKey('Cart', verbose_name = 'Корзина', on_delete = models.CASCADE, related_name = 'products')

    content_type = models.ForeignKey(ContentType, on_delete = models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    quantity = models.PositiveIntegerField(default = 1, verbose_name = 'Количество')
    final_price = models.DecimalField(max_digits = 10, decimal_places = 2, verbose_name = 'Общая цена')

    def __str__(self):
        return f"Продукт: {self.content_object.name}"
        
    def get_product_price(self):
        # Возвращает текущую цену продукта из прайс-листа для Album
        if self.content_type.model == 'album': 
            return self.content_object.discounted_price  
        # elif self.content_type.model == 'service':
        #     return self.content_object.price
        raise ValueError(f"Объект {self.content_object} не поддерживает определение цены")

    @property
    def unit_price(self):
        """Возвращает цену за единицу товара, основываясь на сохраненной финальной цене"""
        if self.quantity and self.final_price:
            return self.final_price / self.quantity
        return 0

    @property
    # Возвращает отображаемое имя продукта в корзине
    def display_name(self):
        model_fields = self.MODEL_CART_PRODUCT_DISPLAY_NAME_MAP.get(self.content_object.__class__._meta.model_name.capitalize())
        prefix = model_fields.get("prefix", "")
        # Если is_constructable равно True, имя формируется динамически из указанных полей
        if model_fields and model_fields['is_constructable']:
            display_name = model_fields['separator'].join(
                # operator.attrgetter — извлекает атрибуты (например, name, artist.name) динамически из content_object
                [operator.attrgetter(field)(self.content_object) for field in model_fields['fields']]
            )
            return f"{prefix}{display_name}"
        # Если is_constructable равно False, имя берется напрямую из указанного поля
        if model_fields and not model_fields['is_constructable']:
            display_name = operator.attrgetter(model_fields['field'])(self.content_object)
            return f"{prefix}{display_name}"
        return self.content_object
    
    def save(self, *args, **kwargs):
        # Пересчитывает итоговую цену на основе текущей цены продукта из прайс-листа
        self.final_price = self.quantity * self.get_product_price()
        super().save(*args, **kwargs)
        self.cart.save()

    class Meta:
            verbose_name = 'Продукт корзины'
            verbose_name_plural = 'Продукты корзины'
            unique_together = [['cart', 'content_type', 'object_id']]
            ordering = ['id'] 

