"""Print placement (template) + scale/position (listing), and the listing
editor's Printful color dropdown. Mock client only."""

from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

from . import printful
from .models import Design, Listing, PrintPlacement, PrintPosition, ProductTemplate, ProductType, Status


_counter = [0]


def make_listing(scale=100, position=PrintPosition.CENTER, placement=PrintPlacement.FRONT, blueprint_id=""):
    _counter[0] += 1
    tpl = ProductTemplate.objects.create(
        name=f"Tee {_counter[0]}", product_type=ProductType.TEE, base_cost=Decimal("11"), shipping_est=Decimal("5"),
        print_placement=placement, printful_blueprint_id=blueprint_id)
    design = Design.objects.create(title="Pillars")
    return Listing.objects.create(
        design=design, template=tpl, product_type="tee", status=Status.LIVE, price=Decimal("40"),
        print_scale_pct=scale, print_position=position)


class PrintFilePayloadTests(TestCase):
    def test_default_scale_and_center_is_just_the_placement_no_position_math(self):
        listing = make_listing()
        self.assertEqual(listing.print_file_payload(), {"type": "front"})

    def test_uses_the_templates_placement(self):
        listing = make_listing(placement=PrintPlacement.BACK)
        self.assertEqual(listing.print_file_payload()["type"], "back")

    def test_smaller_scale_adds_a_position_object(self):
        listing = make_listing(scale=50)
        payload = listing.print_file_payload()
        self.assertIn("position", payload)
        pos = payload["position"]
        self.assertEqual(pos["width"], pos["height"])
        self.assertEqual(pos["width"], round(pos["area_width"] * 0.5))

    def test_center_is_actually_centered(self):
        listing = make_listing(scale=50, position=PrintPosition.CENTER)
        pos = listing.print_file_payload()["position"]
        self.assertEqual(pos["left"] + pos["width"] / 2, pos["area_width"] / 2)
        self.assertEqual(pos["top"] + pos["height"] / 2, pos["area_height"] / 2)

    def test_higher_moves_up_lower_moves_down(self):
        higher = make_listing(scale=50, position=PrintPosition.HIGHER).print_file_payload()["position"]
        lower = make_listing(scale=50, position=PrintPosition.LOWER).print_file_payload()["position"]
        self.assertLess(higher["top"], lower["top"])

    def test_left_and_right_move_the_expected_direction(self):
        left = make_listing(scale=50, position=PrintPosition.LEFT).print_file_payload()["position"]
        right = make_listing(scale=50, position=PrintPosition.RIGHT).print_file_payload()["position"]
        self.assertLess(left["left"], right["left"])

    def test_scale_stored_out_of_range_is_still_clamped_at_payload_time(self):
        listing = make_listing(scale=100)
        listing.print_scale_pct = 5  # bypasses the view's own clamp, e.g. set directly
        payload = listing.print_file_payload()
        self.assertEqual(payload["position"]["width"], round(payload["position"]["area_width"] * 0.25))

    def test_full_scale_but_off_center_still_gets_a_position(self):
        listing = make_listing(scale=100, position=PrintPosition.HIGHER)
        self.assertIn("position", listing.print_file_payload())


class SyncPayloadIncludesPositioningTests(TestCase):
    def test_sync_listing_sends_the_position(self):
        from .models import Design as D
        design = D.objects.create(title="X")
        design.artwork.save("x.png", __import__("django.core.files.base", fromlist=["ContentFile"]).ContentFile(b"fake"), save=True)
        tpl = ProductTemplate.objects.create(name="Sync tee", product_type="tee", print_placement="back")
        listing = Listing.objects.create(design=design, template=tpl, product_type="tee", print_scale_pct=60)
        from .models import ListingSize
        ListingSize.objects.create(listing=listing, label="M")
        client = mock.MagicMock(is_mock=False)
        client.create_sync_product.return_value = {"id": 1, "sync_variants": []}
        with mock.patch.object(printful, "get_client", return_value=client):
            printful.sync_listing(listing)
        payload = client.create_sync_product.call_args[0][0]
        file_entry = payload["sync_variants"][0]["files"][0]
        self.assertEqual(file_entry["type"], "back")
        self.assertIn("position", file_entry)


@override_settings(STAFF_2FA_REQUIRED=False)
class ConsoleBase(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user("curator", password="x-12345-yz", is_staff=True)
        self.c = Client()
        self.c.force_login(self.staff)


class TemplatePlacementFormTests(ConsoleBase):
    def form(self, **over):
        data = {"name": "Tee", "product_type": "tee", "base_cost": "11", "shipping_est": "5",
                "sizes": "M", "print_placement": "back"}
        data.update(over)
        return data

    def test_saves_the_chosen_placement(self):
        self.c.post("/manage/templates/new/", self.form())
        self.assertEqual(ProductTemplate.objects.get().print_placement, "back")

    def test_new_template_form_defaults_to_front(self):
        page = self.c.get("/manage/templates/new/")
        self.assertContains(page, '<option value="front" selected>')

    def test_invalid_placement_is_rejected(self):
        r = self.c.post("/manage/templates/new/", self.form(print_placement="chest_tattoo"))
        self.assertContains(r, "valid print placement")
        self.assertEqual(ProductTemplate.objects.count(), 0)


class ListingPositioningFormTests(ConsoleBase):
    def test_saves_scale_and_position(self):
        listing = make_listing()
        self.c.post(f"/manage/listings/{listing.pk}/", {
            "title": "Pillars", "color": "Black", "base_cost": "11", "shipping_est": "5", "price": "40",
            "print_scale_pct": "70", "print_position": "higher",
        })
        listing.refresh_from_db()
        self.assertEqual(listing.print_scale_pct, 70)
        self.assertEqual(listing.print_position, "higher")

    def test_scale_is_clamped_to_25_100(self):
        listing = make_listing()
        self.c.post(f"/manage/listings/{listing.pk}/", {
            "title": "Pillars", "color": "Black", "base_cost": "11", "shipping_est": "5", "price": "40",
            "print_scale_pct": "5", "print_position": "center",
        })
        listing.refresh_from_db()
        self.assertEqual(listing.print_scale_pct, 25)

    def test_garbage_scale_falls_back_to_100(self):
        listing = make_listing(scale=60)
        self.c.post(f"/manage/listings/{listing.pk}/", {
            "title": "Pillars", "color": "Black", "base_cost": "11", "shipping_est": "5", "price": "40",
            "print_scale_pct": "not-a-number", "print_position": "center",
        })
        listing.refresh_from_db()
        self.assertEqual(listing.print_scale_pct, 100)

    def test_invalid_position_is_ignored_keeping_the_previous_value(self):
        listing = make_listing(position=PrintPosition.LOWER)
        self.c.post(f"/manage/listings/{listing.pk}/", {
            "title": "Pillars", "color": "Black", "base_cost": "11", "shipping_est": "5", "price": "40",
            "print_scale_pct": "100", "print_position": "diagonal",
        })
        listing.refresh_from_db()
        self.assertEqual(listing.print_position, "lower")

    def test_edit_page_shows_the_saved_values(self):
        listing = make_listing(scale=70, position=PrintPosition.HIGHER)
        page = self.c.get(f"/manage/listings/{listing.pk}/")
        self.assertContains(page, 'value="70"')
        self.assertContains(page, '<option value="higher" selected>')


class ColorDropdownTests(ConsoleBase):
    def test_no_printful_product_keeps_the_free_text_field(self):
        listing = make_listing(blueprint_id="")
        page = self.c.get(f"/manage/listings/{listing.pk}/")
        self.assertContains(page, '<input id="color"')
        self.assertNotContains(page, '<select id="color"')

    def test_with_a_printful_product_shows_a_dropdown_of_real_colors(self):
        listing = make_listing(blueprint_id="456")
        page = self.c.get(f"/manage/listings/{listing.pk}/")
        self.assertContains(page, '<select id="color"')
        self.assertContains(page, ">Black<")
        self.assertContains(page, ">Khaki<")

    def test_existing_color_not_in_the_real_list_is_kept_as_a_flagged_option(self):
        listing = make_listing(blueprint_id="456")
        listing.color = "Mauve"
        listing.save()
        page = self.c.get(f"/manage/listings/{listing.pk}/")
        self.assertContains(page, "not a real Printful color")
        self.assertContains(page, 'value="Mauve" selected')

    def test_printful_error_falls_back_to_free_text_without_breaking_the_page(self):
        listing = make_listing(blueprint_id="456")
        with mock.patch.object(printful, "catalog_colors", side_effect=printful.PrintfulError("down")):
            page = self.c.get(f"/manage/listings/{listing.pk}/")
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, '<input id="color"')
        self.assertContains(page, "Couldn't reach Printful")

    def test_selecting_a_color_from_the_dropdown_saves_it(self):
        listing = make_listing(blueprint_id="456")
        self.c.post(f"/manage/listings/{listing.pk}/", {
            "title": "Pillars", "color": "Khaki", "base_cost": "11", "shipping_est": "5", "price": "40",
            "print_scale_pct": "100", "print_position": "center",
        })
        listing.refresh_from_db()
        self.assertEqual(listing.color, "Khaki")


class CatalogColorsTests(TestCase):
    def test_no_blueprint_is_an_empty_list(self):
        self.assertEqual(printful.catalog_colors(""), [])

    def test_returns_sorted_real_colors(self):
        self.assertEqual(printful.catalog_colors(456), ["Black", "Khaki", "White"])

    def test_colors_and_match_variants_share_one_cached_fetch(self):
        client = printful.MockPrintful()
        with mock.patch.object(printful, "get_client", return_value=client), \
                mock.patch.object(client, "catalog_variants", wraps=client.catalog_variants) as spy:
            printful.catalog_colors(456)
            printful.match_variants(456, "Black", ["S"])
            self.assertEqual(spy.call_count, 1)
