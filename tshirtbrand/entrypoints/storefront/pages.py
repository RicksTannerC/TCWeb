"""The storefront: the front door, content pages and robots.txt."""

from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render

from shop.models import Collection
from tshirtbrand.entrypoints.storefront.catalogue import live_tees


def landing(request):
    cards = Collection.landing_cards()
    # Curator hasn't featured any collection yet: fall back to a few shirts
    # so the landing page is never empty.
    featured = [] if cards else live_tees()[:4]
    return render(request, "shop/landing.html", {"cards": cards, "featured": featured})


def page(request, slug):
    from shop.console import Page as PageModel

    qs = PageModel.objects.all()
    if not request.user.is_staff:
        qs = qs.filter(status=PageModel.Status.LIVE)
    page_obj = get_object_or_404(qs, slug=slug)
    return render(request, "shop/page.html", {"page": page_obj})


def robots_txt(request):
    host = request.build_absolute_uri("/").rstrip("/")
    lines = [
        "User-agent: *",
        "Disallow: /manage/",
        "Disallow: /admin/",
        "Disallow: /cart/",
        "Disallow: /checkout/",
        "Disallow: /order/",
        "Disallow: /unsubscribe/",
        "Disallow: /webhooks/",
        "",
        f"Sitemap: {host}/sitemap.xml",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain")
