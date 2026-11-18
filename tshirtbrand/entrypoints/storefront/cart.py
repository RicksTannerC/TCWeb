"""The storefront: the cart."""

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from shop.cart import Cart
from shop.models import Listing, ListingSize, Status


def _cart_response(request, feedback_template=None, feedback_ctx=None):
    """htmx: feedback fragment + out-of-band cart updates. else: redirect to cart."""
    if request.htmx:
        html = ""
        if feedback_template:
            html = render(request, feedback_template, feedback_ctx or {}).content.decode()
        html += render(request, "shop/_cart_oob.html").content.decode()
        return HttpResponse(html)
    return redirect("shop:cart_detail")


@require_POST
def cart_add(request, listing_id):
    listing = get_object_or_404(Listing, id=listing_id, status=Status.LIVE)
    size = get_object_or_404(ListingSize, id=request.POST.get("size"), listing=listing)
    Cart(request).add(listing, size)
    if not request.htmx:
        messages.success(request, f"Added {listing.design.title} ({size.label}) to your cart.")
    return _cart_response(request, "shop/_added.html")


@require_POST
def cart_update(request):
    try:
        quantity = int(request.POST.get("quantity", 1))
    except (TypeError, ValueError):
        quantity = 1
    Cart(request).set_quantity(request.POST.get("listing"), request.POST.get("size"), quantity)
    if request.htmx:
        return render(request, "shop/_cart_body.html", {"oob": True})
    return redirect("shop:cart_detail")


@require_POST
def cart_remove(request):
    Cart(request).remove(request.POST.get("listing"), request.POST.get("size"))
    if request.htmx and request.headers.get("HX-Target") == "cart-body":
        return render(request, "shop/_cart_body.html", {"oob": True})
    return _cart_response(request)


def cart_drawer(request):
    return render(request, "shop/_cart_drawer_body.html")


def cart_detail(request):
    return render(request, "shop/cart_detail.html")
