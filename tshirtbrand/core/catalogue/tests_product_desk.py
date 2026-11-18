"""The listing/product use cases on their own, over an in-memory listing store and the in-memory supplier: sending a
listing, re-sending it, reading previews and sizes back. No database, no network."""

from decimal import Decimal

from django.test import SimpleTestCase

from tshirtbrand.adapters.suppliers.memory.supplier import MemorySupplier
from tshirtbrand.core.fulfilment.api import (
    PrintFile, Preview, ProductRecord, ProductVariant, SupplierError,
)

from . import api
from .api import ListingView, ProductDesk, SizeView


class MemoryListings:
    def __init__(self, sizes=("S", "M"), status="draft", product_id=""):
        self.view = ListingView(
            1, "pillars", "Pillars", "Black", product_id, status,
            tuple(SizeView(label, Decimal("40"), catalog_variant_id=f"cat-{label}") for label in sizes))
        self.previews, self.sent_status, self.files_asked = None, None, 0
        self.variant_ids = {s.label: s.variant_id for s in self.view.sizes}

    def listing(self, listing_id):
        sizes = tuple(SizeView(s.label, s.price, s.catalog_variant_id, self.variant_ids[s.label]) for s in self.view.sizes)
        return ListingView(self.view.id, self.view.slug, self.view.title, self.view.color, self.view.product_id,
                           self.view.status, sizes)

    def print_files(self, listing_id):
        self.files_asked += 1
        return (PrintFile("front", f"https://art.test/{self.files_asked}"),)

    def set_product(self, listing_id, product_id):
        self.view = ListingView(self.view.id, self.view.slug, self.view.title, self.view.color, product_id,
                                self.view.status, self.view.sizes)

    def clear_variant_ids(self, listing_id):
        self.variant_ids = {label: "" for label in self.variant_ids}

    def set_variant_ids(self, listing_id, ids_by_label):
        self.variant_ids.update(ids_by_label)

    def store_previews(self, listing_id, previews):
        self.previews = previews

    def mark_sent(self, listing_id, status):
        self.sent_status = status


class RecordingSupplier(MemorySupplier):
    """The in-memory supplier, noting what it was asked to create and able to answer with a canned product."""

    def __init__(self):
        super().__init__()
        self.created = []
        self.canned = None
        self.fail_read = False

    def create_product(self, spec, color=""):
        self.created.append(spec)
        return self.canned if self.canned is not None else super().create_product(spec, color)

    def get_product(self, product_id, color=""):
        if self.fail_read:
            raise SupplierError("down")
        return self.canned if self.canned is not None else super().get_product(product_id, color)


class RuleTests(SimpleTestCase):
    def test_a_replacement_gets_a_fresh_product_id(self):
        self.assertEqual(api.product_external_id("pillars"), "pillars")
        self.assertEqual(api.product_external_id("pillars", replace=True, stamp=99), "pillars-r99")

    def test_variant_ids_round_trip(self):
        self.assertEqual(api.label_of_variant(api.variant_external_id("pillars-r9", "2XL")), "2XL")

    def test_sizes_without_a_matched_blank_are_listed(self):
        view = ListingView(1, "s", "T", "", "", "draft", (SizeView("S", Decimal("1"), "c1"), SizeView("M", Decimal("1"))))
        self.assertEqual(api.missing_catalog_sizes(view), ["M"])

    def test_matching_uses_the_listings_own_colour_and_refuses_to_guess(self):
        variants = [ProductVariant("1", "x", "S", "Black"), ProductVariant("2", "x", "S", "Ivory"),
                    ProductVariant("3", "x", "M", "Black"), ProductVariant("4", "x", "M", "Black"),
                    ProductVariant("5", "x", "L", "Black"), ProductVariant("", "x", "XL", "Black"),
                    ProductVariant("7", "x", "", "Black")]
        matched, unmatched = api.match_product_variants(variants, "black", ["S", "M", "L", "XL", "2XL"])
        self.assertEqual(matched, {"S": "1", "L": "5"})                  # Ivory ignored; M matches twice
        self.assertEqual(unmatched, ["M", "XL", "2XL"])

    def test_with_no_colour_set_every_variant_counts(self):
        variants = [ProductVariant("1", "x", "S", "Black"), ProductVariant("2", "x", "S", "Ivory")]
        self.assertEqual(api.match_product_variants(variants, "", ["S"]), ({}, ["S"]))


class SendTests(SimpleTestCase):
    def setUp(self):
        self.listings, self.supplier = MemoryListings(), RecordingSupplier()
        self.desk = ProductDesk(self.listings, self.supplier)

    def test_sending_builds_the_product_from_the_listing_and_stores_the_ids(self):
        record = self.desk.send(1)
        spec = self.supplier.created[0]
        self.assertEqual((spec.name, spec.external_id), ("Pillars", "pillars"))
        self.assertEqual([(v.external_id, v.catalog_variant_id, v.retail_price) for v in spec.variants],
                         [("pillars::S", "cat-S", Decimal("40")), ("pillars::M", "cat-M", Decimal("40"))])
        self.assertTrue(all(v.files == spec.variants[0].files and v.files for v in spec.variants))
        self.assertEqual(self.listings.view.product_id, record.product_id)
        self.assertTrue(all(self.listings.variant_ids.values()))
        self.assertEqual(self.listings.sent_status, "hidden")   # out of draft, still not public

    def test_a_listing_already_out_of_draft_keeps_its_status(self):
        for status in ("hidden", "live"):
            listings = MemoryListings(status=status)
            ProductDesk(listings, RecordingSupplier()).send(1)
            self.assertEqual(listings.sent_status, status)

    def test_each_send_makes_fresh_artwork_links(self):
        self.desk.send(1)
        self.desk.send(1)
        self.assertEqual(self.listings.files_asked, 2)

    def test_a_replacement_is_a_new_product_and_forgets_the_old_ids(self):
        self.desk.send(1)
        self.listings.variant_ids["S"] = "stale-id"
        self.supplier.canned = ProductRecord("999", variants=(ProductVariant("new-M", "pillars-r5::M", "M", "Black"),))
        self.desk.send(1, replace=True, stamp=5)
        self.assertEqual(self.supplier.created[-1].external_id, "pillars-r5")
        self.assertEqual(self.listings.variant_ids, {"S": "", "M": "new-M"})   # S must not keep the old product's id
        self.assertEqual(self.listings.view.product_id, "999")

    def test_a_summary_only_reply_is_read_back_for_the_sizes_and_previews(self):
        self.supplier.created_reply = None
        summary = ProductRecord("555")
        full = ProductRecord("555", variants=(ProductVariant("v-S", "x", "S", "Black"), ProductVariant("v-M", "x", "M", "Black")),
                             previews=(Preview("Black", "https://img.test/a.jpg"),))
        calls = []
        self.supplier.create_product = lambda spec, color="": summary
        self.supplier.get_product = lambda pid, color="": calls.append(pid) or full
        self.desk.send(1)
        self.assertEqual(calls, ["555"])
        self.assertEqual(self.listings.variant_ids, {"S": "v-S", "M": "v-M"})
        self.assertEqual(self.listings.previews, full.previews)

    def test_if_the_read_back_fails_the_sizes_stay_blank_never_stale(self):
        self.supplier.create_product = lambda spec, color="": ProductRecord("555")
        self.supplier.fail_read = True
        self.supplier.get_product = lambda pid, color="": (_ for _ in ()).throw(SupplierError("down"))
        self.desk.send(1)
        self.assertEqual(self.listings.variant_ids, {"S": "", "M": ""})
        self.assertEqual(self.listings.sent_status, "hidden")

    def test_a_refusing_supplier_changes_nothing(self):
        self.supplier.create_product = lambda spec, color="": (_ for _ in ()).throw(SupplierError("no"))
        with self.assertRaises(SupplierError):
            self.desk.send(1)
        self.assertEqual((self.listings.view.product_id, self.listings.sent_status), ("", None))


class ReadBackTests(SimpleTestCase):
    def setUp(self):
        self.supplier = RecordingSupplier()
        self.supplier.canned = ProductRecord(
            "555", variants=(ProductVariant("v-S", "x", "S", "Black"), ProductVariant("v-M", "x", "M", "Ivory")),
            previews=(Preview("Black", "https://img.test/a.jpg"),))

    def desk(self, **kw):
        self.listings = MemoryListings(**kw)
        return ProductDesk(self.listings, self.supplier)

    def test_a_listing_not_on_the_supplier_cannot_be_read(self):
        for call in ("refresh_preview", "refresh_variants"):
            with self.assertRaisesMessage(SupplierError, "isn't connected"):
                getattr(self.desk(), call)(1)

    def test_refreshing_the_preview_keeps_the_images_and_counts_them(self):
        desk = self.desk(product_id="555")
        self.assertEqual(desk.refresh_preview(1), 1)
        self.assertEqual(self.listings.previews, self.supplier.canned.previews)

    def test_refreshing_sizes_reports_matched_and_unmatched_and_keeps_the_preview(self):
        desk = self.desk(product_id="555")
        self.assertEqual(desk.refresh_variants(1), (["S"], ["M"]))   # M exists only in another colour
        self.assertEqual(self.listings.variant_ids, {"S": "v-S", "M": ""})
        self.assertEqual(self.listings.previews, self.supplier.canned.previews)

    def test_a_supplier_error_on_read_passes_through(self):
        desk = self.desk(product_id="555")
        self.supplier.fail_read = True
        self.supplier.canned = None
        with self.assertRaisesMessage(SupplierError, "down"):
            desk.refresh_variants(1)
