import os
from pathlib import Path

from django.conf import settings
from dotenv import load_dotenv

from .unfold_config import UNFOLD

# Загружаем переменные окружения из .env файла
load_dotenv()

# ==============================================================================
# ОСНОВНЫЕ НАСТРОЙКИ
# ==============================================================================

# Определяем базовую директорию проекта
BASE_DIR = Path(__file__).resolve().parent.parent

# Секретный ключ Django (должен быть в .env)
SECRET_KEY = os.getenv('SECRET_KEY')

# Режим отладки (True для разработки, False для продакшена)
DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'

# Разрешенные хосты
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', '').split(',')

# ==============================================================================
# ПОДКЛЮЧЕННЫЕ ПРИЛОЖЕНИЯ (INSTALLED APPS)
# ==============================================================================

INSTALLED_APPS = [
    # --- Unfold (Улучшенная админка) ---
    "unfold", 
    "unfold.contrib.filters", 
    "unfold.contrib.forms", 
    "unfold.contrib.inlines", 
    "unfold.contrib.import_export", 
    "unfold.contrib.guardian",  
    "unfold.contrib.simple_history",
    
    # --- Стандартные приложения Django ---
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.humanize',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # --- Сторонние библиотеки ---
    "tailwind", "_tailwind",  
    # Улучшенные выпадающие списки
    'django_select2',       

    # --- Локальные приложения ---
    'apps.accounts',   
    'apps.cart',       
    'apps.catalog',     
    'apps.orders',     
    'apps.promotions',  
]

# Дополнительные приложения для режима отладки
if DEBUG:
    INSTALLED_APPS += [
        "django_browser_reload", 
        "debug_toolbar",         
    ]

# ==============================================================================
# НАСТРОЙКИ TAILWIND CSS
# ==============================================================================

TAILWIND_APP_NAME = "_tailwind"
NPM_BIN_PATH = os.getenv('NPM_BIN_PATH', 'npm.cmd')

# ==============================================================================
# ПРОМЕЖУТОЧНОЕ ПО (MIDDLEWARE)
# ==============================================================================

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

if DEBUG:
    MIDDLEWARE += [
        "debug_toolbar.middleware.DebugToolbarMiddleware", 
        "django_browser_reload.middleware.BrowserReloadMiddleware",
    ]

# Настройки для Debug Toolbar
if DEBUG:
    INTERNAL_IPS = [
        "127.0.0.1",
    ]
    # Исправление для корректной работы JS на Windows
    import mimetypes
    mimetypes.add_type("application/javascript", ".js", True)

# ==============================================================================
# НАСТРОЙКИ URL И ШАБЛОНОВ
# ==============================================================================

ROOT_URLCONF = '_config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / "templates",], 
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.cart.context_processors.global_settings',
            ],
        },
    },
]

WSGI_APPLICATION = '_config.wsgi.application'

# ==============================================================================
# БАЗА ДАННЫХ
# ==============================================================================

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'HOST': os.getenv('POSTGRES_HOST', 'localhost'),
        'PORT': os.getenv('POSTGRES_PORT', 5432),
        'USER': os.getenv('POSTGRES_USER', 'postgres'),
        'PASSWORD': os.getenv('POSTGRES_PASSWORD', 'postgres'),
        'NAME': os.getenv('POSTGRES_DB', 'postgres'),
        'ATOMIC_REQUEST': True, 
    }
}

# ==============================================================================
# СИСТЕМА КЭШИРОВАНИЯ
# ==============================================================================

USE_REDIS = os.getenv('USE_REDIS', 'False').lower() == 'true'

if USE_REDIS:
    CACHES = {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': os.getenv('REDIS_LOCATION', 'redis://redis:6379/1'),
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            }
        }
    }
else:
    # Локальный кэш в памяти для разработки без Redis
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'unique-snowflake',
        }
    }

# ==============================================================================
# ВАЛИДАЦИЯ ПАРОЛЕЙ
# ==============================================================================

AUTH_PASSWORD_VALIDATORS = [
    { 'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator', },
]

# ==============================================================================
# ЛОКАЛИЗАЦИЯ И ЧАСОВЫЕ ПОЯСА
# ==============================================================================

LANGUAGE_CODE = os.getenv('LANGUAGE_CODE', 'en-US') 
TIME_ZONE = os.getenv('TIME_ZONE', 'UTC')           

USE_I18N = True
USE_TZ = True

# ==============================================================================
# СТАТИЧЕСКИЕ И МЕДИА ФАЙЛЫ
# ==============================================================================

STATIC_URL = 'static/' 
STATIC_ROOT = BASE_DIR / 'static'

STATICFILES_DIRS = [
    BASE_DIR / 'static_dev',
]

MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ==============================================================================
# ИНТЕГРАЦИИ
# ==============================================================================

# --- Stripe ---
STRIPE_PUBLIC_KEY = os.getenv('STRIPE_PUBLIC_KEY')
STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')

# --- Яндекс.Карты ---
YANDEX_MAPS_API_KEY = os.getenv('YANDEX_MAPS_API_KEY')
YANDEX_SUGGEST_API_KEY = os.getenv('YANDEX_SUGGEST_API_KEY')

# ==============================================================================
# ПРОЧИЕ НАСТРОЙКИ
# ==============================================================================

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
