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
    """The listing's print areas (main first) as neutral files."""
    out = []
    for entry in listing.print_file_entries():
        pos = entry.get("position")
        box = PrintBox(area_width=pos["area_width"], area_height=pos["area_height"], left=pos["left"],
                       top=pos["top"], width=pos["width"], height=pos["height"]) if pos else None
        out.append(PrintFile(placement=entry["type"], url=entry["url"], box=box))
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
