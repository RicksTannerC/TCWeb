"""What the business does to keep a listing and its product at the print supplier in step: send it, and read its
previews and sizes back. The listing store and the supplier are handed in."""

from tshirtbrand.core.fulfilment.api import ProductSpec, SupplierError, VariantSpec

from .model import (
    label_of_variant, match_product_variants, next_version, product_external_id, product_name, variant_external_id,
)
from .ports import ListingRepository


class ProductDesk:
    def __init__(self, listings: ListingRepository, supplier):
        self.listings = listings
        self.supplier = supplier

    def send(self, listing_id, *, replace=False, stamp=0):
        """Send to the supplier: create the product from a listing's artwork and sizes, store the returned ids,
        and move the listing out of draft (it stays hidden until the curator publishes it).

        replace=True builds a brand-new product (fresh external ids, since the supplier wants those unique) and
        points the listing at it. The old product is left in the supplier's store untouched, for the curator to
        delete by hand. Returns the supplier's ProductRecord."""
        listing = self.listings.listing(listing_id)
        # Each artwork link is signed fresh and short-lived on every call, so the files are built right before
        # the call rather than stored anywhere.
        files = self.listings.print_files(listing_id)
        ext = product_external_id(listing.slug, replace, stamp)
        # The product's name carries a version so the copies in the supplier's store can be told apart (and the old
        # ones found and deleted). A rebuild moves it on according to what changed; the first send is 1.0.0.
        version = next_version(listing.version, listing.changes) if replace else listing.version
        spec = ProductSpec(
            name=product_name(listing.title, version),
            external_id=ext,
            variants=tuple(
                VariantSpec(external_id=variant_external_id(ext, s.label), catalog_variant_id=s.catalog_variant_id,
                            retail_price=s.price, files=files)
                for s in listing.sizes
            ),
        )
        record = self.supplier.create_product(spec, color=listing.color)
        self.listings.set_product(listing_id, record.product_id)
        self.listings.set_version(listing_id, version)

        # A size's variant id belongs to ONE supplier product. On a re-send the old product's ids must not survive
        # (an order would be made from the old shirt), so clear them and fill in the new product's.
        self.listings.clear_variant_ids(listing_id)
        self.listings.set_variant_ids(listing_id, {label_of_variant(v.external_id): v.id for v in record.variants})
        if not record.variants and record.product_id:
            # The create reply is only a summary (no per-size ids), so read the product back: a read-only call on
            # the product just created. If it fails the sizes stay blank (never stale) and Refresh sizes fixes it.
            try:
                self.refresh_variants(listing_id)
            except SupplierError:
                pass
        self.listings.mark_sent(listing_id, "hidden" if listing.status == "draft" else listing.status)
        return record

    def refresh_preview(self, listing_id):
        """Re-read the product from the supplier (read-only) and keep its preview images. Returns how many."""
        record = self._read(listing_id)[1]
        self.listings.store_previews(listing_id, record.previews)
        return len(record.previews)

    def refresh_variants(self, listing_id):
        """Re-read the product from the supplier (read-only) and store each size's real variant id. Returns
        (matched labels, unmatched labels)."""
        listing, record = self._read(listing_id)
        self.listings.store_previews(listing_id, record.previews)
        matched, unmatched = match_product_variants(record.variants, listing.color, [s.label for s in listing.sizes])
        self.listings.set_variant_ids(listing_id, matched)
        return list(matched), unmatched

    def _read(self, listing_id):
        listing = self.listings.listing(listing_id)
        if not listing.is_connected:
            raise SupplierError("This listing isn't connected to a Printful product yet.")
        return listing, self.supplier.get_product(listing.product_id, color=listing.color)
