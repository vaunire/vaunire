class ImageUploadHelper:
    """ 
    Вспомогательный класс для генерации путей загрузки изображений
    Формирует путь: images/<model_lowercase>/<postfix>/<field_value>/<filename>.<ext>
    """
    FIELD_TO_COMBINE_MAP = {
        'defaults': {
            'upload_postfix': 'uploads'
        },
        'Member': {
            'field': 'slug',       
            'upload_postfix': 'members_images' 
        },
        'Artist': {
            'field': 'slug',            
            'upload_postfix': 'artists_images'  
        },
        'Album': {
            'field': 'slug',            
            'upload_postfix': 'albums_images'   
        },
        'ReturnRequest': {
            'field': 'order.customer.user.username',
            'upload_postfix': 'customer_returns'
        },
        'Customer': {
            'field': 'user.username', 
            'upload_postfix': 'avatars'
        },
        'PromoGroup': {
            'field': 'slug',
            'upload_postfix': 'banners' 
        }
    }

    def __init__(self, field_name_to_combine, instance, filename, upload_postfix):
        """
        Инициализация объекта для генерации пути
        """
        self.field_name_to_combine = field_name_to_combine
        self.instance = instance
        self.filename = filename
        self.extension = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''  # Извлекаем расширение файла (например, ".jpg")
        self.upload_postfix = upload_postfix

    @classmethod
    def get_field_to_combine_and_upload_postfix(cls, model_name):
        """
        Возвращает поле для формирования пути и постфикс папки по имени модели
        """
        # Получаем поле для генерации пути из настроек модели
        config = cls.FIELD_TO_COMBINE_MAP.get(model_name, {})
        field = config.get('field')
        # Получаем постфикс, если он есть, или используем значение по умолчанию
        postfix = config.get('upload_postfix', cls.FIELD_TO_COMBINE_MAP['defaults']['upload_postfix'])
       
        return field, postfix

    @property
    def path(self):
        """
        Генерирует полный путь для сохранения файла.
        Пример: images/member/members_images/thom_yorke/thom_yorke.jpg
        """
        field_value = "unknown"  # Значение по умолчанию на случай ошибки
        try:
            current = self.instance
            for part in self.field_name_to_combine.split('.'):
                if current is None:
                    break
                current = getattr(current, part)

            # Если всё прошло успешно — берём значение
            if current is not None:
                cleaned = str(current).strip()
                if cleaned: 
                    field_value = cleaned
        except (AttributeError, TypeError, ValueError):
            pass
        # Формируем имя файла: <значение_поля>.<расширение> 
        filename = f"{field_value}.{self.extension}" if self.extension else field_value
        model_name = self.instance.__class__.__name__.lower()
        
        # Формируем полный путь: images/<имя_модели>/<постфикс>/<значение_поля>/<имя_файла>
        return f"images/{model_name}/{self.upload_postfix}/{field_value}/{filename}"

def upload_function(instance, filename):
    """
    Универсальная функция для upload_to в ImageField/ FileField.
    Поддерживает GenericForeignKey через content_object.
    """
    # Если это generic relation — берём реальный объект
    if hasattr(instance, 'content_object') and instance.content_object:
        instance = instance.content_object
    
    model_name = instance.__class__.__name__
    field, postfix = ImageUploadHelper.get_field_to_combine_and_upload_postfix(model_name)
    
    if not field:
        # Если модели нет в конфиге — кидаем в /uploads, чтобы избежать ошибки
        return f"images/{model_name}/uploads/{filename}"

    helper = ImageUploadHelper(field, instance, filename, postfix)
    return helper.path