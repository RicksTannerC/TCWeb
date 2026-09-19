"""
The curator's console — dashboard, listings intake + editor, collections,
pricing workspace, books, messages. Staff-only. The order desk lives in
manage_views.py; everything else is here.
"""

import logging
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Count, Sum
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_POST
from PIL import Image

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

logger = logging.getLogger(__name__)


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
        "has_templates": ProductTemplate.objects.exists(),
    })


def _is_image(f):
    """True if Pillow can open the upload as a raster image."""
    try:
        Image.open(f).verify()
        return True
    except Exception:  # noqa: BLE001 - anything unreadable is "not an image"
        return False
    finally:
        f.seek(0)


def _title_from_filename(name):
    stem = name.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").strip().title()
    return stem[:120] or "Untitled"


@staff_member_required
@require_POST
def listings_intake(request):
    """Drop one or more print-ready files -> a draft Design + a listing per template.

    Each file is all-or-nothing: if anything fails for one file, nothing is kept
    for it (no half-made design, no stray file on disk) and the rest carry on.
    """
    files = request.FILES.getlist("artwork")
    if not files:
        messages.error(request, "No files received.")
        return redirect("shop:manage_listings")

    templates = [
        t for t in (
            ProductTemplate.objects.filter(product_type=ProductType.TEE).first(),
            ProductTemplate.objects.filter(product_type=ProductType.STICKER).first(),
        ) if t
    ]
    if not templates:
        messages.error(
            request,
            "Set up a product template first. Uploads create a listing from each template "
            "(garment, costs, sizes), and there are none yet. Nothing was uploaded.",
        )
        return redirect("shop:manage_templates")

    made, duplicates, not_images, failed = 0, 0, [], []
    for f in files:
        if not _is_image(f):
            not_images.append(f.name)
            continue
        title = _title_from_filename(f.name)
        duplicate = Design.objects.filter(title=title).exists()
        saved_name = None
        try:
            with transaction.atomic():
                design = Design.objects.create(title=title, story="")
                design.artwork.save(f.name, f, save=True)
                saved_name = design.artwork.name
                for tpl in templates:
                    listing = Listing.objects.create(
                        design=design, template=tpl, product_type=tpl.product_type,
                        status=Status.DRAFT, base_cost=tpl.base_cost, shipping_est=tpl.shipping_est,
                    )
                    listing.price = listing.suggested_price
                    listing.save(update_fields=["price"])
                    for i, size in enumerate(tpl.default_sizes or []):
                        ListingSize.objects.create(
                            listing=listing, label=size["label"],
                            width_in=size.get("width_in"), height_in=size.get("height_in"), sort_order=i,
                        )
        except Exception:  # noqa: BLE001 - report it, keep going with the other files
            logger.exception("Design intake failed for %r", f.name)
            failed.append(f.name)
            if saved_name:  # the database rolled back; don't leave the file behind
                default_storage.delete(saved_name)
            continue
        made += 1
        duplicates += duplicate

    if made:
        messages.success(request, f"Created {made} draft design(s). Not connected to Printful yet.")
    if duplicates:
        messages.info(
            request,
            f"{duplicates} of them share a title with an existing design and were added as separate "
            "designs. Rename them in the editor if you want them told apart.",
        )
    if not_images:
        messages.error(
            request,
            "Skipped (not a PNG, JPEG or WebP image the server can read): " + ", ".join(not_images) + ".",
        )
    if failed:
        messages.error(
            request,
            "Couldn't add: " + ", ".join(failed) + ". Nothing was saved for those; the error is in the server log.",
        )
    if any(t.landed_cost == 0 for t in templates):
        messages.warning(
            request,
            "A template has $0 costs, so its new listings are priced at $0. Set the costs on the Templates page.",
        )
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


# ------------------------------------------------------------------ product templates

TEE_CEILING = Decimal("40")


def parse_sizes(text):
    """Parse the size box into the JSON stored on a template.

    One size per line: "label", "label, width", or "label, width, height"
    (inches). Returns (sizes, error); error is a message or None.
    """
    sizes = []
    for n, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) > 3 or not parts[0]:
            return None, f"Size line {n} (\u201c{line}\u201d): use  label, width, height  (width and height optional)."
        label = parts[0]
        if len(label) > 16:
            return None, f"Size line {n}: the label is longer than 16 characters."
        entry = {"label": label}
        for key, value in zip(("width_in", "height_in"), parts[1:]):
            if not value:
                continue
            try:
                number = Decimal(value)
            except InvalidOperation:
                return None, f"Size line {n} (\u201c{line}\u201d): \u201c{value}\u201d isn't a number."
            if not (0 < number < 1000):
                return None, f"Size line {n}: measurements must be between 0 and 1000 inches."
            entry[key] = int(number) if number == number.to_integral() else float(number)
        sizes.append(entry)
    if not sizes:
        return None, "Add at least one size (for example  M, 20, 29 )."
    labels = [x["label"].lower() for x in sizes]
    if len(labels) != len(set(labels)):
        return None, "Two sizes have the same label."
    return sizes, None


def format_sizes(sizes):
    lines = []
    for s in sizes or []:
        bits = [str(s.get("label", ""))]
        for key in ("width_in", "height_in"):
            if s.get(key) is not None:
                bits.append(str(s[key]))
        lines.append(", ".join(bits))
    return "\n".join(lines)


def _money(value):
    try:
        amount = Decimal(str(value).strip().lstrip("$") or "0")
    except InvalidOperation:
        return None
    return amount if 0 <= amount < 100000 else None


@staff_member_required
def product_templates(request):
    rows = []
    for t in ProductTemplate.objects.annotate(n_listings=Count("listings")):
        warnings = []
        if t.landed_cost == 0:
            warnings.append("Costs are $0, so listings would be priced at $0.")
        if t.product_type == ProductType.TEE and t.suggested_price > TEE_CEILING:
            warnings.append(f"Suggested price is over the ${TEE_CEILING} tee ceiling.")
        if not t.default_sizes:
            warnings.append("No sizes.")
        rows.append({"t": t, "warnings": warnings})
    used_types = set(ProductTemplate.objects.values_list("product_type", flat=True))
    return render(request, "shop/manage/templates.html", {
        "rows": rows,
        "ceiling": TEE_CEILING,
        "missing": [label for value, label in ProductType.choices
                    if value in (ProductType.TEE, ProductType.STICKER) and value not in used_types],
    })


@staff_member_required
def product_template_edit(request, pk=None):
    tpl = get_object_or_404(ProductTemplate, pk=pk) if pk else None
    form = {
        "name": tpl.name if tpl else "",
        "product_type": tpl.product_type if tpl else ProductType.TEE,
        "base_cost": tpl.base_cost if tpl else "",
        "shipping_est": tpl.shipping_est if tpl else "",
        "print_placement": tpl.print_placement if tpl else "",
        "printful_blueprint_id": tpl.printful_blueprint_id if tpl else "",
        "printful_provider_id": tpl.printful_provider_id if tpl else "",
        "sizes": format_sizes(tpl.default_sizes) if tpl else "",
    }
    errors = []

    if request.method == "POST":
        form = {k: request.POST.get(k, "").strip() for k in
                ("name", "product_type", "base_cost", "shipping_est", "print_placement",
                 "printful_blueprint_id", "printful_provider_id")}
        form["sizes"] = request.POST.get("sizes", "")

        if not form["name"]:
            errors.append("Give the template a name.")
        elif ProductTemplate.objects.filter(name__iexact=form["name"]).exclude(pk=pk).exists():
            errors.append("Another template already has that name.")
        if form["product_type"] not in ProductType.values:
            errors.append("Pick a product type.")
        base = _money(form["base_cost"])
        ship = _money(form["shipping_est"])
        if base is None:
            errors.append("Base cost must be a dollar amount, like 11.00.")
        if ship is None:
            errors.append("Shipping estimate must be a dollar amount, like 5.00.")
        sizes, size_error = parse_sizes(form["sizes"])
        if size_error:
            errors.append(size_error)

        if not errors:
            tpl = tpl or ProductTemplate()
            tpl.name = form["name"][:80]
            tpl.product_type = form["product_type"]
            tpl.base_cost, tpl.shipping_est = base, ship
            tpl.print_placement = form["print_placement"][:40]
            tpl.printful_blueprint_id = form["printful_blueprint_id"][:40]
            tpl.printful_provider_id = form["printful_provider_id"][:40]
            tpl.default_sizes = sizes
            tpl.save()
            messages.success(request, f"Saved template \u201c{tpl.name}\u201d. It applies to new uploads; existing listings keep their own values.")
            return redirect("shop:manage_templates")

    return render(request, "shop/manage/template_edit.html", {
        "tpl": tpl,
        "form": form,
        "errors": errors,
        "types": ProductType.choices,
        "n_listings": tpl.listings.count() if tpl and tpl.pk else 0,
    })


@staff_member_required
@require_POST
def product_template_delete(request, pk):
    tpl = get_object_or_404(ProductTemplate, pk=pk)
    try:
        name = tpl.name
        tpl.delete()
    except ProtectedError:
        messages.error(request, f"\u201c{tpl.name}\u201d is used by existing listings, so it can't be deleted.")
        return redirect("shop:manage_templates")
    messages.success(request, f"Deleted template \u201c{name}\u201d.")
    return redirect("shop:manage_templates")


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
