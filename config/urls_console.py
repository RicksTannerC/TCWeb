"""
URLconf for the private console host (settings.CONSOLE_HOST).

The console lives at the root here -- "/" is the dashboard, "/orders/" the order
queue, and so on -- and the Django admin stays at /admin/. The public patterns
are included only so every "shop:..." name still reverses (links in emails, the
"view live" links); HostRoutingMiddleware 404s any request that resolves to
them, so the shop itself is never served from this host.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path

from shop import urls as shop_urls


def robots_txt(request):
    return HttpResponse("User-agent: *\nDisallow: /\n", content_type="text/plain")


urlpatterns = [
    path("admin/", admin.site.urls),
    path("robots.txt", robots_txt),
    path("", include((shop_urls.console_patterns + shop_urls.public_patterns, "shop"))),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
