from decimal import Decimal
# Поддержка универсальных связей (Generic Relations) для связи с галереей изображений
from django.contrib.contenttypes.fields import (GenericForeignKey,
                                                GenericRelation)
from django.contrib.contenttypes.models import ContentType

from django.db import connection, models
from django.urls import reverse
from django.utils import timezone
# mark_safe — делает строку безопасной для HTML (не экранирует теги)
from django.utils.safestring import mark_safe
# slugify — функция для генерации URL-ссылок
from slugify import slugify

# Кастомная функция для загрузки изображений (определяет путь сохранения файлов)
from utils import upload_function


# ❒ Модель для хранения типов медианосителей
class MediaType(models.Model):
    name = models.CharField(max_length = 100, verbose_name = 'Название медианосителя')

    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name = 'Медианоситель'
        verbose_name_plural = 'Медианосители'

# ❒ Модель для хранения стран
class Country(models.Model):
    name = models.CharField(max_length = 100, verbose_name = 'Название страны')

    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name = 'Страна'
        verbose_name_plural = 'Страны'

# ❒ Модель для хранения информации о музыкальных лейблах
class Label(models.Model):
    name = models.CharField(max_length = 255, verbose_name = 'Название лейбла', unique = True)
    country = models.ForeignKey(Country, on_delete = models.SET_NULL, verbose_name = 'Страна', blank = True, null = True)
    description = models.TextField(verbose_name = 'Описание', blank = True, null = True)
    founded_year = models.PositiveIntegerField(verbose_name = 'Год основания', blank = True, null = True)
    slug = models.SlugField(blank = True, help_text = 'Оставьте пустым для автозаполнения')

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name, lowercase=True)
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = 'Лейбл'
        verbose_name_plural = 'Лейблы'

# ❒ Модель для хранения информации об участниках музыкальных групп
class Member(models.Model):
    first_name = models.CharField(max_length = 255, verbose_name = 'Имя музыканта')
    last_name = models.CharField(max_length = 255, verbose_name = 'Фамилия музыканта', blank = True, null = True)
    country = models.ForeignKey(Country, on_delete = models.SET_NULL, verbose_name = 'Страна', blank = True, null = True)
    birth_date = models.DateField(verbose_name = 'Дата рождения', blank = True, null = True)
    role = models.CharField(max_length = 100, verbose_name = 'Роль в группе', blank = True, null = True)
    slug = models.SlugField(blank = True, help_text = 'Оставьте пустым для автозаполнения')
    image = models.ImageField(upload_to = upload_function, blank = True, null = True)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(f"{self.first_name} {self.last_name}", lowercase=True)
        super().save(*args, **kwargs)
    
    class Meta:
        verbose_name = 'Музыкант'
        verbose_name_plural = 'Музыканты'

# ❒ Модель для хранения типов музыкальных жанров
class Genre(models.Model):
    name = models.CharField(max_length = 50, verbose_name = 'Название жанра')
    slug = models.SlugField(blank = True, help_text = 'Оставьте пустым для автозаполнения')

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug: 
            self.slug = slugify(self.name, lowercase=True) 
        super().save(*args, **kwargs)
    
    class Meta:
        verbose_name = 'Жанр'
        verbose_name_plural = 'Жанры'

# ❒ Модель для хранения музыкальных стилей
class Style(models.Model):
    name = models.CharField(max_length = 100, verbose_name = 'Название стиля')
    genre = models.ForeignKey(Genre, on_delete = models.CASCADE, verbose_name = 'Жанр', related_name = 'styles')
    slug = models.SlugField(blank = True, help_text = 'Оставьте пустым для автозаполнения')

    def __str__(self):
        return f"{self.name} ({self.genre.name})"
    
    def save(self, *args, **kwargs):
        if not self.slug:  
            self.slug = slugify(self.name, lowercase=True) 
        super().save(*args, **kwargs)
    
    class Meta:
        verbose_name = 'Стиль'
        verbose_name_plural = 'Стили'

class AlbumManager(models.Manager):
    def get_month_bestseller(self):
        now = timezone.now()
        current_year = now.year
        current_month = now.month

        query = """
            SELECT 
                ca.id, 
                ca.name AS album_name, 
                ca.artist_id, 
                a.name AS artist_name,
                SUM(cp.quantity) AS total_sold,
                ca.slug AS album_slug,
                a.slug AS artist_slug
            FROM orders_order o
            INNER JOIN cart_cart cc ON o.cart_id = cc.id
            INNER JOIN cart_cartproduct cp ON cp.cart_id = cc.id
            INNER JOIN catalog_album ca ON cp.object_id = ca.id
            INNER JOIN catalog_artist a ON ca.artist_id = a.id
            INNER JOIN django_content_type dct ON cp.content_type_id = dct.id
            WHERE 
                o.status = 'completed'
                AND EXTRACT(YEAR FROM o.created_at) = %s
                AND EXTRACT(MONTH FROM o.created_at) = %s
                AND dct.model = 'album'
            GROUP BY ca.id, ca.name, ca.artist_id, a.name, ca.slug, a.slug
            ORDER BY total_sold DESC
            LIMIT 1
        """

        with connection.cursor() as cursor:
            cursor.execute(query, [current_year, current_month])
            result = cursor.fetchone()

            if result:
                album = Album.objects.select_related('artist', 'genre').prefetch_related('styles').get(id=result[0])
                # Добавляем атрибут total_sold к объекту Album
                album.total_sold = result[4]
                return album
            return None
        
# ❒ Модель для хранения информации о музыкальных исполнителях или группах
class Artist(models.Model):
    name = models.CharField(max_length = 255, verbose_name = 'Исполнитель/группа')
    description = models.TextField(verbose_name = 'Описание', blank = True, null = True)
    country = models.ForeignKey(Country, on_delete = models.SET_NULL, verbose_name = 'Страна', blank = True, null = True) 
    genre = models.ForeignKey(Genre, verbose_name = 'Жанр', on_delete = models.CASCADE)
    members = models.ManyToManyField(Member, verbose_name = 'Участник', related_name = 'artist', blank = True)
    image_gallery = GenericRelation('ImageGallery', related_query_name = 'artists')

    image = models.ImageField(upload_to = upload_function, blank = True, null = True)
    slug = models.SlugField(blank = True, help_text = 'Оставьте пустым для автозаполнения')

    def __str__(self):
        return f"{self.name} | {self.genre.name}"
    
    def get_absolute_url(self):
        # Возвращает URL детальной страницы исполнителя
        return reverse('artist_detail', kwargs = {'artist_slug': self.slug})

    def save(self, *args, **kwargs):
        if not self.slug: 
            self.slug = slugify(self.name, lowercase=True)
        super().save(*args, **kwargs)
    
    class Meta:
        verbose_name = 'Исполнитель'
        verbose_name_plural = 'Исполнители'

# ❒ Модель для хранения информации о музыкальных альбомах
class Album(models.Model):
    name = models.CharField(max_length = 255, verbose_name = 'Название альбома')
    artist = models.ForeignKey(Artist, on_delete = models.CASCADE, verbose_name = 'Исполнитель')
    media_type = models.ForeignKey(MediaType, verbose_name = 'Тип медианосителя', on_delete = models.CASCADE)
    release_date = models.DateField(verbose_name = 'Дата релиза')
    genre = models.ForeignKey(Genre, on_delete = models.CASCADE, verbose_name = 'Жанр', blank = True, null = True)
    styles = models.ManyToManyField(Style, verbose_name = 'Стили', blank = True)
    tracklist = models.TextField(verbose_name = 'Трэклист', blank = True, null = True)
    description = models.TextField(verbose_name = 'Описание', default = 'Описание появится позже', blank = True, null = True) 
    label = models.ForeignKey(Label, on_delete = models.SET_NULL, verbose_name = 'Лейбл', blank = True, null = True)
    country = models.ForeignKey(Country, on_delete = models.SET_NULL, verbose_name = 'Страна выпуска', blank = True, null = True) 
    condition = models.CharField(max_length = 50, verbose_name = 'Состояние товара', blank = True, null = True,
                                 help_text = 'Например: Mint (идеальное), Near Mint (почти идеальное), Very Good (очень хорошее) и т.д.')
    article = models.CharField(max_length = 100, verbose_name = 'Артикул', unique = True)
    stock = models.PositiveIntegerField(default = 1, verbose_name = 'Наличие на складе')
    out_of_stock = models.BooleanField(default = False, verbose_name = "Нет в наличии", editable = False)
    offer_of_the_week = models.BooleanField(default = False, verbose_name = "Предложение недели")
    image = models.ImageField(upload_to = upload_function)
    slug = models.SlugField(blank = True, help_text = 'Оставьте пустым для автозаполнения')
    total_sold = models.PositiveIntegerField(default = 0, verbose_name='Продано всего', help_text = 'Общее количество проданных копий этого альбома (обновляется автоматически)', editable = False, blank = True)
    objects = AlbumManager()

    # Добавляем GenericRelation для связи с ImageGallery
    image_gallery = GenericRelation('ImageGallery', related_query_name = 'albums')

    format_quantity = models.CharField(max_length = 100, verbose_name = 'Количество носителей', blank = True, null = True,
                                       help_text = 'Примеры: "2xVinyl" (две виниловые пластинки), "1xCD" (один компакт-диск), "1xVinyl + 1xCD" (комбинированный набор)')
    format_type = models.CharField(max_length = 100, verbose_name = 'Тип формата', blank = True, null = True,
                                   help_text = 'Пример: LP (Long Play - полноформатный альбом), SP (Single Play - сингл), EP (Extended Play - мини альбом)')
    format_edition = models.CharField(max_length = 100, verbose_name = 'Издание', blank = True, null = True,
                                      help_text = 'Пример: Reissue (переиздание), Expanded Edition (расширенное издание), Limited Edition (ограниченное издание)')  
    format_color = models.CharField(max_length = 100, verbose_name = 'Цвет носителя', blank = True, null = True,
                                    help_text = 'Пример: White (белый), Black (чёрный), Transparent (прозрачный), Multicolor (многоцветный), или любой другой')  
    package_type = models.CharField(max_length = 100, verbose_name = 'Формат обложки', blank = True, null = True, help_text = 'Например: Jewel case, Digipak, Cardboard sleeve')
    
    is_explicit = models.BooleanField(default = False, verbose_name = 'Содержит нецензурную речь')
    has_autograph = models.BooleanField(default = False, verbose_name = 'С автографом')

    weight = models.PositiveIntegerField(verbose_name = 'Масса без упаковки, г', blank = True, null = True)

    width = models.PositiveIntegerField(verbose_name = 'Ширина, мм', blank = True, null = True)
    height = models.PositiveIntegerField(verbose_name = 'Высота, мм', blank = True, null = True)
    depth = models.PositiveIntegerField(verbose_name = 'Толщина/Глубина, мм', blank = True, null = True)

    def __str__(self):
        return f"{self.id} | {self.artist.name} | {self.name}"

    # Формирует строку с описанием формата альбома (например, "2xVinyl, LP, Reissue, White")
    def get_format(self):
        return ', '.join([
            str(part) for part in [
                self.format_quantity,
                self.format_type,
                self.format_edition,
                self.format_color
            ] if part
        ])
    
    def get_absolute_url(self):
        # Возвращает URL детальной страницы альбома
        return reverse('album_detail', kwargs = {'artist_slug': self.artist.slug, 'album_slug': self.slug})

    @property
    def ct_model(self):
        # Полезно для корзины, чтобы идентифицировать тип объекта как альбом
        return self._meta.model_name
    
    def save(self, *args, **kwargs):
        if not self.slug: 
            self.slug = slugify(self.name, lowercase=True)  
        super().save(*args, **kwargs)

    @property
    def current_price(self):
        # Возвращает цену из активного прайс-листа или 0, если её нет
        active_pricelist = PriceList.objects.filter(is_active = True).first()
        if active_pricelist:
            pricelist_item = self.items.filter(price_list = active_pricelist).first()
            return pricelist_item.price if pricelist_item else 0
        return 0
    
    @property
    def active_promotion(self):
        # Возвращает активную акцию для альбома, если она есть
        return self.promotions.filter(
            is_active = True,
            start_date__lte = timezone.now(),
            end_date__gte = timezone.now()
        ).first()

    @property
    def discounted_price(self):
        # Возвращает цену со скидкой, если есть активная акция
        if self.active_promotion:
            discount = self.current_price * (self.active_promotion.discount_percentage / Decimal('100.00'))
            discounted_price = self.current_price - discount
            return max(discounted_price, Decimal('0.00'))
        return self.current_price
    
    @property
    def dimensions_display(self):
        """Возвращает габариты в формате 10х125х140 мм"""
        if self.depth and self.width and self.height:
            return f"{self.depth}x{self.width}x{self.height}"
        return "Не указано"

    class Meta:
        verbose_name = 'Альбом'
        verbose_name_plural = 'Альбомы'

# ❒ Модель для хранения информации о прайс-листах 
class PriceList(models.Model):
    number = models.CharField(max_length = 50, unique = True, verbose_name = 'Номер прайс-листа') 
    start_date = models.DateField(verbose_name = 'Дата начала действия')
    end_date = models.DateField(blank = True, null = True, verbose_name = 'Дата окончания действия')
    is_active = models.BooleanField(default = True, verbose_name = 'Активен')

    def __str__(self):
        status = "Активен" if self.is_active else "Неактивен"
        return f'Прайс-лист №{self.number} от {self.start_date} ({status})'

    class Meta:
        verbose_name = 'Прайс-лист'
        verbose_name_plural = 'Прайс-листы'

# ❒ Хранит информацию о позициях в прайс-листе (цена для конкретного товара)
class PriceListItem(models.Model):
    price_list = models.ForeignKey('PriceList', on_delete = models.CASCADE, related_name = 'items', verbose_name = 'Прайс-лист')
    album = models.ForeignKey(Album, on_delete = models.CASCADE, verbose_name = 'Альбом', related_name = 'items')
    price = models.DecimalField(decimal_places = 2, max_digits = 10, verbose_name = 'Цена')

    def __str__(self):
        return f"{self.album} | {self.price} ({self.price_list.number})"

    class Meta:
        verbose_name = 'Позиция прайс-листа'
        verbose_name_plural = 'Позиции прайс-листа'
        unique_together = ('price_list', 'album')  # Один альбом — одна цена в прайс-листе

# ❒ Модель для хранения изображений, связанных с разными объектами (альбомами, артистами и т.д.)
class ImageGallery(models.Model):
    image = models.ImageField(upload_to = upload_function, verbose_name = 'Изображение')
    use_in_slider = models.BooleanField(default = False, verbose_name = 'Использовать в слайдере')
    
    # Универсальная связь позволяет ImageGallery хранить изображения для разных объектов (альбомов, артистов) в одной таблице
    content_type = models.ForeignKey(ContentType, on_delete = models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    def __str__(self):
        return f"Изображение для {self.content_object}"
    
    def image_url(self):
        # Отображает изображение в админке с помощью HTML-тега <img>
         return mark_safe(f'<img src = "{self.image.url}" width = "auto" height = "100px"')
    
    class Meta:
        verbose_name = 'Галерея изображений'
        verbose_name_plural = verbose_name

# ❒ Модель для группировки рекламных баннеров и слайдов
class PromoGroup(models.Model):
    name = models.CharField(max_length = 100, verbose_name = 'Название блока')
    slug = models.SlugField(unique = True, verbose_name = 'Slug (для вызова в шаблоне)')
    
    def get_images(self):
        ct = ContentType.objects.get_for_model(self)
        return ImageGallery.objects.filter(content_type = ct, object_id = self.id)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = 'Рекламный блок'
        verbose_name_plural = 'Рекламные блоки'

def check_stock_change(instance, **kwargs):
    # Проверяет наличие альбома на складе
    try:
        album = Album.objects.get(id = instance.id)
    except Album.DoesNotExist:
        return None
    instance.out_of_stock = True if not album.stock else False
