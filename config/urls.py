from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path

from shop.public_media import media_patterns
from shop.sitemaps import SITEMAPS
from shop.views import robots_txt

urlpatterns = [
    path("admin/", admin.site.urls),
    path("robots.txt", robots_txt),
    path("sitemap.xml", sitemap, {"sitemaps": SITEMAPS}, name="django.contrib.sitemaps.views.sitemap"),
    path("", include("shop.urls")),
]

# Public images (mockups etc.); originals are private and not served from here.
urlpatterns += media_patterns()
