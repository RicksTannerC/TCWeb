from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path

from shop.sitemaps import SITEMAPS
from shop.views import robots_txt

urlpatterns = [
    path("admin/", admin.site.urls),
    path("robots.txt", robots_txt),
    path("sitemap.xml", sitemap, {"sitemaps": SITEMAPS}, name="django.contrib.sitemaps.views.sitemap"),
    path("", include("shop.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
