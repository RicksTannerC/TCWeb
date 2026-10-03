"""Reordering a listing's images in the editor. The order is what shoppers see in
the carousel, and the first image is the shop's cover."""

import io
import os
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from PIL import Image

from .models import Design, Listing, ListingImage, ProductTemplate, Status


def _png():
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (10, 90, 40)).save(buf, "PNG")
    return buf.getvalue()


@override_settings(STAFF_2FA_REQUIRED=False)
class ImageOrderTests(TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.enterContext(override_settings(MEDIA_ROOT=os.path.join(tmp.name, "public")))
        self.c = Client()
        self.c.force_login(get_user_model().objects.create_user("cur", password="x-12345-yz", is_staff=True))
        self.tpl = ProductTemplate.objects.create(name="Tee", product_type="tee")

    def listing(self, n=3, orders=None):
        listing = Listing.objects.create(design=Design.objects.create(title=f"W{Listing.objects.count()}"),
                                         template=self.tpl, product_type="tee", status=Status.LIVE)
        orders = orders if orders is not None else range(n)
        self.imgs = [ListingImage.objects.create(listing=listing, image=f"listings/{listing.pk}-{i}.png",
                                                 sort_order=o, alt_text=f"img{i}")
                     for i, o in enumerate(orders)]
        return listing

    def order(self, listing):
        return [i.alt_text for i in ListingImage.objects.filter(listing=listing)]

    def move(self, img, direction):
        return self.c.post(f"/manage/images/{img.pk}/move/", {"direction": direction})

    def test_later_swaps_with_the_next_image(self):
        listing = self.listing()
        self.move(self.imgs[0], "later")
        self.assertEqual(self.order(listing), ["img1", "img0", "img2"])

    def test_earlier_swaps_with_the_previous_image(self):
        listing = self.listing()
        self.move(self.imgs[2], "earlier")
        self.assertEqual(self.order(listing), ["img0", "img2", "img1"])

    def test_make_cover_moves_to_the_front_and_keeps_the_rest_in_order(self):
        listing = self.listing(4)
        self.move(self.imgs[3], "first")
        self.assertEqual(self.order(listing), ["img3", "img0", "img1", "img2"])

    def test_moving_past_either_end_changes_nothing(self):
        listing = self.listing()
        self.move(self.imgs[0], "earlier")
        self.move(self.imgs[2], "later")
        self.assertEqual(self.order(listing), ["img0", "img1", "img2"])

    def test_the_first_image_stays_first_when_made_cover_again(self):
        listing = self.listing()
        self.move(self.imgs[0], "first")
        self.assertEqual(self.order(listing), ["img0", "img1", "img2"])

    def test_duplicate_sort_values_are_healed_and_the_move_still_works(self):
        listing = self.listing(orders=[0, 0, 0])  # e.g. fabricated by the old mock button
        before = self.order(listing)
        self.move(self.imgs[2], "earlier")
        after = self.order(listing)
        self.assertEqual(after, [before[0], before[2], before[1]])
        self.assertEqual(list(ListingImage.objects.filter(listing=listing).values_list("sort_order", flat=True)), [0, 1, 2])

    def test_gaps_are_renumbered(self):
        listing = self.listing(orders=[3, 9, 40])
        self.move(self.imgs[1], "later")
        self.assertEqual(list(ListingImage.objects.filter(listing=listing).values_list("sort_order", flat=True)), [0, 1, 2])
        self.assertEqual(self.order(listing), ["img0", "img2", "img1"])

    def test_other_listings_are_untouched(self):
        a, mine = self.listing(), None
        a_imgs = self.imgs
        b = self.listing()
        before_b = self.order(b)
        self.move(a_imgs[0], "later")
        self.assertEqual(self.order(b), before_b)

    def test_unknown_direction_changes_nothing_and_says_so(self):
        listing = self.listing()
        r = self.c.post(f"/manage/images/{self.imgs[0].pk}/move/", {"direction": "sideways"}, follow=True)
        self.assertEqual(self.order(listing), ["img0", "img1", "img2"])
        self.assertContains(r, "Unknown way to move")

    def test_post_only_and_staff_only_and_404_for_missing(self):
        listing = self.listing()
        self.assertEqual(self.c.get(f"/manage/images/{self.imgs[0].pk}/move/").status_code, 405)
        self.assertNotEqual(Client().post(f"/manage/images/{self.imgs[0].pk}/move/", {"direction": "later"}).status_code, 200)
        self.assertEqual(self.order(listing), ["img0", "img1", "img2"])
        self.assertEqual(self.c.post("/manage/images/99999/move/", {"direction": "later"}).status_code, 404)

    def test_it_returns_to_the_imagery_section(self):
        listing = self.listing()
        r = self.move(self.imgs[0], "later")
        self.assertRedirects(r, f"/manage/listings/{listing.pk}/#imagery", fetch_redirect_response=False)

    def test_a_new_upload_goes_to_the_end_even_after_reordering_and_deleting(self):
        listing = self.listing()
        self.move(self.imgs[2], "first")           # img2, img0, img1
        self.c.post(f"/manage/images/{self.imgs[0].pk}/delete/")  # img2, img1
        self.c.post(f"/manage/listings/{listing.pk}/image/", {
            "kind": "mockup", "image": SimpleUploadedFile("new.png", _png(), content_type="image/png")})
        self.assertEqual(self.order(listing)[:2], ["img2", "img1"])
        self.assertEqual(ListingImage.objects.filter(listing=listing).last().alt_text, "")
        self.assertEqual(ListingImage.objects.filter(listing=listing).count(), 3)

    def test_two_uploads_at_once_keep_their_own_places(self):
        listing = self.listing(orders=[0])
        self.c.post(f"/manage/listings/{listing.pk}/image/", {"kind": "mockup", "image": [
            SimpleUploadedFile("a.png", _png(), content_type="image/png"),
            SimpleUploadedFile("b.png", _png(), content_type="image/png")]})
        self.assertEqual(list(ListingImage.objects.filter(listing=listing).values_list("sort_order", flat=True)), [0, 1, 2])

    def test_first_upload_into_an_empty_listing_starts_at_zero(self):
        listing = self.listing(n=0)
        self.c.post(f"/manage/listings/{listing.pk}/image/", {
            "kind": "mockup", "image": SimpleUploadedFile("a.png", _png(), content_type="image/png")})
        self.assertEqual(ListingImage.objects.get(listing=listing).sort_order, 0)

    # ---- what shoppers see ----
    def test_the_cover_follows_the_new_order(self):
        listing = self.listing()
        self.assertEqual(listing.primary_image.alt_text, "img0")
        self.move(self.imgs[2], "first")
        listing = Listing.objects.get(pk=listing.pk)
        self.assertEqual(listing.primary_image.alt_text, "img2")

    def test_the_public_carousel_follows_the_new_order(self):
        listing = self.listing()
        self.move(self.imgs[2], "first")
        html = Client().get(listing.get_absolute_url()).content.decode()
        positions = [html.index(f"{listing.pk}-{i}.png") for i in (2, 0, 1)]
        self.assertEqual(positions, sorted(positions))

    # ---- the editor page ----
    def test_page_shows_positions_the_cover_and_the_right_buttons(self):
        listing = self.listing()
        html = self.c.get(f"/manage/listings/{listing.pk}/").content.decode()
        self.assertIn("<strong>Cover</strong>", html)
        self.assertEqual(html.count("make cover"), 2)  # every image but the first
        self.assertIn('aria-label="Move image 1 earlier" disabled', html)
        self.assertIn('aria-label="Move image 3 later" disabled', html)
        self.assertIn('id="imagery"', html)

    def test_a_single_image_has_no_move_controls(self):
        listing = self.listing(n=1)
        html = self.c.get(f"/manage/listings/{listing.pk}/").content.decode()
        self.assertNotIn("make cover", html)
        self.assertNotIn("/move/", html)
