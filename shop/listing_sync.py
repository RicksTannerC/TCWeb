"""Keeping a listing and its product at the print supplier in step: send it, read its previews and sizes
back, match sizes to the supplier's blanks, and the catalogue lookups the listing editor needs.

Talks to the supplier only through the neutral port (tshirtbrand.core.fulfilment). It builds neutral
requests from the listing and writes neutral results onto it; a supplier's API shapes never appear here."""

from __future__ import annotations

import time

from django.utils import timezone

from tshirtbrand.bootstrap import get_supplier
from tshirtbrand.core.fulfilment.api import ProductSpec, SupplierError, VariantSpec

from .supplier_bridge import print_files_for


def missing_catalog_sizes(listing):
    """Sizes with no catalogue variant matched yet (needed to build a product)."""
    return [s.label for s in listing.sizes.all() if not s.printful_catalog_variant_id]


def sync_listing(listing, *, replace=False):
    """
    'Send to Printful': create the product at the supplier from a listing's artwork + sizes, store the
    returned ids, and move the listing out of 'draft' (it is still hidden until the curator publishes it).

    replace=True builds a brand-new product (fresh external ids, since the supplier wants those unique) and
    points the listing at it. The old product is left in the supplier's store untouched, for the curator to
    delete by hand. Returns the neutral ProductRecord.
    """
    from .models import Status

    supplier = get_supplier()
    # Each artwork link is signed fresh and short-lived on every call, so the files are built right before
    # the call rather than stored anywhere.
    files = print_files_for(listing)
    ext = f"{listing.slug}-r{int(time.time())}" if replace else listing.slug
    spec = ProductSpec(
        name=listing.design.title,
        external_id=ext,
        variants=tuple(
            VariantSpec(external_id=f"{ext}::{s.label}", catalog_variant_id=s.printful_catalog_variant_id or "",
                        retail_price=s.price, files=files)
            for s in listing.sizes.all()
        ),
    )
    record = supplier.create_product(spec, color=listing.color)
    listing.printful_product_id = record.product_id

    # A size's variant id belongs to ONE supplier product. On a re-send the old product's ids must not
    # survive (an order would be made from the old shirt), so clear them and fill in the new product's.
    listing.sizes.update(printful_variant_id="")
    for v in record.variants:
        listing.sizes.filter(label=v.external_id.split("::")[-1]).update(printful_variant_id=v.id)
    if not record.variants and listing.printful_product_id:
        # The create reply is only a summary (no per-size ids), so read the product back: a read-only call
        # on the product just created. If it fails the sizes stay blank (never stale) and Refresh sizes
        # from Printful fixes it.
        try:
            refresh_sync_variants(listing)
        except SupplierError:
            pass
    if listing.status == Status.DRAFT:
        listing.status = Status.HIDDEN
    listing.printful_sent_blueprint_id = listing.template.printful_blueprint_id
    listing.printful_sent_color = listing.color
    listing.printful_sent_placement = listing.effective_print_placement
    listing.printful_sent_prints = listing.print_signature()
    listing.save(update_fields=["printful_product_id", "status", "updated", "printful_sent_blueprint_id",
                                "printful_sent_color", "printful_sent_placement", "printful_sent_prints"])
    return record


def store_previews(listing, record):
    listing.printful_preview = [{"label": p.label, "url": p.url} for p in record.previews]
    listing.printful_preview_checked = timezone.now()
    listing.save(update_fields=["printful_preview", "printful_preview_checked"])
    return listing.printful_preview


def refresh_preview(listing):
    """Re-read this listing's product from the supplier (read-only) and keep its preview images.
    Returns how many were found."""
    if not listing.printful_product_id:
        raise SupplierError("This listing isn't connected to a Printful product yet.")
    record = get_supplier().get_product(listing.printful_product_id, color=listing.color)
    return len(store_previews(listing, record))


def refresh_sync_variants(listing):
    """Re-read this listing's product from the supplier (read-only) and store each size's real *product
    variant* id. Returns (matched labels, unmatched labels).

    Where the product holds several colors, only the listing's own color is used; a size that still
    matches more than one variant is left unmatched rather than guessed."""
    if not listing.printful_product_id:
        raise SupplierError("This listing isn't connected to a Printful product yet.")
    record = get_supplier().get_product(listing.printful_product_id, color=listing.color)
    store_previews(listing, record)

    by_label = {}
    for v in record.variants:
        if not v.size or not v.id:
            continue
        if listing.color and v.color and v.color.lower() != listing.color.lower():
            continue
        by_label.setdefault(v.size.lower(), []).append(v.id)

    matched, unmatched = [], []
    for s in listing.sizes.all():
        found = by_label.get(s.label.lower(), [])
        if len(found) == 1:
            s.printful_variant_id = found[0]
            s.save(update_fields=["printful_variant_id"])
            matched.append(s.label)
        else:
            unmatched.append(s.label)
    return matched, unmatched


def match_variants(blueprint_id, color, size_labels):
    """For a catalogue product, the supplier's variant id for each size label in `color`.
    Returns (matches {label: variant id}, unmatched [label], available_colors [str])."""
    m = get_supplier().match_sizes(blueprint_id, color, list(size_labels))
    return m.matches, list(m.unmatched), list(m.available_colors)


def _swatch_css(hex1, hex2):
    if hex1 and hex2 and hex2 != hex1:
        return f"linear-gradient(135deg, {hex1} 50%, {hex2} 50%)"
    return hex1


def catalog_color_options(blueprint_id):
    """Each color of a catalogue product for the listing's color picker: [{"name", "hex", "hex2",
    "swatch" (css background), "image"}], sorted by name."""
    if not blueprint_id:
        return []
    return [{"name": c.name, "hex": c.hex, "hex2": c.hex2, "image": c.image, "swatch": _swatch_css(c.hex, c.hex2)}
            for c in get_supplier().colors(blueprint_id)]


def search_catalog(query):
    """Catalogue search as the dicts the template's results partial reads."""
    return [{"id": p.id, "title": p.title, "model": p.model, "brand": p.brand}
            for p in get_supplier().search_catalog(query)]
