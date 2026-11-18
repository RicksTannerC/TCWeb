"""Turns shop models into the neutral requests the supplier port takes (and nothing else).

This is the Django-aware half of talking to a supplier: it reads orders, listings and sizes. The other
half, turning a neutral request into a particular supplier's API calls, lives in that supplier's adapter.
It is a stop on the way to the persistence adapter (docs/ARCHITECTURE.md, step 6)."""

from tshirtbrand.core.fulfilment.api import OrderLine, PrintBox, PrintFile, Recipient, SupplierError


def recipient_for(order):
    a = order.shipping_address or {}
    return Recipient(
        name=order.name, email=order.email, address1=a.get("line1", ""), address2=a.get("line2", ""),
        city=a.get("city", ""), region=a.get("state", ""), country=a.get("country", "US"),
        postal_code=a.get("postal_code", ""),
    )


def print_files_for(listing):
    """The listing's print areas (main first) as neutral files, each with its own freshly signed artwork link.

    A positioned raster print is built into the file itself: the link serves a full-print-area image with the
    art already placed, because Printful ignores the `position` of a store product's file and centres it.
    SVG art can't be composed here, so it goes with a box for the supplier to place (best effort). An area
    whose design has no artwork is skipped."""
    from .printful_delivery import build_delivery_url

    out = []
    for design, placement, layout in listing.print_jobs():
        composed = layout is not None and design.can_compose
        url = build_delivery_url(design, layout=layout if composed else None) if composed else design.print_file_url
        if not url:
            continue
        box = None
        if layout is not None and not composed:
            box = PrintBox(area_width=layout.area_width, area_height=layout.area_height, left=layout.left,
                           top=layout.top, width=layout.width, height=layout.height)
        out.append(PrintFile(placement=placement, url=url, box=box))
    return tuple(out)


def line_for(item):
    """One order line for the size actually ordered.

    ListingSize.printful_variant_id holds a *sync* variant id once the listing has been sent to the
    supplier (sync_listing overwrites the catalog id), and a catalog variant id before that (Match sizes).
    Each goes in its own field of the neutral line."""
    listing = item.listing
    size = item.listing_size
    if listing and listing.is_connected:
        vid = (getattr(size, "printful_variant_id", "") or "") if size else ""
    else:
        vid = (getattr(size, "printful_catalog_variant_id", "") or "") if size else ""
    if not listing or not vid:
        raise SupplierError(
            f"{item.design_title} ({item.size_label}) has no Printful variant — "
            "open the listing and use 'Match sizes to Printful variants', then send it to Printful."
        )
    if listing.is_connected:
        return OrderLine(quantity=item.quantity, name=item.design_title, unit_price=item.unit_price,
                         product_variant_id=str(vid))
    # not synced yet: order straight off the catalog variant, with the art attached
    return OrderLine(quantity=item.quantity, name=item.design_title, unit_price=item.unit_price,
                     catalog_variant_id=str(vid), files=print_files_for(listing))
