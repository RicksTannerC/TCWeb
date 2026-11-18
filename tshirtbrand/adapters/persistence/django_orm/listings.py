"""The catalogue context's listing store, on the Django ORM."""

from django.utils import timezone

from shop.models import Listing
from shop.supplier_bridge import print_files_for
from tshirtbrand.core.catalogue.api import ListingView, SizeView, Version


class DjangoListingRepository:
    def _get(self, listing_id):
        try:
            return Listing.objects.select_related("design", "template").get(pk=listing_id)
        except Listing.DoesNotExist as exc:
            raise LookupError(f"no listing {listing_id}") from exc

    def listing(self, listing_id):
        listing = self._get(listing_id)
        return ListingView(
            id=listing.id, slug=listing.slug, title=listing.design.title, color=listing.color,
            product_id=listing.printful_product_id, status=listing.status,
            sizes=tuple(SizeView(label=s.label, price=s.price, catalog_variant_id=s.printful_catalog_variant_id or "",
                                 variant_id=s.printful_variant_id or "") for s in listing.sizes.all()),
            version=Version(listing.version_whole, listing.version_front, listing.version_back),
            changes=listing.changes_since_sent(),
        )

    def print_files(self, listing_id):
        return print_files_for(self._get(listing_id))

    def set_product(self, listing_id, product_id):
        listing = self._get(listing_id)
        listing.printful_product_id = product_id
        listing.save(update_fields=["printful_product_id", "updated"])

    def set_version(self, listing_id, version):
        listing = self._get(listing_id)
        listing.version_whole, listing.version_front, listing.version_back = version.whole, version.front, version.back
        listing.save(update_fields=["version_whole", "version_front", "version_back", "updated"])

    def clear_variant_ids(self, listing_id):
        self._get(listing_id).sizes.update(printful_variant_id="")

    def set_variant_ids(self, listing_id, ids_by_label):
        listing = self._get(listing_id)
        for label, variant_id in ids_by_label.items():
            listing.sizes.filter(label=label).update(printful_variant_id=variant_id)

    def store_previews(self, listing_id, previews):
        listing = self._get(listing_id)
        listing.printful_preview = [{"label": p.label, "url": p.url} for p in previews]
        listing.printful_preview_checked = timezone.now()
        listing.save(update_fields=["printful_preview", "printful_preview_checked"])

    def mark_sent(self, listing_id, status):
        listing = self._get(listing_id)
        listing.status = status
        listing.printful_sent_blueprint_id = listing.template.printful_blueprint_id
        listing.printful_sent_color = listing.color
        listing.printful_sent_placement = listing.effective_print_placement
        listing.printful_sent_prints = listing.print_signature()
        listing.printful_sent_front, listing.printful_sent_back = listing.print_signature_by_side()
        listing.save(update_fields=["status", "updated", "printful_sent_blueprint_id", "printful_sent_color",
                                    "printful_sent_placement", "printful_sent_prints", "printful_sent_front",
                                    "printful_sent_back"])
