"""Printful catalog search and size-matching (mock client only — see
shop.printful.MockPrintful; nothing in this file touches the real API)."""

from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings

from . import printful
from .models import Design, Listing, ListingSize, ProductTemplate, ProductType, Status


class SearchCatalogTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_matches_by_title_model_or_brand(self):
        self.assertTrue(any(p["id"] == 456 for p in printful.search_catalog("stanley")))
        self.assertTrue(any(p["id"] == 456 for p in printful.search_catalog("sttu169")))
        self.assertTrue(any(p["id"] == 71 for p in printful.search_catalog("bella")))

    def test_case_insensitive(self):
        self.assertTrue(any(p["id"] == 145 for p in printful.search_catalog("GILDAN")))

    def test_short_or_empty_query_returns_nothing(self):
        self.assertEqual(printful.search_catalog(""), [])
        self.assertEqual(printful.search_catalog(" a "), [])

    def test_no_match_is_an_empty_list_not_an_error(self):
        self.assertEqual(printful.search_catalog("nonexistent brand xyz"), [])

    def test_catalog_is_fetched_once_and_cached(self):
        client = printful.MockPrintful()
        with mock.patch.object(printful, "get_client", return_value=client), \
                mock.patch.object(client, "list_catalog", wraps=client.list_catalog) as spy:
            printful.search_catalog("stanley")
            printful.search_catalog("gildan")
            self.assertEqual(spy.call_count, 1)


class MatchVariantsTests(TestCase):
    def test_matches_each_size_for_the_given_color(self):
        matches, unmatched, colors = printful.match_variants(456, "Khaki", ["S", "M", "2XL"])
        self.assertEqual(set(matches), {"S", "M", "2XL"})
        self.assertEqual(unmatched, [])
        self.assertIn("Khaki", colors)

    def test_color_matching_is_case_insensitive(self):
        matches, unmatched, _ = printful.match_variants(456, "khaki", ["S"])
        self.assertIn("S", matches)

    def test_unknown_color_matches_nothing_but_lists_real_colors(self):
        matches, unmatched, colors = printful.match_variants(456, "Mauve", ["S", "M"])
        self.assertEqual(matches, {})
        self.assertEqual(unmatched, ["S", "M"])
        self.assertEqual(colors, ["Black", "Khaki", "White"])

    def test_unknown_size_label_is_reported_unmatched(self):
        matches, unmatched, _ = printful.match_variants(456, "Black", ["S", "3XL"])
        self.assertIn("S", matches)
        self.assertEqual(unmatched, ["3XL"])

    def test_variant_ids_are_stable_and_distinct_per_color(self):
        black, _, _ = printful.match_variants(456, "Black", ["M"])
        white, _, _ = printful.match_variants(456, "White", ["M"])
        self.assertNotEqual(black["M"], white["M"])
        black2, _, _ = printful.match_variants(456, "Black", ["M"])
        self.assertEqual(black["M"], black2["M"])


@override_settings(STAFF_2FA_REQUIRED=False)
class ConsoleBase(TestCase):
    def setUp(self):
        cache.clear()
        self.staff = get_user_model().objects.create_user("curator", password="x-12345-yz", is_staff=True)
        self.c = Client()
        self.c.force_login(self.staff)


class TemplateSearchViewTests(ConsoleBase):
    def test_search_returns_a_matching_result(self):
        r = self.c.get("/manage/templates/printful-search/", {"q": "stanley"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "STTU169")
        self.assertContains(r, "#456")

    def test_no_query_shows_nothing_and_does_not_error(self):
        r = self.c.get("/manage/templates/printful-search/", {"q": ""})
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "STTU169")

    def test_no_match_says_so(self):
        r = self.c.get("/manage/templates/printful-search/", {"q": "nonexistent xyz"})
        self.assertContains(r, "No Printful products match")

    def test_requires_staff(self):
        r = Client().get("/manage/templates/printful-search/", {"q": "stanley"})
        self.assertEqual(r.status_code, 302)

    def test_picking_a_result_and_saving_stores_id_and_name(self):
        r = self.c.post("/manage/templates/new/", {
            "name": "Creator tee", "product_type": "tee", "base_cost": "11.00", "shipping_est": "5.00",
            "sizes": "S\nM", "printful_blueprint_id": "456",
            "printful_blueprint_name": "Unisex Organic Cotton Creator 2.0 T-Shirt | Stanley/Stella STTU169",
        })
        self.assertEqual(r.status_code, 302)
        tpl = ProductTemplate.objects.get()
        self.assertEqual(tpl.printful_blueprint_id, "456")
        self.assertIn("STTU169", tpl.printful_blueprint_name)
        page = self.c.get("/manage/catalogue/setup/")
        self.assertContains(page, "STTU169")

    def test_template_without_a_printful_product_says_so_on_the_setup_page(self):
        ProductTemplate.objects.create(name="No Printful yet", product_type="tee", default_sizes=[{"label": "M"}])
        page = self.c.get("/manage/catalogue/setup/")
        self.assertContains(page, "Not linked to a Printful product yet")


class ListingMatchSizesViewTests(ConsoleBase):
    def make_listing(self, color="Khaki", blueprint_id="456"):
        tpl = ProductTemplate.objects.create(
            name="Tee", product_type=ProductType.TEE, base_cost=Decimal("11"), shipping_est=Decimal("5"),
            printful_blueprint_id=blueprint_id)
        design = Design.objects.create(title="Pillars")
        listing = Listing.objects.create(design=design, template=tpl, product_type="tee",
                                          status=Status.LIVE, price=Decimal("40"), color=color)
        for label in ("S", "M", "L"):
            ListingSize.objects.create(listing=listing, label=label)
        return listing

    def test_matches_every_size_and_saves_the_variant_ids(self):
        listing = self.make_listing()
        r = self.c.post(f"/manage/listings/{listing.pk}/match-printful-sizes/")
        self.assertRedirects(r, f"/manage/listings/{listing.pk}/", fetch_redirect_response=False)
        labels_with_ids = set(listing.sizes.exclude(printful_variant_id="").values_list("label", flat=True))
        self.assertEqual(labels_with_ids, {"S", "M", "L"})

    def test_edit_page_shows_matched_variant_ids(self):
        listing = self.make_listing()
        self.c.post(f"/manage/listings/{listing.pk}/match-printful-sizes/")
        page = self.c.get(f"/manage/listings/{listing.pk}/")
        size = listing.sizes.first()
        size.refresh_from_db()
        self.assertContains(page, f"Printful #{size.printful_variant_id}")

    def test_no_template_blueprint_refuses_with_a_helpful_message(self):
        listing = self.make_listing(blueprint_id="")
        r = self.c.post(f"/manage/listings/{listing.pk}/match-printful-sizes/", follow=True)
        self.assertContains(r, "no Printful product chosen yet")
        self.assertEqual(listing.sizes.exclude(printful_variant_id="").count(), 0)

    def test_no_color_refuses_with_a_helpful_message(self):
        listing = self.make_listing(color="")
        r = self.c.post(f"/manage/listings/{listing.pk}/match-printful-sizes/", follow=True)
        self.assertContains(r, "Set this listing&#x27;s color first")

    def test_unmatched_color_reports_the_real_available_colors(self):
        listing = self.make_listing(color="Mauve")
        r = self.c.post(f"/manage/listings/{listing.pk}/match-printful-sizes/", follow=True)
        self.assertContains(r, "Black")
        self.assertContains(r, "Khaki")
        self.assertEqual(listing.sizes.exclude(printful_variant_id="").count(), 0)

    def test_partial_match_reports_which_sizes_failed(self):
        listing = self.make_listing()
        ListingSize.objects.create(listing=listing, label="7XL")  # not a real Printful size
        r = self.c.post(f"/manage/listings/{listing.pk}/match-printful-sizes/", follow=True)
        self.assertContains(r, "7XL")
        self.assertEqual(listing.sizes.get(label="S").printful_variant_id != "", True)

    def test_edit_page_prompts_to_pick_a_printful_product_first(self):
        listing = self.make_listing(blueprint_id="")
        page = self.c.get(f"/manage/listings/{listing.pk}/")
        self.assertContains(page, "Catalogue setup page")
        self.assertNotContains(page, "Match sizes to Printful variants")

    def test_requires_staff_and_post(self):
        listing = self.make_listing()
        self.assertEqual(Client().post(f"/manage/listings/{listing.pk}/match-printful-sizes/").status_code, 302)
        self.assertEqual(self.c.get(f"/manage/listings/{listing.pk}/match-printful-sizes/").status_code, 405)
