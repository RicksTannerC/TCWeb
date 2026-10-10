"""A private record, per design, of where the artwork came from and whether it was
searched for conflicts -- the evidence behind the Terms' ownership promise."""

import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

from .models import Design, Listing, ProductTemplate, Status


@override_settings(STAFF_2FA_REQUIRED=False)
class DesignRightsTests(TestCase):
    def setUp(self):
        self.c = Client()
        self.c.force_login(get_user_model().objects.create_user("cur", password="x-12345-yz", is_staff=True))
        self.tpl = ProductTemplate.objects.create(name="Tee", product_type="tee")

    def listing(self, status=Status.LIVE, **design_kw):
        design = Design.objects.create(title=f"D{Design.objects.count()}", **design_kw)
        return Listing.objects.create(design=design, template=self.tpl, product_type="tee",
                                      status=status, price=Decimal("30"))

    def save(self, listing, **extra):
        data = {"title": listing.design.title, "color": "", "base_cost": "10", "shipping_est": "5",
                "price": "30", "print_scale_pct": "100", "print_position": "center"}
        data.update(extra)
        return self.c.post(f"/manage/listings/{listing.pk}/", data, follow=True)

    # ---- saving ----
    def test_origin_date_and_notes_are_saved_from_the_editor(self):
        listing = self.listing()
        self.save(listing, origin="licensed", ip_checked_on="2026-10-11", ip_notes="Envato licence #123; searched USPTO")
        d = Design.objects.get(pk=listing.design_id)
        self.assertEqual(d.origin, "licensed")
        self.assertEqual(d.ip_checked_on, datetime.date(2026, 10, 11))
        self.assertEqual(d.ip_notes, "Envato licence #123; searched USPTO")
        self.assertTrue(d.rights_recorded)

    def test_an_unknown_origin_value_is_ignored(self):
        listing = self.listing(origin="original")
        self.save(listing, origin="made-up")
        self.assertEqual(Design.objects.get(pk=listing.design_id).origin, "original")

    def test_a_bad_date_is_refused_with_a_message_and_the_old_date_kept(self):
        listing = self.listing(ip_checked_on=datetime.date(2026, 1, 2))
        r = self.save(listing, ip_checked_on="31/12/2026")
        self.assertContains(r, "That date isn&#x27;t valid")
        self.assertEqual(Design.objects.get(pk=listing.design_id).ip_checked_on, datetime.date(2026, 1, 2))

    def test_an_empty_date_clears_it(self):
        listing = self.listing(ip_checked_on=datetime.date(2026, 1, 2))
        self.save(listing, ip_checked_on="")
        self.assertIsNone(Design.objects.get(pk=listing.design_id).ip_checked_on)

    def test_a_form_that_does_not_mention_the_fields_leaves_them_alone(self):
        """Other forms/tests post only part of the editor; that must not wipe the record."""
        listing = self.listing(origin="original", ip_checked_on=datetime.date(2026, 3, 4), ip_notes="kept")
        self.save(listing)  # no origin / ip_checked_on / ip_notes keys at all
        d = Design.objects.get(pk=listing.design_id)
        self.assertEqual((d.origin, d.ip_checked_on, d.ip_notes), ("original", datetime.date(2026, 3, 4), "kept"))

    # ---- what the editor shows ----
    def test_the_editor_shows_the_saved_values(self):
        listing = self.listing(origin="ai", ip_checked_on=datetime.date(2026, 5, 6), ip_notes="prompt log in drive")
        html = self.c.get(f"/manage/listings/{listing.pk}/").content.decode()
        self.assertIn('<option value="ai" selected>', html)
        self.assertIn('value="2026-05-06"', html)
        self.assertIn("prompt log in drive", html)

    def test_a_live_listing_with_nothing_recorded_gets_a_quiet_nudge(self):
        listing = self.listing()
        self.assertIn("Rights not fully recorded", self.c.get(f"/manage/listings/{listing.pk}/").content.decode())

    def test_no_nudge_once_recorded_or_while_still_a_draft(self):
        done = self.listing(origin="original", ip_checked_on=datetime.date(2026, 1, 1))
        draft = self.listing(status=Status.DRAFT)
        self.assertNotIn("Rights not fully recorded", self.c.get(f"/manage/listings/{done.pk}/").content.decode())
        self.assertNotIn("Rights not fully recorded", self.c.get(f"/manage/listings/{draft.pk}/").content.decode())

    def test_an_origin_without_a_search_date_is_still_incomplete(self):
        listing = self.listing(origin="original")
        self.assertFalse(listing.design.rights_recorded)

    def test_the_listings_list_marks_designs_without_a_record(self):
        self.listing()
        self.listing(origin="original", ip_checked_on=datetime.date(2026, 1, 1))
        html = self.c.get("/manage/listings/").content.decode()
        self.assertEqual(html.count("rights not recorded"), 1)

    # ---- never public ----
    def test_the_notes_never_appear_on_the_public_shop(self):
        listing = self.listing(origin="licensed", ip_checked_on=datetime.date(2026, 1, 1),
                               ip_notes="SECRET-LICENCE-NOTE-12345")
        for url in ("/", listing.get_absolute_url()):
            html = Client().get(url).content.decode()
            self.assertNotIn("SECRET-LICENCE-NOTE-12345", html)
            self.assertNotIn("Conflict search done on", html)
