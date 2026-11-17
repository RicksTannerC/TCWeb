"""Replacing a design's artwork from the listing editor, and the Printful preview's
broken-thumbnail case. Local only: nothing here talks to Printful."""

import io
import os
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings

from tshirtbrand.adapters.suppliers.printful.supplier import _clean_image_url, _previews

from . import printful
from .models import Design, Listing, ListingPrint, ProductTemplate


def png(w=20, h=10):
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGBA", (w, h), (1, 2, 3, 255)).save(buf, "PNG")
    return buf.getvalue()


class Base(TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.enterContext(override_settings(
            MEDIA_ROOT=os.path.join(tmp.name, "public"), PRIVATE_MEDIA_ROOT=os.path.join(tmp.name, "private"),
            STAFF_2FA_REQUIRED=False))
        self.c = Client()
        self.c.force_login(get_user_model().objects.create_user("cur", password="x-12345-yz", is_staff=True))
        self.tpl = ProductTemplate.objects.create(name="Tee", product_type="tee", print_placement="back")
        self.design = Design.objects.create(title="Main")
        self.design.artwork.save("old.png", ContentFile(png(10, 10)), save=True)
        self.listing = Listing.objects.create(design=self.design, template=self.tpl, product_type="tee")
        self.storage = self.design.artwork.storage

    def upload(self, name="new.png", data=None):
        return SimpleUploadedFile(name, png(40, 20) if data is None else data, content_type="image/png")


class ReplaceMainTests(Base):
    def post(self, **kw):
        r = self.c.post(f"/manage/listings/{self.listing.pk}/replace-artwork/", kw)
        return r, self.c.get(r["Location"])

    def test_replaces_the_file_removes_the_old_one_and_bumps_the_version(self):
        old = self.design.artwork.name
        _, page = self.post(artwork=self.upload())
        self.design.refresh_from_db()
        self.assertNotEqual(self.design.artwork.name, old)
        self.assertTrue(self.storage.exists(self.design.artwork.name))
        self.assertFalse(self.storage.exists(old))
        self.assertEqual(self.design.artwork_version, 1)
        self.assertContains(page, "Artwork replaced")

    def test_a_non_image_is_refused_and_nothing_changes(self):
        old = self.design.artwork.name
        _, page = self.post(artwork=self.upload("x.png", b"not an image"))
        self.design.refresh_from_db()
        self.assertEqual(self.design.artwork.name, old)
        self.assertEqual(self.design.artwork_version, 0)
        self.assertContains(page, "isn&#x27;t a readable")

    def test_no_file_is_refused(self):
        _, page = self.post()
        self.assertContains(page, "Choose an image file")

    def test_a_listing_sent_with_the_old_file_is_flagged(self):
        self.listing.printful_product_id = "1"
        self.listing.printful_sent_prints = self.listing.print_signature()
        self.listing.save()
        self.assertEqual(self.listing.printful_changes_not_sent, [])
        self.post(artwork=self.upload())
        listing = Listing.objects.get(pk=self.listing.pk)
        self.assertTrue(any("print areas" in c for c in listing.printful_changes_not_sent))

    def test_a_shared_design_says_so(self):
        Listing.objects.create(design=self.design, template=self.tpl, product_type="tee")
        _, page = self.post(artwork=self.upload())
        self.assertContains(page, "shared with 1 other listing")

    def test_the_editor_has_the_panel(self):
        self.assertContains(self.c.get(f"/manage/listings/{self.listing.pk}/"), "Replace artwork")

    def test_post_only_and_staff_only(self):
        url = f"/manage/listings/{self.listing.pk}/replace-artwork/"
        self.assertEqual(self.c.get(url).status_code, 405)
        self.assertNotEqual(Client().post(url).status_code, 200)


class ReplacePrintTests(Base):
    def setUp(self):
        super().setUp()
        self.extra = Design.objects.create(title="Front")
        self.extra.artwork.save("front.png", ContentFile(png()), save=True)
        self.p = ListingPrint.objects.create(listing=self.listing, placement="front", design=self.extra, scale_pct=30)

    def post(self, **kw):
        r = self.c.post(f"/manage/listings/{self.listing.pk}/prints/{self.p.pk}/replace-artwork/", kw)
        return r, self.c.get(r["Location"])

    def test_the_print_gets_new_art_and_the_old_design_is_dropped(self):
        old_name = self.extra.artwork.name
        _, page = self.post(artwork=self.upload())
        self.p.refresh_from_db()
        self.assertNotEqual(self.p.design_id, self.extra.pk)
        self.assertEqual((self.p.scale_pct, self.p.placement), (30, "front"))
        self.assertFalse(Design.objects.filter(pk=self.extra.pk).exists())
        self.assertFalse(self.storage.exists(old_name))
        self.assertTrue(self.storage.exists(self.p.design.artwork.name))
        self.assertContains(page, "print artwork replaced")

    def test_the_main_print_is_untouched(self):
        self.post(artwork=self.upload())
        self.design.refresh_from_db()
        self.assertEqual(self.design.artwork_version, 0)
        self.assertTrue(self.storage.exists(self.design.artwork.name))

    def test_a_print_that_reused_the_main_art_gets_its_own_copy_of_the_new_one(self):
        self.p.design = None
        self.p.save()
        self.post(artwork=self.upload())
        self.p.refresh_from_db()
        self.assertIsNotNone(self.p.design_id)
        self.assertNotEqual(self.p.design_id, self.design.pk)
        self.assertTrue(Design.objects.filter(pk=self.design.pk).exists())

    def test_a_bad_file_changes_nothing(self):
        self.post(artwork=self.upload("x.png", b"nope"))
        self.p.refresh_from_db()
        self.assertEqual(self.p.design_id, self.extra.pk)
        self.assertTrue(self.storage.exists(self.extra.artwork.name))

    def test_a_listing_sent_with_the_old_print_is_flagged(self):
        self.listing.printful_product_id = "1"
        self.listing.printful_sent_prints = self.listing.print_signature()
        self.listing.save()
        self.post(artwork=self.upload())
        listing = Listing.objects.get(pk=self.listing.pk)
        self.assertTrue(any("print areas" in c for c in listing.printful_changes_not_sent))

    def test_the_wrong_listings_print_is_a_404(self):
        other = Listing.objects.create(design=Design.objects.create(title="O"), template=self.tpl, product_type="tee")
        r = self.c.post(f"/manage/listings/{other.pk}/prints/{self.p.pk}/replace-artwork/", {"artwork": self.upload()})
        self.assertEqual(r.status_code, 404)


class BarePreviewUrlTests(Base):
    BARE = "https://files.cdn.printful.com/"
    REAL = "https://files.cdn.printful.com/files/1d2/abc_preview.png"

    def test_a_bare_cdn_host_is_not_an_image(self):
        self.assertEqual(_clean_image_url(self.BARE), "")
        self.assertEqual(_clean_image_url(self.BARE.rstrip("/")), "")
        self.assertEqual(_clean_image_url(self.REAL), self.REAL)

    def test_a_new_read_drops_it(self):
        got = _previews({"sync_product": {"thumbnail_url": self.BARE}, "sync_variants": []}, "")
        self.assertEqual(got, ())

    def test_an_old_stored_read_is_not_shown_as_a_broken_image(self):
        self.listing.printful_product_id = "1"
        self.listing.printful_preview = [{"label": "Product thumbnail", "url": self.BARE},
                                         {"label": "Black Heather", "url": self.REAL}]
        self.listing.save()
        page = self.c.get(f"/manage/listings/{self.listing.pk}/")
        self.assertContains(page, self.REAL)
        self.assertNotContains(page, f'src="{self.BARE}"')
        self.assertEqual(len(self.listing.preview_images), 1)
