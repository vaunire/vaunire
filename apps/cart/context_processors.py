from django.conf import settings

def global_settings(request):
    return {
        'yandex_maps_api_key': settings.YANDEX_MAPS_API_KEY,
        'yandex_suggest_api_key': settings.YANDEX_SUGGEST_API_KEY,
    }