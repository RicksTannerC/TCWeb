"""The storefront: the shop grid and a listing's page."""

from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render

from shop.models import Listing, Status
from tshirtbrand.core.catalogue.api import storefront_kinds


def live_tees(query=""):
    qs = (
        Listing.objects.filter(status=Status.LIVE, product_type__in=storefront_kinds())
        .select_related("design", "collection")
        .prefetch_related("images", "design__tags")
        .order_by("collection__is_base", "collection__name", "sort_order", "design__title")
    )
    if query:
        qs = qs.filter(
            Q(design__title__icontains=query)
            | Q(design__tags__name__icontains=query)
            | Q(color__icontains=query)
            | Q(product_type__icontains=query)
        ).distinct()
    return qs


def _grouped_tees(query=""):
    """[(collection|None, [listings])] — named collections first, the base last."""
    groups = {}
    order = []
    for tee in live_tees(query):
        col = tee.collection if (tee.collection and not tee.collection.is_base) else None
        key = col.id if col else 0
        if key not in groups:
            groups[key] = {"collection": col, "listings": []}
            order.append(key)
        groups[key]["listings"].append(tee)
    return [groups[k] for k in order]


def shop_index(request):
    query = request.GET.get("q", "").strip()
    groups = _grouped_tees(query)
    ctx = {"groups": groups, "query": query}
    if request.htmx and request.GET.get("grid"):
        return render(request, "shop/_grid.html", ctx)
    return render(request, "shop/shop.html", {**ctx, "overlay": None})


def listing_detail(request, slug):
    listing = get_object_or_404(
        Listing.objects.select_related("design", "template", "collection").prefetch_related(
            "images", "sizes", "design__tags"
        ),
        slug=slug,
    )
    ctx = {"listing": listing, "sticker": listing.design.sticker_listing}
    if request.htmx:
        return render(request, "shop/_overlay.html", ctx)
    ctx.update({"groups": _grouped_tees(), "query": "", "overlay": listing})
    return render(request, "shop/shop.html", ctx)


def overlay_close(request):
    return HttpResponse("")
