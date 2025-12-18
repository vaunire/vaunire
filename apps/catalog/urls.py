from django.urls import path

from .views import AlbumDetailView, ArtistDetailView, BaseView, OfferView, PrivacyPolicyView, CookiesView, search_view

urlpatterns = [
    path('', BaseView.as_view(), name = 'base'),
    path('search/', search_view, name = 'search'),

    path('legal/offer/', OfferView.as_view(), name='offer'),
    path('legal/privacy/', PrivacyPolicyView.as_view(), name='privacy'),
    path('legal/cookies/', CookiesView.as_view(), name='cookies'),

    path('<str:artist_slug>/', ArtistDetailView.as_view(), name = 'artist_detail'),
    path('<str:artist_slug>/<str:album_slug>/', AlbumDetailView.as_view(), name = 'album_detail'),
]