"""
The curator's console — dashboard, listings intake + editor, collections,
pricing workspace, books, messages. Staff-only. The order desk lives in
manage_views.py; everything else is here.
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from . import printful
from .console import ContactMessage, OverheadEntry, Page, VisitLog
from .models import (
    Collection,
    Design,
    Listing,
    ListingImage,
    ListingSize,
    ProductTemplate,
    ProductType,
    Status,
    Tag,
)
from .orders import Order, OrderStatus, Subscriber


# ------------------------------------------------------------------ dashboard

@staff_member_required
def dashboard(request):
    now = timezone.now()
    d7, d30 = now - timedelta(days=7), now - timedelta(days=30)

    paid = Order.objects.exclude(status=OrderStatus.PENDING_PAYMENT)
    completed = paid.exclude(status=OrderStatus.REFUNDED)

    def revenue(since):
        return completed.filter(created__gte=since).aggregate(s=Sum("grand_total"))["s"] or Decimal("0")

    from .orders import OrderItem
    top_designs = (
        OrderItem.objects.filter(order__in=completed)
        .values("design_title")
        .annotate(units=Sum("quantity"))
        .order_by("-units")[:6]
    )

    abandoned = Order.objects.filter(status=OrderStatus.PENDING_PAYMENT, created__gte=d30).count()
    checked_out = paid.filter(created__gte=d30).count()
    abandon_rate = (
        round(abandoned / (abandoned + checked_out) * 100) if (abandoned + checked_out) else 0
    )

    recent = list(completed.filter(created__gte=d30).prefetch_related("items"))
    avg_margin = (sum((o.margin for o in recent), Decimal("0")) / len(recent)) if recent else Decimal("0")

    sources = (
        VisitLog.objects.filter(created__gte=d30)
        .values("referrer_host", "utm_source")
        .annotate(n=Count("id"))
        .order_by("-n")[:6]
    )
    top_sources = []
    for s in sources:
        label = s["utm_source"] or s["referrer_host"] or "direct"
        top_sources.append({"label": label, "n": s["n"]})

    ctx = {
        "rev_7": revenue(d7),
        "rev_30": revenue(d30),
        "orders_7": completed.filter(created__gte=d7).count(),
        "orders_30": len(recent),
        "awaiting": paid.filter(status=OrderStatus.PENDING_APPROVAL).count(),
        "avg_margin": avg_margin.quantize(Decimal("0.01")),
        "top_designs": top_designs,
        "top_sources": top_sources,
        "visits_30": VisitLog.objects.filter(created__gte=d30).count(),
        "abandon_rate": abandon_rate,
        "subscribers": Subscriber.objects.filter(is_active=True).count(),
        "live_listings": Listing.objects.filter(status=Status.LIVE).count(),
        "draft_listings": Listing.objects.filter(status=Status.DRAFT).count(),
        "unread_messages": ContactMessage.objects.filter(handled=False).count(),
    }
    return render(request, "shop/manage/dashboard.html", ctx)


# ------------------------------------------------------------------ listings

@staff_member_required
def listings(request):
    status = request.GET.get("status", "")
    qs = Listing.objects.select_related("design", "collection").prefetch_related("images")
    if status in Status.values:
        qs = qs.filter(status=status)
    groups = {
        "Draft": qs.filter(status=Status.DRAFT),
        "Hidden": qs.filter(status=Status.HIDDEN),
        "Live": qs.filter(status=Status.LIVE),
    } if not status else {dict(Status.choices)[status]: qs}
    return render(request, "shop/manage/listings.html", {
        "groups": [(k, list(v)) for k, v in groups.items()],
        "status": status,
        "status_choices": Status.choices,
    })


@staff_member_required
@require_POST
def listings_intake(request):
    """Drop one or more print-ready files -> a draft Design + tee + sticker per file."""
    files = request.FILES.getlist("artwork")
    if not files:
        messages.error(request, "No files received.")
        return redirect("shop:manage_listings")

    tee_tpl = ProductTemplate.objects.filter(product_type=ProductType.TEE).first()
    sticker_tpl = ProductTemplate.objects.filter(product_type=ProductType.STICKER).first()
    made = 0
    for f in files:
        stem = f.name.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").strip().title()
        design = Design.objects.create(title=stem or "Untitled", story="", artwork=f)
        for tpl in [t for t in (tee_tpl, sticker_tpl) if t]:
            listing = Listing.objects.create(
                design=design, template=tpl, product_type=tpl.product_type,
                status=Status.DRAFT, base_cost=tpl.base_cost, shipping_est=tpl.shipping_est,
            )
            listing.price = listing.suggested_price
            listing.save(update_fields=["price"])
            for i, s in enumerate(tpl.default_sizes or []):
                ListingSize.objects.create(
                    listing=listing, label=s["label"],
                    width_in=s.get("width_in"), height_in=s.get("height_in"), sort_order=i,
                )
        made += 1
    messages.success(request, f"Created {made} draft design(s). Not connected to Printful yet.")
    return redirect("shop:manage_listings")


@staff_member_required
def listing_edit(request, pk):
    listing = get_object_or_404(
        Listing.objects.select_related("design", "template", "collection").prefetch_related(
            "sizes", "images", "design__tags"
        ),
        pk=pk,
    )
    if request.method == "POST":
        d = listing.design
        d.title = request.POST.get("title", d.title).strip() or d.title
        d.story = request.POST.get("story", "")
        d.save()
        d.tags.set(_tags_from_csv(request.POST.get("tags", "")))

        listing.color = request.POST.get("color", "")
        price = request.POST.get("price", "").strip()
        if price:
            listing.price = Decimal(price)
        listing.base_cost = Decimal(request.POST.get("base_cost", listing.base_cost) or 0)
        listing.shipping_est = Decimal(request.POST.get("shipping_est", listing.shipping_est) or 0)
        comp = request.POST.get("competitor_price", "").strip()
        listing.competitor_price = Decimal(comp) if comp else None
        cid = request.POST.get("collection", "")
        listing.collection = Collection.objects.filter(pk=cid).first() if cid else None
        listing.save()

        for size in listing.sizes.all():
            v = request.POST.get(f"size_price_{size.id}", "").strip()
            size.price_override = Decimal(v) if v else None
            size.save(update_fields=["price_override"])

        messages.success(request, "Saved.")
        return redirect("shop:manage_listing_edit", pk=pk)

    return render(request, "shop/manage/listing_edit.html", {
        "listing": listing,
        "collections": Collection.objects.all(),
        "all_tags": Tag.objects.all(),
        "image_kinds": ListingImage.Kind.choices,
        "is_mock": getattr(printful.get_client(), "is_mock", False),
    })


def _tags_from_csv(csv):
    out = []
    for name in [t.strip() for t in csv.split(",") if t.strip()]:
        out.append(Tag.objects.get_or_create(slug=slugify(name), defaults={"name": name})[0])
    return out


@staff_member_required
@require_POST
def listing_send_to_printful(request, pk):
    listing = get_object_or_404(Listing, pk=pk)
    try:
        printful.sync_listing(listing)
        messages.success(request, f"{listing.design.title} sent to Printful.")
    except printful.PrintfulError as exc:
        messages.error(request, str(exc))
    return redirect("shop:manage_listing_edit", pk=pk)


@staff_member_required
@require_POST
def listing_set_status(request, pk):
    listing = get_object_or_404(Listing, pk=pk)
    new = request.POST.get("status")
    if new in Status.values:
        if new == Status.LIVE and not listing.sizes.exists():
            messages.error(request, "Add at least one size before publishing.")
        else:
            listing.status = new
            listing.save(update_fields=["status", "updated"])
            messages.success(request, f"{listing.design.title} is now {listing.get_status_display()}.")
    return redirect(request.POST.get("next") or "shop:manage_listings")


@staff_member_required
@require_POST
def listing_add_image(request, pk):
    listing = get_object_or_404(Listing, pk=pk)
    for f in request.FILES.getlist("image"):
        ListingImage.objects.create(
            listing=listing, image=f, kind=request.POST.get("kind", ListingImage.Kind.LIFESTYLE),
            sort_order=listing.images.count(),
        )
    messages.success(request, "Image added.")
    return redirect("shop:manage_listing_edit", pk=pk)


@staff_member_required
@require_POST
def listing_generate_mockups(request, pk):
    listing = get_object_or_404(Listing, pk=pk)
    client = printful.get_client()
    if not getattr(client, "is_mock", False) and not listing.is_connected:
        messages.error(request, "Send the listing to Printful first.")
        return redirect("shop:manage_listing_edit", pk=pk)
    # Mock: fabricate mockup image rows. Real Printful mockup generation is
    # an async task — wired here, implemented when a key is present.
    result = client.create_sync_product({"sync_product": {"name": listing.design.title}, "sync_variants": []})
    for m in result.get("mockups", []):
        ListingImage.objects.get_or_create(
            listing=listing, alt_text=f"{listing.design.title} mockup",
            defaults={"kind": ListingImage.Kind.MOCKUP, "sort_order": 0},
        )
    messages.info(request, "Mockups requested (mock).")
    return redirect("shop:manage_listing_edit", pk=pk)


@staff_member_required
@require_POST
def image_delete(request, pk):
    img = get_object_or_404(ListingImage, pk=pk)
    listing_pk = img.listing_id
    img.delete()
    return redirect("shop:manage_listing_edit", pk=listing_pk)


# ------------------------------------------------------------------ collections

@staff_member_required
def collections(request):
    cols = Collection.objects.prefetch_related("listings").annotate(n=Count("listings"))
    return render(request, "shop/manage/collections.html", {"collections": cols})


@staff_member_required
def collection_edit(request, pk):
    col = get_object_or_404(Collection, pk=pk)
    if request.method == "POST":
        col.name = request.POST.get("name", col.name).strip() or col.name
        col.summary = request.POST.get("summary", "")
        col.status = request.POST.get("status", col.status)
        gl = request.POST.get("go_live_at", "").strip()
        col.go_live_at = gl or None
        col.save()
        listing_ids = request.POST.getlist("listings")
        Listing.objects.filter(collection=col).exclude(id__in=listing_ids).update(collection=None)
        Listing.objects.filter(id__in=listing_ids).update(collection=col)
        messages.success(request, "Collection saved.")
        return redirect("shop:manage_collection_edit", pk=pk)

    return render(request, "shop/manage/collection_edit.html", {
        "col": col,
        "member_ids": set(col.listings.values_list("id", flat=True)),
        "all_listings": Listing.objects.select_related("design").exclude(status=Status.DRAFT),
    })


@staff_member_required
@require_POST
def collection_toggle(request, pk):
    col = get_object_or_404(Collection, pk=pk)
    col.status = Status.HIDDEN if col.status == Status.LIVE else Status.LIVE
    col.save(update_fields=["status", "updated"])
    messages.success(request, f"{col.name} is now {col.get_status_display()}.")
    return redirect("shop:manage_collections")


@staff_member_required
@require_POST
def collection_create(request):
    name = request.POST.get("name", "").strip()
    if name:
        Collection.objects.create(name=name)
        messages.success(request, f"Created collection “{name}”.")
    return redirect("shop:manage_collections")


# ------------------------------------------------------------------ pricing

@staff_member_required
def pricing(request):
    rows = (
        Listing.objects.select_related("design")
        .exclude(status=Status.DRAFT)
        .order_by("product_type", "design__title")
    )
    return render(request, "shop/manage/pricing.html", {"rows": rows, "ceiling": Decimal("40")})


@staff_member_required
@require_POST
def pricing_update(request):
    for key, value in request.POST.items():
        if not key.startswith("price_"):
            continue
        try:
            listing = Listing.objects.get(pk=key.split("_", 1)[1])
        except (Listing.DoesNotExist, ValueError):
            continue
        v = value.strip()
        if v:
            listing.price = Decimal(v)
            listing.save(update_fields=["price", "updated"])
        comp = request.POST.get(f"comp_{listing.pk}", "").strip()
        listing.competitor_price = Decimal(comp) if comp else None
        listing.save(update_fields=["competitor_price"])
    messages.success(request, "Prices updated.")
    return redirect("shop:manage_pricing")


# ------------------------------------------------------------------ books

@staff_member_required
def books(request):
    completed = Order.objects.exclude(
        status__in=[OrderStatus.PENDING_PAYMENT, OrderStatus.REFUNDED]
    )
    refunded = Order.objects.filter(status=OrderStatus.REFUNDED)

    revenue = completed.aggregate(s=Sum("items_total"))["s"] or Decimal("0")
    tax_collected = completed.aggregate(s=Sum("tax_total"))["s"] or Decimal("0")
    refunds = refunded.aggregate(s=Sum("grand_total"))["s"] or Decimal("0")
    supplier_cost = sum((o.supplier_cost for o in completed), Decimal("0"))

    overhead_qs = OverheadEntry.objects.all()
    overhead_total = overhead_qs.aggregate(s=Sum("amount"))["s"] or Decimal("0")
    by_cat = overhead_qs.values("category").annotate(s=Sum("amount")).order_by("-s")

    net = revenue - supplier_cost - overhead_total - refunds

    return render(request, "shop/manage/books.html", {
        "revenue": revenue,
        "supplier_cost": supplier_cost,
        "overhead_total": overhead_total,
        "overhead_by_cat": by_cat,
        "refunds": refunds,
        "tax_collected": tax_collected,
        "net": net,
        "entries": overhead_qs[:50],
        "categories": OverheadEntry.Category.choices,
    })


@staff_member_required
@require_POST
def overhead_add(request):
    try:
        OverheadEntry.objects.create(
            incurred_on=request.POST.get("incurred_on") or timezone.now().date(),
            label=request.POST.get("label", "").strip() or "Expense",
            amount=Decimal(request.POST.get("amount", "0") or "0"),
            category=request.POST.get("category", OverheadEntry.Category.OTHER),
            note=request.POST.get("note", ""),
        )
        messages.success(request, "Expense logged.")
    except Exception:  # noqa: BLE001
        messages.error(request, "Couldn't log that — check the amount and date.")
    return redirect("shop:manage_books")


@staff_member_required
@require_POST
def overhead_delete(request, pk):
    OverheadEntry.objects.filter(pk=pk).delete()
    return redirect("shop:manage_books")


# ------------------------------------------------------------------ messages

@staff_member_required
def inbox(request):
    show = request.GET.get("show", "open")
    qs = ContactMessage.objects.select_related("order")
    if show == "open":
        qs = qs.filter(handled=False)
    return render(request, "shop/manage/inbox.html", {"messages_list": qs, "show": show})


@staff_member_required
@require_POST
def message_toggle(request, pk):
    m = get_object_or_404(ContactMessage, pk=pk)
    m.handled = not m.handled
    m.save(update_fields=["handled"])
    return redirect(request.POST.get("next") or "shop:manage_inbox")


# ------------------------------------------------------------------ pages

@staff_member_required
def pages(request):
    return render(request, "shop/manage/pages.html", {"pages": Page.objects.all()})


@staff_member_required
def page_edit(request, pk=None):
    page = get_object_or_404(Page, pk=pk) if pk else Page()
    if request.method == "POST":
        page.title = request.POST.get("title", "").strip() or "Untitled"
        if request.POST.get("slug", "").strip():
            page.slug = slugify(request.POST["slug"])
        page.body = request.POST.get("body", "")
        page.meta_description = request.POST.get("meta_description", "").strip()
        page.status = request.POST.get("status", Page.Status.DRAFT)
        page.show_in_footer = bool(request.POST.get("show_in_footer"))
        page.footer_order = int(request.POST.get("footer_order") or 0)
        page.save()
        messages.success(request, f"“{page.title}” saved.")
        return redirect("shop:manage_page_edit", pk=page.pk)
    return render(request, "shop/manage/page_edit.html", {"page": page, "statuses": Page.Status.choices})
