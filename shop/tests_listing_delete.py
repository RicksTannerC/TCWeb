"""Deleting a listing (and its design when nothing else uses it). Local only."""

import os
import tempfile
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import Client, TestCase, override_settings

from .models import Design, Listing, ListingPrint, ListingSize, ProductTemplate
from .orders import Order, OrderItem


class ListingDeleteTests(TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()  # artwork lands here, never in the real private store
        self.addCleanup(tmp.cleanup)
        self.enterContext(override_settings(
            MEDIA_ROOT=os.path.join(tmp.name, "public"), PRIVATE_MEDIA_ROOT=os.path.join(tmp.name, "private"),
            STAFF_2FA_REQUIRED=False))
        self.c = Client()
        self.c.force_login(get_user_model().objects.create_user("cur", password="x-12345-yz", is_staff=True))
        self.tpl = ProductTemplate.objects.create(name="Tee", product_type="tee")
        self.design = Design.objects.create(title="Jack-o")
        self.listing = Listing.objects.create(design=self.design, template=self.tpl, product_type="tee", status="draft")
        ListingSize.objects.create(listing=self.listing, label="M")

    def delete(self, listing=None):
        listing = listing or self.listing
        r = self.c.post(f"/manage/listings/{listing.pk}/delete/")
        return r, self.c.get(r["Location"])

    def test_a_draft_goes_and_its_design_with_it(self):
        r, page = self.delete()
        self.assertRedirects(r, "/manage/listings/", fetch_redirect_response=False)
        self.assertFalse(Listing.objects.filter(pk=self.listing.pk).exists())
        self.assertFalse(Design.objects.filter(pk=self.design.pk).exists())
        self.assertContains(page, "Deleted")

    def test_a_design_with_another_listing_stays(self):
        other = Listing.objects.create(design=self.design, template=self.tpl, product_type="tee", status="draft")
        _, page = self.delete()
        self.assertTrue(Design.objects.filter(pk=self.design.pk).exists())
        self.assertTrue(Listing.objects.filter(pk=other.pk).exists())
        self.assertContains(page, "The design stays")

    def test_the_private_artwork_file_is_removed_with_its_design(self):
        self.design.artwork.save("a.png", ContentFile(b"x"), save=True)
        name = self.design.artwork.name
        storage = self.design.artwork.storage
        self.assertTrue(storage.exists(name))
        self.delete()
        self.assertFalse(storage.exists(name))

    def test_an_additional_prints_own_artwork_design_goes_too(self):
        extra = Design.objects.create(title="Jack-o — front")
        extra.artwork.save("b.png", ContentFile(b"x"), save=True)
        ListingPrint.objects.create(listing=self.listing, placement="front", design=extra, scale_pct=30)
        self.delete()
        self.assertFalse(Design.objects.filter(pk=extra.pk).exists())

    def test_artwork_shared_with_another_listings_print_is_kept(self):
        shared = Design.objects.create(title="Shared")
        shared.artwork.save("c.png", ContentFile(b"x"), save=True)
        ListingPrint.objects.create(listing=self.listing, placement="front", design=shared)
        keeper = Listing.objects.create(design=Design.objects.create(title="K"), template=self.tpl, product_type="tee")
        ListingPrint.objects.create(listing=keeper, placement="front", design=shared)
        self.delete()
        self.assertTrue(Design.objects.filter(pk=shared.pk).exists())

    def test_a_live_listing_is_refused(self):
        self.listing.status = "live"
        self.listing.save()
        _, page = self.delete()
        self.assertTrue(Listing.objects.filter(pk=self.listing.pk).exists())
        self.assertContains(page, "is live. Unpublish it first")

    def test_an_ordered_listing_is_refused_and_the_order_is_untouched(self):
        order = Order.objects.create(email="a@b.test", grand_total=Decimal("30"))
        item = OrderItem.objects.create(order=order, listing=self.listing, design_title="Jack-o", quantity=1,
                                        unit_price=Decimal("30"))
        _, page = self.delete()
        self.assertTrue(Listing.objects.filter(pk=self.listing.pk).exists())
        item.refresh_from_db()
        self.assertEqual(item.listing_id, self.listing.pk)
        self.assertContains(page, "has been ordered")

    def test_the_page_shows_the_button_only_when_deletion_is_allowed(self):
        url = f"/manage/listings/{self.listing.pk}/"
        self.assertContains(self.c.get(url), "Delete this listing")
        self.listing.status = "live"
        self.listing.save()
        self.assertNotContains(self.c.get(url), "Delete this listing")
        self.listing.status = "draft"
        self.listing.save()
        order = Order.objects.create(email="a@b.test", grand_total=Decimal("1"))
        OrderItem.objects.create(order=order, listing=self.listing, design_title="x", quantity=1, unit_price=Decimal("1"))
        self.assertNotContains(self.c.get(url), "Delete this listing")

    def test_a_printful_product_is_called_out_but_never_touched(self):
        self.listing.printful_product_id = "477"
        self.listing.save()
        self.assertContains(self.c.get(f"/manage/listings/{self.listing.pk}/"), "is <strong>not</strong>")
        _, page = self.delete()
        self.assertContains(page, "product 477")

    def test_post_only_and_staff_only(self):
        self.assertEqual(self.c.get(f"/manage/listings/{self.listing.pk}/delete/").status_code, 405)
        self.assertNotEqual(Client().post(f"/manage/listings/{self.listing.pk}/delete/").status_code, 200)
        self.assertTrue(Listing.objects.filter(pk=self.listing.pk).exists())
