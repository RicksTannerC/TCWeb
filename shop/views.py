from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .cart import Cart
from .models import Listing, ListingSize, ProductType, Status


def _live_tees(query=""):
    qs = (
        Listing.objects.filter(status=Status.LIVE, product_type=ProductType.TEE)
        .select_related("design")
        .prefetch_related("images", "design__tags")
    )
    if query:
        qs = qs.filter(
            Q(design__title__icontains=query)
            | Q(design__tags__name__icontains=query)
            | Q(color__icontains=query)
            | Q(product_type__icontains=query)
        ).distinct()
    return qs


def shop_index(request):
    query = request.GET.get("q", "").strip()
    tees = _live_tees(query)

    if request.htmx and request.GET.get("grid"):
        return render(request, "shop/_grid.html", {"tees": tees, "query": query})

    return render(request, "shop/shop.html", {"tees": tees, "query": query, "overlay": None})


def listing_detail(request, slug):
    listing = get_object_or_404(
        Listing.objects.select_related("design", "template", "collection").prefetch_related(
            "images", "sizes", "design__tags"
        ),
        slug=slug,
    )
    # Draft/hidden listings are reachable only with a direct link, never indexed.
    ctx = {"listing": listing, "sticker": listing.design.sticker_listing}

    if request.htmx:
        return render(request, "shop/_overlay.html", ctx)

    ctx.update({"tees": _live_tees(), "query": "", "overlay": listing})
    return render(request, "shop/shop.html", ctx)


def overlay_close(request):
    """Empties the overlay slot; htmx pushes the URL back to the grid."""
    return HttpResponse("")


@require_POST
def cart_add(request, listing_id):
    listing = get_object_or_404(Listing, id=listing_id, status=Status.LIVE)
    size_id = request.POST.get("size")
    size = get_object_or_404(ListingSize, id=size_id, listing=listing)

    cart = Cart(request)
    cart.add(listing, size)

    if request.htmx:
        return render(request, "shop/_added.html")

    messages.success(request, f"Added {listing.design.title} ({size.label}) to your cart.")
    return redirect("shop:cart_detail")


@require_POST
def cart_update(request):
    cart = Cart(request)
    listing_id = request.POST.get("listing")
    size_id = request.POST.get("size")
    try:
        quantity = int(request.POST.get("quantity", 1))
    except (TypeError, ValueError):
        quantity = 1
    cart.set_quantity(listing_id, size_id, quantity)
    return redirect("shop:cart_detail")


@require_POST
def cart_remove(request):
    cart = Cart(request)
    cart.remove(request.POST.get("listing"), request.POST.get("size"))
    return redirect("shop:cart_detail")


def cart_detail(request):
    return render(request, "shop/cart_detail.html", {"cart": Cart(request)})
