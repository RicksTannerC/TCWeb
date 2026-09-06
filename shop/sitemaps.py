from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from .console import Page
from .models import Listing, ProductType, Status


class StaticSitemap(Sitemap):
    priority = 0.6
    changefreq = "weekly"

    def items(self):
        return ["shop:landing", "shop:index"]

    def location(self, name):
        return reverse(name)


class ListingSitemap(Sitemap):
    priority = 0.8
    changefreq = "weekly"

    def items(self):
        return Listing.objects.filter(status=Status.LIVE, product_type=ProductType.TEE)

    def lastmod(self, obj):
        return obj.updated


class PageSitemap(Sitemap):
    priority = 0.4
    changefreq = "monthly"

    def items(self):
        return Page.objects.filter(status=Page.Status.LIVE)

    def lastmod(self, obj):
        return obj.updated


SITEMAPS = {
    "static": StaticSitemap,
    "listings": ListingSitemap,
    "pages": PageSitemap,
}
