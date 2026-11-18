"""Keeping a listing and its product at the print supplier in step: send it, read its previews and sizes back,
match sizes to the supplier's blanks, and the catalogue lookups the listing editor needs.

The sequencing and rules live in tshirtbrand.core.catalogue (the ProductDesk use cases); bootstrap.get_product_desk()
wires them to the ORM and the current supplier. These functions take and return the Django listing the views work
with, refreshed after the use case has run. The catalogue lookups below only ask the supplier port."""

from __future__ import annotations

import time

from tshirtbrand.bootstrap import get_product_desk, get_supplier
from tshirtbrand.core.catalogue.api import missing_catalog_sizes as _missing_catalog_sizes


def _listing_view(listing):
    from tshirtbrand.adapters.persistence.django_orm.listings import DjangoListingRepository

    return DjangoListingRepository().listing(listing.pk)


def missing_catalog_sizes(listing):
    """Sizes with no catalogue variant matched yet (needed to build a product)."""
    return _missing_catalog_sizes(_listing_view(listing))


def sync_listing(listing, *, replace=False):
    """Send to the supplier: create the product from the listing's artwork and sizes, store the returned ids, and
    move the listing out of draft (it is still hidden until the curator publishes it). replace=True builds a
    brand-new product and leaves the old one for the curator to delete by hand. Returns the neutral ProductRecord."""
    record = get_product_desk().send(listing.pk, replace=replace, stamp=int(time.time()))
    listing.refresh_from_db()
    return record


def refresh_preview(listing):
    """Re-read this listing's product from the supplier (read-only) and keep its preview images. Returns how
    many were found."""
    found = get_product_desk().refresh_preview(listing.pk)
    listing.refresh_from_db()
    return found


def refresh_sync_variants(listing):
    """Re-read this listing's product from the supplier (read-only) and store each size's real variant id.
    Returns (matched labels, unmatched labels)."""
    result = get_product_desk().refresh_variants(listing.pk)
    listing.refresh_from_db()
    return result


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
