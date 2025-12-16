from django.templatetags.static import static
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

from django.utils.safestring import mark_safe

UNFOLD = {
    "DASHBOARD_CALLBACK": "apps.accounts.views.dashboard_callback",
    "SITE_TITLE": mark_safe(
        """
        <div class="vaunire-title">
            <div class="vaunire-main">
                <span class="vaunire-logo">VAUNIRE</span>
                <span class="vaunire-dot">.</span>
                <span class="vaunire-admin">admin</span>
            </div>
            <div class="vaunire-subtitle">Музыкальный интернет-магазин</div>
        </div>
        """
    ),
    "SITE_HEADER": " ",
    "SITE_ICON": lambda request: static("images/logo/logo_admin.png"),
    "SITE_FAVICONS": [
        {
            "rel": "icon",
            "sizes": "48x48",
            "type": "image/svg+xml",
            "href": lambda request: static("images/logo/favicon.svg"),
        },
    ],
    "STYLES": [
        lambda request: static("css/admin_font.css"),
    ],
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": True,
        "navigation": [
            {
                "separator": False,
                "collapsible": False,
                "items": [
                    {
                        "title": _("Информационная панель"),
                        "icon": "monitoring",
                        "link": reverse_lazy("admin:index"),
                    },
                ],
            },
            {
                "title": _("Справочники"),
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": _("Альбомы"),
                        "icon": "album",
                        "link": reverse_lazy("admin:catalog_album_changelist"),
                    },
                    {
                        "title": _("Исполнители"),
                        "icon": "artist",
                        "link": reverse_lazy("admin:catalog_artist_changelist"),
                    },
                    {
                        "title": _("Музыканты"),
                        "icon": "group",
                        "link": reverse_lazy("admin:catalog_member_changelist"),
                    },
                    {
                        "title": _("Жанры"),
                        "icon": "music_note",
                        "link": reverse_lazy("admin:catalog_genre_changelist"),
                    },
                    {
                        "title": _("Стили"),
                        "icon": "queue_music",
                        "link": reverse_lazy("admin:catalog_style_changelist"),
                    },
                    {
                        "title": _("Медианосители"),
                        "icon": "audio_video_receiver",
                        "link": reverse_lazy("admin:catalog_mediatype_changelist"),
                    },
                    {
                        "title": _("Лейблы"),
                        "icon": "instant_mix",
                        "link": reverse_lazy("admin:catalog_label_changelist"),
                    },
                    {
                        "title": _("Страны"),
                        "icon": "flag",
                        "link": reverse_lazy("admin:catalog_country_changelist"),
                    },
                    {
                        "title": _("Галерея изображений"),
                        "icon": "image",
                        "link": reverse_lazy("admin:catalog_imagegallery_changelist"),
                    },
                    {
                        "title": _("Покупатели"),
                        "icon": "groups",
                        "link": reverse_lazy("admin:accounts_customer_changelist"),
                    },
                    {
                        "title": _("Уведомления"),
                        "icon": "notifications_active",
                        "link": reverse_lazy("admin:accounts_notifications_changelist"),
                    },
                    {
                        "title": _("Рекламные блоки"),
                        "icon": "burst_mode", 
                        "link": reverse_lazy("admin:catalog_promogroup_changelist"),
                    },
                ],
            },
            {
                "title": _("Заказы и платежи"),
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": _("Заказы"),
                        "icon": "shopping_bag",
                        "link": reverse_lazy("admin:orders_order_changelist"),
                    },
                    {
                        "title": _("Платежи"),
                        "icon": "payment",
                        "link": reverse_lazy("admin:orders_payment_changelist"),
                    },
                    {
                        "title": _("Заявки на возврат"),
                        "icon": "assignment_return",
                        "link": reverse_lazy("admin:orders_returnrequest_changelist"),
                    },
                ],
            },
            {
                "title": _("Прайс-листы"),
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": _("Прайс-листы"),
                        "icon": "currency_ruble",
                        "link": reverse_lazy("admin:catalog_pricelist_changelist"),
                    },
                    {
                        "title": _("Позиции прайс-листа"),
                        "icon": "menu",
                        "link": reverse_lazy("admin:catalog_pricelistitem_changelist"),
                    },
                ],
            },
            {
                "title": _("Корзина"),
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": _("Корзины"),
                        "icon": "shopping_cart",
                        "link": reverse_lazy("admin:cart_cart_changelist"),
                    },
                    {
                        "title": _("Продукты корзины"),
                        "icon": "add_shopping_cart",
                        "link": reverse_lazy("admin:cart_cartproduct_changelist"),
                    },
                ],
            },
            {
                "title": _("Акции и промокоды"),
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": _("Акции"),
                        "icon": "shoppingmode",
                        "link": reverse_lazy("admin:promotions_promotion_changelist"),
                    },
                    {
                        "title": _("Промокоды"),
                        "icon": "checkbook",
                        "link": reverse_lazy("admin:promotions_promocode_changelist"),
                    },
                ],
            },
        ],
    },
    "COLORS": {
        "primary": {
            "50": "239 246 255",    # bg-blue-50
            "100": "219 234 254",   # bg-blue-100
            "200": "191 219 254",   # bg-blue-200
            "300": "147 197 253",   # bg-blue-300
            "400": "96 165 250",    # bg-blue-400
            "500": "59 130 246",    # bg-blue-500 (основной)
            "600": "37 99 235",     # bg-blue-600 
            "700": "29 78 216",     # bg-blue-700
            "800": "30 64 175",     # bg-blue-800
            "900": "30 58 138",     # bg-blue-900
        },
    },
}