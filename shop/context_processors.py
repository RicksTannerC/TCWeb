from django.conf import settings
from django.urls import reverse

from .cart import Cart
from .console import Page


def cart(request):
    from .views import checkout_open

    c = Cart(request)
    return {"cart": c, "cart_count": len(c), "checkout_open": checkout_open()}


def footer_pages(request):
    return {
        "footer_pages": Page.objects.filter(
            status=Page.Status.LIVE, show_in_footer=True
        ).only("title", "slug", "footer_order")
    }


def site_urls(request):
    """Absolute link to the public shop, for console pages that may be served
    from the private console host (where the shop itself is not served)."""
    base = settings.SITE_BASE_URL.rstrip("/")
    return {"public_shop_url": base + reverse("shop:index"), "shop_legal_name": settings.SHOP_LEGAL_NAME}
