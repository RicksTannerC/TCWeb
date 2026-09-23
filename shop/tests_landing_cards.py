"""Landing-page collection cards: curator-controlled, with a safe fallback."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

from .models import Collection, Design, Listing, ListingImage, ProductTemplate, Status


def make_listing(title, collection=None, status=Status.LIVE):
    tpl = ProductTemplate.objects.first() or ProductTemplate.objects.create(
        name="Tee", product_type="tee", base_cost=Decimal("11"), shipping_est=Decimal("5"))
    design = Design.objects.create(title=title)
    return Listing.objects.create(
        design=design, template=tpl, product_type="tee", status=status,
        price=Decimal("40"), collection=collection)


class CollectionModelTests(TestCase):
    def test_no_centerpiece_without_a_live_listing(self):
        col = Collection.objects.create(name="Deep Field")
        self.assertIsNone(col.centerpiece_listing)
        make_listing("Nebula", collection=col, status=Status.DRAFT)
        self.assertIsNone(col.centerpiece_listing)

    def test_centerpiece_is_a_live_listing_in_the_collection(self):
        col = Collection.objects.create(name="Deep Field")
        listing = make_listing("Nebula", collection=col)
        self.assertEqual(col.centerpiece_listing, listing)

    def test_landing_cards_requires_live_status_and_the_flag_and_a_centerpiece(self):
        shown = Collection.objects.create(name="Shown", status=Status.LIVE, featured_on_landing=True)
        make_listing("A", collection=shown)

        hidden_status = Collection.objects.create(name="Hidden status", status=Status.HIDDEN, featured_on_landing=True)
        make_listing("B", collection=hidden_status)

        not_featured = Collection.objects.create(name="Not featured", status=Status.LIVE, featured_on_landing=False)
        make_listing("C", collection=not_featured)

        empty = Collection.objects.create(name="Empty", status=Status.LIVE, featured_on_landing=True)

        self.assertEqual(Collection.landing_cards(), [shown])

    def test_landing_cards_are_ordered_and_orphans_are_dropped(self):
        b = Collection.objects.create(name="B", status=Status.LIVE, featured_on_landing=True, landing_sort_order=2)
        a = Collection.objects.create(name="A", status=Status.LIVE, featured_on_landing=True, landing_sort_order=1)
        make_listing("x", collection=a)
        make_listing("y", collection=b)
        self.assertEqual(Collection.landing_cards(), [a, b])


class LandingViewTests(TestCase):
    def test_shows_collection_cards_when_any_are_featured(self):
        col = Collection.objects.create(name="Deep Field", status=Status.LIVE, featured_on_landing=True, summary="Cosmic stuff")
        make_listing("Nebula", collection=col)
        make_listing("Solo shirt")  # a live listing with no collection: shouldn't leak into "featured" fallback
        html = Client().get("/").content.decode()
        self.assertIn("Deep Field", html)
        self.assertIn("Cosmic stuff", html)
        self.assertIn('href="/shop/#collection-deep-field"', html)
        self.assertNotIn("In the shop now", html)
        self.assertNotIn("Solo shirt", html)

    def test_falls_back_to_individual_shirts_when_nothing_is_featured(self):
        make_listing("Solo shirt")
        html = Client().get("/").content.decode()
        self.assertIn("In the shop now", html)
        self.assertIn("Solo shirt", html)
        self.assertNotIn("Explore the catalogue", html)

    def test_empty_state_is_just_the_hero(self):
        r = Client().get("/")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("Explore the catalogue", r.content.decode())

    def test_card_links_to_a_real_anchor_on_the_shop_page(self):
        col = Collection.objects.create(name="Deep Field", status=Status.LIVE, featured_on_landing=True)
        listing = make_listing("Nebula", collection=col)
        html = Client().get("/shop/").content.decode()
        self.assertIn(f'id="collection-{col.slug}"', html)
        self.assertIn(listing.design.title, html)


@override_settings(STAFF_2FA_REQUIRED=False)
class ConsoleToggleTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user("curator", password="x-12345-yz", is_staff=True)
        self.c = Client()
        self.c.force_login(self.staff)
        self.col = Collection.objects.create(name="Deep Field")

    def test_toggle_flips_the_flag_and_redirects(self):
        r = self.c.post(f"/manage/collections/{self.col.pk}/toggle-landing/")
        self.assertRedirects(r, "/manage/catalogue/setup/#collections", fetch_redirect_response=False)
        self.col.refresh_from_db()
        self.assertTrue(self.col.featured_on_landing)
        self.c.post(f"/manage/collections/{self.col.pk}/toggle-landing/")
        self.col.refresh_from_db()
        self.assertFalse(self.col.featured_on_landing)

    def test_warns_if_featured_while_still_hidden(self):
        r = self.c.post(f"/manage/collections/{self.col.pk}/toggle-landing/", follow=True)
        self.assertContains(r, "once it&#x27;s published")

    def test_list_page_shows_the_state_and_the_button(self):
        page = self.c.get("/manage/catalogue/setup/")
        self.assertContains(page, "Show on landing")
        self.col.featured_on_landing = True
        self.col.save()
        page = self.c.get("/manage/catalogue/setup/")
        self.assertContains(page, "Remove from landing")
        self.assertContains(page, "On landing")

    def test_old_collections_url_redirects_to_the_merged_page(self):
        r = self.c.get("/manage/collections/")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r["Location"], "/manage/catalogue/setup/#collections")

    def test_requires_staff_and_post(self):
        self.assertEqual(Client().post(f"/manage/collections/{self.col.pk}/toggle-landing/").status_code, 302)
        self.assertEqual(self.c.get(f"/manage/collections/{self.col.pk}/toggle-landing/").status_code, 405)
