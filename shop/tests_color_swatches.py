"""The listing editor's color picker: a real swatch per color, a photo of that
color on the blank, and a link to the blank on Printful. Mock data only."""

from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

from . import printful
from .models import Design, Listing, ProductTemplate

VARIANTS = {"variants": [
    {"id": 1, "size": "M", "color": "Black", "color_code": "#0B0B0B", "image": "https://files.cdn.printful.com/p/black.jpg"},
    {"id": 2, "size": "L", "color": "Black", "color_code": "#0B0B0B", "image": "https://files.cdn.printful.com/p/black-l.jpg"},
    {"id": 3, "size": "M", "color": "Khaki", "color_code": "b8a77f"},
    {"id": 4, "size": "M", "color": "Heather Grey/Navy", "color_code": "#c8c8c8", "color_code2": "#1c2a4a"},
    {"id": 5, "size": "M", "color": "Mystery"},
]}


def options():
    with mock.patch.object(printful, "_cached_variants", return_value=VARIANTS):
        return {o["name"]: o for o in printful.catalog_color_options("586")}


class ColorOptionsTests(TestCase):
    def test_one_entry_per_color_with_the_exact_hex(self):
        o = options()
        self.assertEqual(set(o), {"Black", "Khaki", "Heather Grey/Navy", "Mystery"})
        self.assertEqual(o["Black"]["hex"], "#0b0b0b")  # normalised to lowercase #rrggbb
        self.assertEqual(o["Khaki"]["hex"], "#b8a77f")  # a missing '#' is tolerated

    def test_the_first_photo_for_a_color_is_used(self):
        self.assertEqual(options()["Black"]["image"], "https://files.cdn.printful.com/p/black.jpg")

    def test_a_two_tone_color_gets_a_split_swatch(self):
        sw = options()["Heather Grey/Navy"]["swatch"]
        self.assertIn("linear-gradient", sw)
        self.assertIn("#c8c8c8", sw)
        self.assertIn("#1c2a4a", sw)

    def test_a_color_without_a_code_has_no_swatch_and_no_photo(self):
        self.assertEqual(options()["Mystery"]["swatch"], "")
        self.assertEqual(options()["Mystery"]["image"], "")

    def test_sorted_by_name(self):
        with mock.patch.object(printful, "_cached_variants", return_value=VARIANTS):
            names = [o["name"] for o in printful.catalog_color_options("586")]
        self.assertEqual(names, sorted(names, key=str.lower))

    def test_hostile_values_from_the_api_are_never_passed_on(self):
        bad = {"variants": [
            {"color": "Evil", "color_code": "red; background:url(//x)", "color_code2": "#12345",
             "image": "javascript:alert(1)"},
            {"color": "Evil2", "color_code": "#ff0000", "image": 'https://x.test/a.jpg" onerror="alert(1)'},
            {"color": "Evil3", "image": "http://insecure.test/a.jpg"},
        ]}
        with mock.patch.object(printful, "_cached_variants", return_value=bad):
            o = {x["name"]: x for x in printful.catalog_color_options("586")}
        self.assertEqual((o["Evil"]["hex"], o["Evil"]["hex2"], o["Evil"]["image"]), ("", "", ""))
        self.assertEqual(o["Evil2"]["image"], "")
        self.assertEqual(o["Evil2"]["swatch"], "#ff0000")
        self.assertEqual(o["Evil3"]["image"], "")

    def test_no_blueprint_means_no_options(self):
        self.assertEqual(printful.catalog_color_options(""), [])

    def test_the_mock_catalogue_carries_swatches_for_local_development(self):
        o = {x["name"]: x for x in printful.catalog_color_options(456)}
        self.assertEqual(o["Black"]["hex"], "#0b0b0b")
        self.assertEqual(o["White"]["hex"], "#ffffff")


class ProductLinkTests(TestCase):
    def test_built_in_the_pattern_of_a_real_printful_dashboard_link(self):
        self.assertEqual(
            printful.dashboard_product_url("Unisex Garment-Dyed Heavyweight T-Shirt | Comfort Colors 1717"),
            "https://www.printful.com/dashboard/custom/mens/t-shirts/unisex-garment-dyed-heavyweight-t-shirt-comfort-colors-1717")
        # the shape of the link the curator pasted earlier (a slash in the brand becomes a hyphen)
        self.assertEqual(
            printful.dashboard_product_url("Unisex Organic Cotton T-Shirt | Stanley/Stella STTU169"),
            "https://www.printful.com/dashboard/custom/mens/t-shirts/unisex-organic-cotton-t-shirt-stanley-stella-sttu169")

    def test_nothing_is_guessed_without_a_name_or_for_non_tees(self):
        self.assertEqual(printful.dashboard_product_url(""), "")
        self.assertEqual(printful.dashboard_product_url("Kiss-Cut Stickers", "sticker"), "")


@override_settings(STAFF_2FA_REQUIRED=False)
class PickerPageTests(TestCase):
    def setUp(self):
        self.c = Client()
        self.c.force_login(get_user_model().objects.create_user("cur", password="x-12345-yz", is_staff=True))

    def listing(self, color="Khaki", name="Unisex Garment-Dyed Heavyweight T-Shirt | Comfort Colors 1717"):
        tpl = ProductTemplate.objects.create(name="Tee", product_type="tee", printful_blueprint_id="586",
                                             printful_blueprint_name=name)
        return Listing.objects.create(design=Design.objects.create(title="W"), template=tpl,
                                      product_type="tee", color=color)

    def page(self, listing):
        with mock.patch.object(printful, "_cached_variants", return_value=VARIANTS):
            return self.c.get(f"/manage/listings/{listing.pk}/").content.decode()

    def test_every_option_shows_its_swatch_and_name(self):
        html = self.page(self.listing())
        self.assertIn('style="background:#0b0b0b"', html)
        self.assertIn('style="background:#b8a77f"', html)
        self.assertIn("linear-gradient(135deg, #c8c8c8 50%, #1c2a4a 50%)", html)
        for name in ("Black", "Khaki", "Mystery"):
            self.assertIn(f'<span class="color-picker__name">{name}</span>', html)

    def test_the_current_color_starts_selected_with_its_swatch_and_photo(self):
        html = self.page(self.listing(color="Black"))
        self.assertIn('data-value="Black"', html)
        self.assertIn('data-swatch="#0b0b0b"', html)
        self.assertIn('data-image="https://files.cdn.printful.com/p/black.jpg"', html)
        self.assertIn('<input type="hidden" id="color" name="color" value="Black"', html)

    def test_the_product_link_is_offered_for_the_chosen_blank(self):
        html = self.page(self.listing())
        self.assertIn('data-product-url="https://www.printful.com/dashboard/custom/mens/t-shirts/'
                      'unisex-garment-dyed-heavyweight-t-shirt-comfort-colors-1717"', html)
        self.assertIn("See this color on Printful", html)

    def test_no_link_when_the_blank_has_no_name(self):
        html = self.page(self.listing(name=""))
        self.assertIn('data-product-url=""', html)

    def test_an_unknown_color_is_flagged_and_kept(self):
        html = self.page(self.listing(color="Bay"))
        self.assertIn("is not a real Printful color", html)
        self.assertIn('value="Bay"', html)

    def test_hostile_api_values_cannot_inject_into_the_page(self):
        bad = {"variants": [{"color": "X", "color_code": '#ff0000" onmouseover="alert(1)', "image": 'https://a.test/x" onerror="y'}]}
        listing = self.listing(color="X")
        with mock.patch.object(printful, "_cached_variants", return_value=bad):
            html = self.c.get(f"/manage/listings/{listing.pk}/").content.decode()
        self.assertNotIn("onmouseover", html)
        self.assertNotIn('onerror="y', html)

    def test_saving_posts_the_hidden_inputs_value(self):
        listing = self.listing(color="")
        self.c.post(f"/manage/listings/{listing.pk}/", {
            "title": "W", "color": "Black", "base_cost": "11", "shipping_est": "5", "price": "40",
            "print_scale_pct": "100", "print_position": "center"})
        listing.refresh_from_db()
        self.assertEqual(listing.color, "Black")
