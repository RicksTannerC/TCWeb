"""Switching a listing to another product template (e.g. a different shirt). Local only:
nothing here talks to Printful."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

from .console_views import parse_sizes
from .models import Design, Listing, ListingPrint, ListingSize, PrintPlacement, ProductTemplate


@override_settings(STAFF_2FA_REQUIRED=False)
class TemplateSwitchTests(TestCase):
    def setUp(self):
        self.c = Client()
        self.c.force_login(get_user_model().objects.create_user("cur", password="x-12345-yz", is_staff=True))
        self.old = ProductTemplate.objects.create(
            name="Heavyweight", product_type="tee", printful_blueprint_id="586", base_cost=Decimal("15.00"),
            shipping_est=Decimal("6.00"), print_placement="back")
        self.new = ProductTemplate.objects.create(
            name="Bella", product_type="tee", printful_blueprint_id="71", base_cost=Decimal("13.92"),
            shipping_est=Decimal("5.50"), print_placement="back")
        self.sticker = ProductTemplate.objects.create(name="Sticker", product_type="sticker")
        self.listing = Listing.objects.create(
            design=Design.objects.create(title="Jack-o"), template=self.old, product_type="tee", color="Ivory",
            price=Decimal("30.00"), base_cost=Decimal("21.55"), shipping_est=Decimal("6.00"),
            printful_product_id="477", printful_sent_blueprint_id="586", printful_sent_color="Ivory")
        self.size = ListingSize.objects.create(
            listing=self.listing, label="M", printful_variant_id="5539558979", printful_catalog_variant_id="9001")
        self.url = f"/manage/listings/{self.listing.pk}/"

    def post(self, **over):
        data = {"title": "Jack-o", "color": "Ivory", "price": "30.00", "base_cost": "21.55", "shipping_est": "6.00",
                "template": str(self.old.pk)}
        data.update(over)
        return self.c.post(self.url, data)

    def test_the_form_offers_templates_of_the_same_kind_only(self):
        page = self.c.get(self.url)
        self.assertContains(page, "Shirt (template)")
        self.assertContains(page, "Bella")
        self.assertNotContains(page, f'<option value="{self.sticker.pk}"')

    def test_switching_changes_the_template_and_costs_but_not_the_price(self):
        self.post(template=str(self.new.pk))
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.template, self.new)
        self.assertEqual((self.listing.base_cost, self.listing.shipping_est), (Decimal("13.92"), Decimal("5.50")))
        self.assertEqual(self.listing.price, Decimal("30.00"))

    def test_the_old_product_keeps_its_order_ids_but_the_catalog_id_is_cleared(self):
        self.post(template=str(self.new.pk))
        self.size.refresh_from_db()
        self.assertEqual(self.size.printful_variant_id, "5539558979")
        self.assertEqual(self.size.printful_catalog_variant_id, "")
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.printful_product_id, "477")

    def test_the_banner_says_printful_still_has_the_old_shirt(self):
        self.post(template=str(self.new.pk))
        page = self.c.get(self.url)
        self.assertContains(page, "Printful still has the old version")
        self.assertContains(page, "shirt (product 586")

    def test_message_explains_the_next_steps(self):
        r = self.post(template=str(self.new.pk))
        page = self.c.get(r["Location"])
        self.assertContains(page, "Changed the shirt to Bella")
        self.assertContains(page, "Re-send to Printful")

    def test_saving_without_changing_it_keeps_hand_set_costs(self):
        self.post(base_cost="22.10")
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.template, self.old)
        self.assertEqual(self.listing.base_cost, Decimal("22.10"))
        self.size.refresh_from_db()
        self.assertEqual(self.size.printful_catalog_variant_id, "9001")

    def test_another_kind_of_template_is_refused(self):
        r = self.post(template=str(self.sticker.pk))
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.template, self.old)
        self.assertContains(self.c.get(r["Location"]), "isn&#x27;t a template this listing can switch to")

    def test_junk_ids_are_ignored(self):
        for junk in ("abc", "99999", "-1", "1; drop"):
            self.post(template=junk)
            self.listing.refresh_from_db()
            self.assertEqual(self.listing.template, self.old, junk)

    def test_a_clash_with_an_additional_print_blocks_the_switch_but_saves_the_rest(self):
        self.new.print_placement = "front"
        self.new.save()
        ListingPrint.objects.create(listing=self.listing, placement=PrintPlacement.FRONT, scale_pct=30)
        r = self.post(template=str(self.new.pk), price="31.00")
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.template, self.old)
        self.assertEqual(self.listing.price, Decimal("31.00"))
        self.assertEqual(self.listing.base_cost, Decimal("21.55"))
        self.assertContains(self.c.get(r["Location"]), "already has an additional print")

    def test_login_is_required(self):
        self.assertNotEqual(Client().post(self.url, {"template": str(self.new.pk)}).status_code, 200)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.template, self.old)


class SizeBoxTests(TestCase):
    def test_tab_separated_rows_from_a_spreadsheet_parse(self):
        sizes, err = parse_sizes("S\t28\t18\nM\t29\t20")
        self.assertIsNone(err)
        self.assertEqual(sizes, [{"label": "S", "width_in": 28, "height_in": 18},
                                 {"label": "M", "width_in": 29, "height_in": 20}])

    def test_commas_still_work(self):
        sizes, _ = parse_sizes("M, 20, 29")
        self.assertEqual(sizes, [{"label": "M", "width_in": 20, "height_in": 29}])
