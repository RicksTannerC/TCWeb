from .cart import Cart
from .console import Page


def cart(request):
    c = Cart(request)
    return {"cart": c, "cart_count": len(c)}


def footer_pages(request):
    return {
        "footer_pages": Page.objects.filter(
            status=Page.Status.LIVE, show_in_footer=True
        ).only("title", "slug", "footer_order")
    }
