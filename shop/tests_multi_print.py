"""More than one print area on a listing: a large back print plus a small front
design. Mock/stub clients only -- nothing here talks to Printful."""

import os
import tempfile
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock
from urllib.parse import urlsplit

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings

from . import printful
from .fulfillment import _line
from .models import (
    Design, Listing, ListingPrint, ListingSize, PrintPlacement, PrintPosition, ProductTemplate, placement_payload,
)

def _png():
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGBA", (8, 8), (20, 120, 60, 255)).save(buf, "PNG")
    return buf.getvalue()


PNG = _png()


class PayloadMathTests(TestCase):
    def test_default_is_just_the_placement(self):
        self.assertEqual(placement_payload("back", 100, PrintPosition.CENTER), {"type": "back"})

    def test_small_scale_gets_a_position_box(self):
        p = placement_payload("front", 30, PrintPosition.CENTER)["position"]
        self.assertEqual((p["width"], p["height"]), (300, 300))

    def test_the_box_never_leaves_the_print_area(self):
        for pos in PrintPosition.values:
            for scale in (25, 30, 50, 75, 99):
                p = placement_payload("front", scale, pos)["position"]
                self.assertGreaterEqual(p["top"], 0, (pos, scale))
                self.assertGreaterEqual(p["left"], 0, (pos, scale))
                self.assertLessEqual(p["top"] + p["height"], p["area_height"], (pos, scale))
                self.assertLessEqual(p["left"] + p["width"], p["area_width"], (pos, scale))

    def test_upper_presets_sit_in_the_upper_corners(self):
        ul = placement_payload("front", 30, PrintPosition.TOP_LEFT)["position"]
        ur = placement_payload("front", 30, PrintPosition.TOP_RIGHT)["position"]
        self.assertLess(ul["left"], ur["left"])
        self.assertEqual(ul["top"], ur["top"])
        self.assertLess(ul["top"] + ul["height"] / 2, 500)  # above the vertical middle
        self.assertLess(ul["left"] + ul["width"] / 2, 500)  # left of the horizontal middle


class PrivateBase(TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.private = os.path.join(tmp.name, "private")
        self.enterContext(override_settings(
            MEDIA_ROOT=os.path.join(tmp.name, "public"), PRIVATE_MEDIA_ROOT=self.private, STAFF_2FA_REQUIRED=False))
        self.c = Client()
        self.c.force_login(get_user_model().objects.create_user("cur", password="x-12345-yz", is_staff=True))
        self.tpl = ProductTemplate.objects.create(name="Tee", product_type="tee", print_placement="front",
                                                  printful_blueprint_id="586")

    def files(self):
        return [f for _, _, fs in os.walk(self.private) for f in fs]

    def design(self, title="Wanderer", art=True):
        d = Design.objects.create(title=title)
        if art:
            d.artwork.save(f"{title.lower()}.png", ContentFile(PNG), save=True)
        return d

    def listing(self, placement="back", **kw):
        listing = Listing.objects.create(design=self.design(), template=self.tpl, product_type="tee",
                                         print_placement=placement, color="Black", **kw)
        ListingSize.objects.create(listing=listing, label="M", printful_catalog_variant_id="4012")
        return listing

    def url(self, listing, suffix=""):
        return f"/manage/listings/{listing.pk}/{suffix}"


class EntriesTests(PrivateBase):
    def test_a_listing_with_no_extras_sends_one_file(self):
        entries = self.listing().print_file_entries()
        self.assertEqual([e["type"] for e in entries], ["back"])

    def test_main_and_extra_each_get_their_own_type_position_and_artwork_link(self):
        listing = self.listing(placement="back")
        logo = self.design("Logo")
        ListingPrint.objects.create(listing=listing, placement="front", design=logo, scale_pct=30,
                                    position=PrintPosition.TOP_LEFT)
        main, extra = listing.print_file_entries()
        self.assertEqual((main["type"], extra["type"]), ("back", "front"))
        self.assertNotIn("position", main)
        self.assertEqual(extra["position"]["width"], 300)
        self.assertNotEqual(main["url"], extra["url"])
        self.assertIn(f"/{logo.pk}/", extra["url"])
        self.assertIn(f"/{listing.design.pk}/", main["url"])

    def test_extra_without_its_own_design_reuses_the_main_artwork(self):
        listing = self.listing(placement="back")
        ListingPrint.objects.create(listing=listing, placement="front", scale_pct=30)
        main, extra = listing.print_file_entries()
        self.assertIn(f"/{listing.design.pk}/", extra["url"])

    def test_an_extra_whose_design_has_no_artwork_is_skipped(self):
        listing = self.listing(placement="back")
        ListingPrint.objects.create(listing=listing, placement="front", design=self.design("Empty", art=False))
        self.assertEqual([e["type"] for e in listing.print_file_entries()], ["back"])

    def test_an_extra_clashing_with_the_main_placement_is_never_sent(self):
        listing = self.listing(placement="back")
        ListingPrint.objects.create(listing=listing, placement="front", scale_pct=30)
        listing.print_placement = "front"  # main moves onto the extra's side
        listing.save()
        self.assertEqual([e["type"] for e in listing.print_file_entries()], ["front"])
        self.assertEqual(len(listing.print_conflicts), 1)

    def test_the_artwork_links_actually_serve_each_file(self):
        listing = self.listing(placement="back")
        ListingPrint.objects.create(listing=listing, placement="front", design=self.design("Logo"))
        for e in listing.print_file_entries():
            r = Client().get(urlsplit(e["url"]).path)
            self.assertEqual(r.status_code, 200)
            r.close()


class SendAndOrderTests(PrivateBase):
    def test_sync_listing_sends_both_files_on_every_variant(self):
        listing = self.listing(placement="back")
        ListingPrint.objects.create(listing=listing, placement="front", design=self.design("Logo"),
                                    scale_pct=30, position=PrintPosition.TOP_LEFT)
        client = mock.MagicMock(is_mock=False)
        client.create_sync_product.return_value = {"sync_product": {"id": 9}, "sync_variants": []}
        with mock.patch.object(printful, "get_client", return_value=client):
            printful.sync_listing(listing)
        files = client.create_sync_product.call_args[0][0]["sync_variants"][0]["files"]
        self.assertEqual(sorted(f["type"] for f in files), ["back", "front"])
        self.assertEqual(len({f["url"] for f in files}), 2)

    def test_sending_records_the_layout_so_a_later_change_is_noticed(self):
        listing = self.listing(placement="back")
        client = mock.MagicMock(is_mock=False)
        client.create_sync_product.return_value = {"sync_product": {"id": 9}, "sync_variants": []}
        with mock.patch.object(printful, "get_client", return_value=client):
            printful.sync_listing(listing)
        listing.refresh_from_db()
        self.assertEqual(listing.printful_changes_not_sent, [])
        ListingPrint.objects.create(listing=listing, placement="front", scale_pct=30)
        self.assertTrue(any("print areas" in c for c in listing.printful_changes_not_sent))

    def test_changing_size_or_position_of_an_extra_is_noticed_too(self):
        listing = self.listing(placement="back")
        extra = ListingPrint.objects.create(listing=listing, placement="front", scale_pct=30)
        listing.printful_product_id = "9"
        listing.printful_sent_prints = listing.print_signature()
        listing.save()
        self.assertEqual(listing.printful_changes_not_sent, [])
        extra.scale_pct = 50
        extra.save()
        listing = Listing.objects.get(pk=listing.pk)
        self.assertTrue(listing.printful_changes_not_sent)

    def test_an_order_for_an_unsent_listing_carries_every_print_area(self):
        listing = self.listing(placement="back")
        ListingPrint.objects.create(listing=listing, placement="front", design=self.design("Logo"), scale_pct=30)
        size = listing.sizes.get()
        item = SimpleNamespace(listing=listing, listing_size=size, size_label="M", quantity=1,
                               design_title="Wanderer", unit_price=Decimal("40"))
        line = _line(item)
        self.assertEqual(sorted(f["type"] for f in line["files"]), ["back", "front"])


class AddEditRemoveViewTests(PrivateBase):
    def add(self, listing, **data):
        return self.c.post(self.url(listing, "prints/add/"), data, follow=True)

    def test_upload_a_small_front_design_for_a_back_print_listing(self):
        listing = self.listing(placement="back")
        r = self.add(listing, placement="front", position="top_left", scale_pct="30",
                     artwork=SimpleUploadedFile("chest.png", PNG, content_type="image/png"))
        p = listing.prints.get()
        self.assertEqual((p.placement, p.scale_pct, p.position), ("front", 30, "top_left"))
        self.assertIsNotNone(p.design)
        self.assertTrue(p.design.artwork)
        self.assertContains(r, "Added a front print")
        self.assertEqual(len(self.files()), 2)  # the main art plus the new one

    def test_reuse_an_existing_design(self):
        listing = self.listing(placement="back")
        logo = self.design("Logo")
        self.add(listing, placement="front", design=str(logo.pk))
        self.assertEqual(listing.prints.get().design, logo)

    def test_blank_choice_means_the_same_artwork(self):
        listing = self.listing(placement="back")
        self.add(listing, placement="front")
        self.assertIsNone(listing.prints.get().design)

    def test_a_design_without_artwork_is_refused(self):
        listing = self.listing(placement="back")
        empty = self.design("Empty", art=False)
        r = self.add(listing, placement="front", design=str(empty.pk))
        self.assertEqual(listing.prints.count(), 0)
        self.assertContains(r, "no artwork")

    def test_garbage_upload_is_refused_and_leaves_nothing_behind(self):
        listing = self.listing(placement="back")
        before = len(self.files())
        r = self.add(listing, placement="front", artwork=SimpleUploadedFile("x.png", b"not an image"))
        self.assertEqual(listing.prints.count(), 0)
        self.assertEqual(len(self.files()), before)
        self.assertEqual(Design.objects.count(), 1)
        self.assertContains(r, "isn&#x27;t a readable")

    def test_cannot_add_on_the_same_side_as_the_main_print(self):
        listing = self.listing(placement="back")
        r = self.add(listing, placement="back")
        self.assertEqual(listing.prints.count(), 0)
        self.assertContains(r, "already on the back")

    def test_template_default_counts_as_the_main_side(self):
        listing = self.listing(placement="")  # falls back to the template's front
        r = self.add(listing, placement="front")
        self.assertEqual(listing.prints.count(), 0)
        self.assertContains(r, "already on the front")

    def test_cannot_add_the_same_side_twice(self):
        listing = self.listing(placement="back")
        self.add(listing, placement="front")
        r = self.add(listing, placement="front")
        self.assertEqual(listing.prints.count(), 1)
        self.assertContains(r, "already an additional print")

    def test_unknown_placement_is_refused(self):
        listing = self.listing(placement="back")
        r = self.add(listing, placement="left_sleeve")
        self.assertEqual(listing.prints.count(), 0)
        self.assertContains(r, "front or back")

    def test_scale_and_position_are_sanitised(self):
        listing = self.listing(placement="back")
        self.add(listing, placement="front", scale_pct="3", position="diagonal")
        p = listing.prints.get()
        self.assertEqual((p.scale_pct, p.position), (25, "center"))
        self.add(Listing.objects.get(pk=listing.pk), placement="front", scale_pct="x")  # second add is refused (dup)
        self.assertEqual(listing.prints.count(), 1)

    def test_update_changes_size_and_position(self):
        listing = self.listing(placement="back")
        p = ListingPrint.objects.create(listing=listing, placement="front", scale_pct=30)
        self.c.post(self.url(listing, f"prints/{p.pk}/"), {"scale_pct": "40", "position": "top_right"})
        p.refresh_from_db()
        self.assertEqual((p.scale_pct, p.position), (40, "top_right"))

    def test_cannot_edit_another_listings_print(self):
        listing, other = self.listing(placement="back"), self.listing(placement="back")
        p = ListingPrint.objects.create(listing=other, placement="front", scale_pct=30)
        r = self.c.post(self.url(listing, f"prints/{p.pk}/"), {"scale_pct": "99"})
        self.assertEqual(r.status_code, 404)
        p.refresh_from_db()
        self.assertEqual(p.scale_pct, 30)

    def test_remove_deletes_an_upload_made_for_it_including_the_file(self):
        listing = self.listing(placement="back")
        self.add(listing, placement="front", artwork=SimpleUploadedFile("chest.png", PNG, content_type="image/png"))
        p = listing.prints.get()
        self.c.post(self.url(listing, f"prints/{p.pk}/delete/"))
        self.assertEqual(listing.prints.count(), 0)
        self.assertEqual(Design.objects.count(), 1)  # only the listing's own design is left
        self.assertEqual(len(self.files()), 1)

    def test_remove_keeps_a_design_that_a_listing_or_another_print_still_uses(self):
        listing = self.listing(placement="back")
        other = self.listing(placement="back")
        logo = self.design("Logo")
        a = ListingPrint.objects.create(listing=listing, placement="front", design=logo)
        ListingPrint.objects.create(listing=other, placement="front", design=logo)
        self.c.post(self.url(listing, f"prints/{a.pk}/delete/"))
        self.assertTrue(Design.objects.filter(pk=logo.pk).exists())
        self.assertEqual(len([f for f in self.files() if f.startswith("logo")]), 1)

    def test_remove_never_touches_the_listings_own_design(self):
        listing = self.listing(placement="back")
        p = ListingPrint.objects.create(listing=listing, placement="front", scale_pct=30)  # design = None
        self.c.post(self.url(listing, f"prints/{p.pk}/delete/"))
        self.assertTrue(Design.objects.filter(pk=listing.design_id).exists())

    def test_all_three_routes_are_post_only_and_staff_only(self):
        listing = self.listing(placement="back")
        p = ListingPrint.objects.create(listing=listing, placement="front")
        for path in (f"prints/add/", f"prints/{p.pk}/", f"prints/{p.pk}/delete/"):
            self.assertEqual(self.c.get(self.url(listing, path)).status_code, 405)
            self.assertNotEqual(Client().post(self.url(listing, path)).status_code, 200)
        self.assertEqual(listing.prints.count(), 1)

    def test_moving_the_main_print_onto_an_extras_side_is_refused(self):
        listing = self.listing(placement="back")
        ListingPrint.objects.create(listing=listing, placement="front", scale_pct=30)
        r = self.c.post(self.url(listing), {
            "title": "Wanderer", "color": "Black", "base_cost": "11", "shipping_est": "5", "price": "40",
            "print_scale_pct": "100", "print_position": "center", "print_placement": "front"}, follow=True)
        listing.refresh_from_db()
        self.assertEqual(listing.print_placement, "back")
        self.assertContains(r, "already has an additional print")


class PageTests(PrivateBase):
    def test_page_shows_the_panel_the_extras_and_the_add_form(self):
        listing = self.listing(placement="back")
        page = self.c.get(self.url(listing))
        self.assertContains(page, "Additional print areas")
        self.assertContains(page, "No additional print areas")
        self.assertContains(page, '<option value="front">Front</option>')
        self.assertNotContains(page, '<option value="back">Back</option>\n          </select></div>\n        <div class="field"><label for="new_position">')
        ListingPrint.objects.create(listing=listing, placement="front", scale_pct=30, position="top_left")
        page = self.c.get(self.url(listing))
        self.assertContains(page, "Both sides are in use")
        self.assertContains(page, '<option value="top_left" selected>')

    def test_the_main_fields_are_labelled_as_the_main_print(self):
        self.assertContains(self.c.get(self.url(self.listing())), "Main print goes on the")

    def test_drift_banner_appears_when_the_layout_changed_after_sending(self):
        listing = self.listing(placement="back")
        listing.printful_product_id = "9"
        listing.printful_sent_blueprint_id = "586"
        listing.printful_sent_color = "Black"
        listing.printful_sent_prints = listing.print_signature()
        listing.save()
        self.assertNotContains(self.c.get(self.url(listing)), "Printful still has the old version")
        ListingPrint.objects.create(listing=listing, placement="front", scale_pct=30)
        self.assertContains(self.c.get(self.url(listing)), "Printful still has the old version")
