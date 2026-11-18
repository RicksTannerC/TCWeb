"""The curator's console: product templates and collections (catalogue setup)."""

from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from shop import listing_sync
from shop.models import Collection, Listing, PrintPlacement, ProductTemplate, ProductType, Status
from tshirtbrand.core.catalogue import api as catalogue


# ------------------------------------------------------------------ product templates


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
        # a size row pasted from a spreadsheet is tab-separated; treat tabs like commas
        parts = [p.strip() for p in line.replace("\t", ",").split(",")]
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


def _template_rows():
    rows = []
    for t in ProductTemplate.objects.annotate(n_listings=Count("listings")):
        rows.append({"t": t, "warnings": t.warnings})
    return rows


@staff_member_required
def product_templates(request):
    """Old standalone URL: templates now live on the merged Catalogue setup page."""
    return redirect(reverse("shop:manage_catalogue_setup") + "#templates")


@staff_member_required
def product_template_edit(request, pk=None):
    tpl = get_object_or_404(ProductTemplate, pk=pk) if pk else None
    form = {
        "name": tpl.name if tpl else "",
        "product_type": tpl.product_type if tpl else ProductType.TEE,
        "base_cost": tpl.base_cost if tpl else "",
        "shipping_est": tpl.shipping_est if tpl else "",
        "print_placement": tpl.print_placement if tpl else PrintPlacement.FRONT,
        "printful_blueprint_id": tpl.printful_blueprint_id if tpl else "",
        "printful_blueprint_name": tpl.printful_blueprint_name if tpl else "",
        "printful_provider_id": tpl.printful_provider_id if tpl else "",
        "sizes": format_sizes(tpl.default_sizes) if tpl else "",
    }
    errors = []

    if request.method == "POST":
        form = {k: request.POST.get(k, "").strip() for k in
                ("name", "product_type", "base_cost", "shipping_est", "print_placement",
                 "printful_blueprint_id", "printful_blueprint_name", "printful_provider_id")}
        form["sizes"] = request.POST.get("sizes", "")

        if not form["name"]:
            errors.append("Give the template a name.")
        elif ProductTemplate.objects.filter(name__iexact=form["name"]).exclude(pk=pk).exists():
            errors.append("Another template already has that name.")
        if form["product_type"] not in ProductType.values:
            errors.append("Pick a product type.")
        if form["print_placement"] and form["print_placement"] not in PrintPlacement.values:
            errors.append("Pick a valid print placement.")
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
            tpl.printful_blueprint_name = form["printful_blueprint_name"][:160]
            tpl.printful_provider_id = form["printful_provider_id"][:40]
            tpl.default_sizes = sizes
            tpl.save()
            messages.success(request, f"Saved template \u201c{tpl.name}\u201d. It applies to new uploads; existing listings keep their own values.")
            return redirect(reverse("shop:manage_catalogue_setup") + "#templates")

    return render(request, "shop/manage/template_edit.html", {
        "tpl": tpl,
        "form": form,
        "errors": errors,
        "types": ProductType.choices,
        "placements": PrintPlacement.choices,
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
        return redirect(reverse("shop:manage_catalogue_setup") + "#templates")
    messages.success(request, f"Deleted template \u201c{name}\u201d.")
    return redirect(reverse("shop:manage_catalogue_setup") + "#templates")


@staff_member_required
def template_printful_search(request):
    """htmx: search Printful's real catalog by name, for picking a template's
    blueprint product. This is a real outbound call using PRINTFUL_API_KEY --
    made only when a curator types into this search box, on their own
    initiative, from their own signed-in console session."""
    q = request.GET.get("q", "")
    results = listing_sync.search_catalog(q)
    return render(request, "shop/manage/_printful_search_results.html", {"results": results, "q": q.strip()})




# ------------------------------------------------------------------ collections

def _collection_rows():
    return Collection.objects.prefetch_related("listings").annotate(n=Count("listings"))


@staff_member_required
def collections(request):
    """Old standalone URL: collections now live on the merged Catalogue setup page."""
    return redirect(reverse("shop:manage_catalogue_setup") + "#collections")


@staff_member_required
def catalogue_setup(request):
    """Templates + Collections, one page: both small, related setup tables that
    don't need their own top-level nav slot. Individual create/edit/delete
    actions keep their own focused sub-pages, reached from here."""
    used_types = set(ProductTemplate.objects.values_list("product_type", flat=True))
    return render(request, "shop/manage/catalogue_setup.html", {
        "rows": _template_rows(),
        "ceiling": catalogue.kind_for(ProductType.TEE).price_ceiling,
        "missing": [label for value, label in ProductType.choices
                    if value in (ProductType.TEE, ProductType.STICKER) and value not in used_types],
        "collections": _collection_rows(),
    })


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
    return redirect(reverse("shop:manage_catalogue_setup") + "#collections")


@staff_member_required
@require_POST
def collection_toggle_landing(request, pk):
    col = get_object_or_404(Collection, pk=pk)
    col.featured_on_landing = not col.featured_on_landing
    col.save(update_fields=["featured_on_landing", "updated"])
    if col.featured_on_landing and col.status != Status.LIVE:
        messages.warning(request, f"{col.name} will show on the landing page once it's published.")
    else:
        messages.success(request, f"{col.name} {'now shows' if col.featured_on_landing else 'no longer shows'} on the landing page.")
    return redirect(reverse("shop:manage_catalogue_setup") + "#collections")


@staff_member_required
@require_POST
def collection_create(request):
    name = request.POST.get("name", "").strip()
    if name:
        Collection.objects.create(name=name)
        messages.success(request, f"Created collection “{name}”.")
    return redirect(reverse("shop:manage_catalogue_setup") + "#collections")
