from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


# ❒ Модель для хранения акций (например, сезонная распродажа)
class Promotion(models.Model):
    name = models.CharField(max_length = 100, verbose_name = "Наименовании акции")
    description = models.TextField(blank = True, verbose_name = "Описание")
    start_date = models.DateTimeField(verbose_name = "Дата начала")
    end_date = models.DateTimeField(verbose_name = "Дата окончания")
    discount_percentage = models.DecimalField(max_digits = 5, decimal_places = 2, validators = [MinValueValidator(0), MaxValueValidator(100)], verbose_name = "Процент скидки")
    albums = models.ManyToManyField('catalog.Album', blank = True, verbose_name = "Альбомы, участвующие в акции", related_name = 'promotions')
    is_active = models.BooleanField(default = True, verbose_name = "Активна")

    class Meta:
        verbose_name = "Акция"
        verbose_name_plural = "Акции"

    def __str__(self):
        return f"{self.name} ({self.discount_percentage}%)"

    def is_valid(self):
        now = timezone.now()
        return self.is_active and self.start_date <= now <= self.end_date

# ❒ Модель промокода с фиксированной или процентной скидкой
class PromoCode(models.Model):
    code = models.CharField(max_length = 20, unique = True, verbose_name = "Код")
    discount_amount = models.DecimalField(max_digits = 10, decimal_places = 2, validators = [MinValueValidator(0)], verbose_name = "Фиксированная скидка (руб)")
    valid_from = models.DateTimeField(verbose_name = "Действует с")
    valid_until = models.DateTimeField(verbose_name = "Действует до")
    max_uses = models.PositiveIntegerField(default = 0, verbose_name = "Максимальное количество использований (0 = без ограничений)")
    times_used = models.PositiveIntegerField(default = 0, verbose_name = "Сколько раз использовано")
    is_active = models.BooleanField(default = True, verbose_name = "Активен")
    min_purchase_amount = models.DecimalField(max_digits = 10, decimal_places = 2, validators = [MinValueValidator(0)], default = 0, verbose_name = "Минимальная сумма покупки (руб)")

    class Meta:
        verbose_name = "Промокод"
        verbose_name_plural = "Промокоды"

    def __str__(self):
        return self.code

    def is_valid(self):
        """Базовая проверка: активен ли промокод"""
        now = timezone.now()
        return (
            self.is_active
            and self.valid_from <= now <= self.valid_until
            and (self.max_uses == 0 or self.times_used < self.max_uses)
        )

    def check_applicability(self, cart_price: Decimal):
        """Полная проверка применимости промокода к корзине"""
        if not self.is_valid():
            if not self.is_active:
                return False, "Промокод неактивен."
            if timezone.now() < self.valid_from:
                return False, "Промокод ещё не действует."
            if timezone.now() > self.valid_until:
                return False, "Промокод истёк."
            if self.max_uses > 0 and self.times_used >= self.max_uses:
                return False, "Промокод достиг лимита использований."

        if cart_price < self.min_purchase_amount:
            return False, f"Минимальная сумма покупки: {self.min_purchase_amount} ₽."

        return True, ""
