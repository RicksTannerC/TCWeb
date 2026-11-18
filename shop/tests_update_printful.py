"""The listing editor's one Printful action: Update Printful. Sends a listing that isn't on Printful, and builds a
new, version-numbered product for one that is, matching sizes first when it has to. Printful is a stub throughout
(no real call), and the old product is never touched."""

from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings

from tshirtbrand.adapters.persistence.django_orm.listings import DjangoListingRepository

from . import printful
from .models import Design, Listing, ListingPrint, ListingSize, ProductTemplate


@override_settings(STAFF_2FA_REQUIRED=False)
class UpdatePrintfulTests(TestCase):
    def setUp(self):
        cache.clear()
        self.c = Client()
        self.c.force_login(get_user_model().objects.create_user("cur", password="x-12345-yz", is_staff=True))

    def listing(self, sent=True, color="Khaki", labels=("S", "M")):
        tpl = ProductTemplate.objects.create(name="Tee", product_type="tee", printful_blueprint_id="456")
        listing = Listing.objects.create(design=Design.objects.create(title="Wanderer"), template=tpl,
                                         product_type="tee", color=color)
        for i, label in enumerate(labels):
            ListingSize.objects.create(listing=listing, label=label, printful_catalog_variant_id=str(4000 + i),
                                       printful_variant_id=str(9000 + i) if sent else "")
        if sent:
            repo = DjangoListingRepository()
            repo.set_product(listing.pk, "474865517")
            repo.mark_sent(listing.pk, "hidden")       # records what was sent, as a real send does
            listing.refresh_from_db()
        return listing

    def fake_printful(self):
        client = mock.MagicMock(is_mock=False)

        def create(payload):
            return {"sync_product": {"id": 999},
                    "sync_variants": [{"id": 8000 + i, "external_id": v["external_id"]}
                                      for i, v in enumerate(payload["sync_variants"])]}
        client.create_sync_product.side_effect = create
        return client

    def update(self, listing, client=None):
        client = client or self.fake_printful()
        with mock.patch.object(printful, "get_client", return_value=client):
            r = self.c.post(f"/manage/listings/{listing.pk}/update-printful/")
        self.assertEqual(r.status_code, 302)
        listing.refresh_from_db()
        return client, self.c.get(r["Location"].split("?")[0])

    def sent_name(self, client):
        return client.create_sync_product.call_args[0][0]["sync_product"]["name"]

    def test_a_listing_not_on_printful_is_sent_as_the_first_version(self):
        listing = self.listing(sent=False)
        client, page = self.update(listing)
        self.assertEqual(self.sent_name(client), "Wanderer 1.0.0")
        self.assertEqual((listing.printful_product_id, listing.version), ("999", "1.0.0"))
        self.assertContains(page, "Sent to Printful as")
        self.assertContains(page, "Wanderer 1.0.0")

    def test_a_front_change_makes_a_new_product_one_step_up_the_second_number(self):
        listing = self.listing()
        listing.print_scale_pct = 60
        listing.save()
        client, page = self.update(listing)
        self.assertEqual((self.sent_name(client), listing.version), ("Wanderer 1.1.0", "1.1.0"))
        self.assertContains(page, "Wanderer 1.0.0")                     # the old one is named so it can be found and deleted
        self.assertContains(page, "474865517")
        self.assertEqual(listing.printful_product_id, "999")

    def test_a_back_print_is_the_third_number(self):
        listing = self.listing()
        ListingPrint.objects.create(listing=listing, placement="back", scale_pct=100)
        client, _ = self.update(listing)
        self.assertEqual((self.sent_name(client), listing.version), ("Wanderer 1.0.1", "1.0.1"))

    def test_a_new_color_is_a_whole_listing_change_and_starts_front_and_back_again(self):
        listing = self.listing()
        Listing.objects.filter(pk=listing.pk).update(version_front=2, version_back=3)
        listing.color = "Black"
        listing.save()
        client, _ = self.update(listing)
        self.assertEqual((self.sent_name(client), listing.version), ("Wanderer 2.0.0", "2.0.0"))

    def test_a_rebuild_with_nothing_changed_is_still_a_new_whole_version(self):
        listing = self.listing()
        client, _ = self.update(listing)
        self.assertEqual((self.sent_name(client), listing.version), ("Wanderer 2.0.0", "2.0.0"))

    def test_a_product_sent_before_versions_is_named_without_a_number_in_the_message(self):
        listing = self.listing()
        Listing.objects.filter(pk=listing.pk).update(printful_sent_front="", printful_sent_back="")
        client, page = self.update(listing)
        self.assertEqual(listing.version, "2.0.0")
        self.assertContains(page, "old one, “Wanderer” ")

    def test_the_old_product_is_never_deleted(self):
        client, _ = self.update(self.listing())
        self.assertFalse([c for c in client.method_calls if "delete" in c[0] or "cancel" in c[0]])

    def test_a_refusal_leaves_the_listing_on_its_old_product_and_version(self):
        listing = self.listing()
        client = mock.MagicMock(is_mock=False)
        client.create_sync_product.side_effect = printful.PrintfulError("nope")
        _, page = self.update(listing, client)
        self.assertContains(page, "wouldn")
        self.assertEqual((listing.printful_product_id, listing.version), ("474865517", "1.0.0"))

    def test_sizes_with_no_printful_variant_are_matched_first_and_nothing_is_sent_if_they_cannot_be(self):
        listing = self.listing(sent=False)
        listing.sizes.update(printful_catalog_variant_id="")
        client = self.fake_printful()
        client.catalog_variants.return_value = {"variants": [{"id": 1, "color": "Khaki", "size": "S"}]}   # no M
        _, page = self.update(listing, client)
        client.create_sync_product.assert_not_called()
        self.assertContains(page, "Nothing was sent to Printful")
        self.assertEqual(listing.printful_product_id, "")

    def test_matched_sizes_go_on_to_the_send(self):
        listing = self.listing(sent=False)
        listing.sizes.update(printful_catalog_variant_id="")
        client = self.fake_printful()
        client.catalog_variants.return_value = {"variants": [
            {"id": 11, "color": "Khaki", "size": "S"}, {"id": 12, "color": "Khaki", "size": "M"}]}
        self.update(listing, client)
        payload = client.create_sync_product.call_args[0][0]
        self.assertEqual([v["variant_id"] for v in payload["sync_variants"]], [11, 12])

    def test_a_listing_whose_template_has_no_printful_product_is_told_so(self):
        listing = self.listing(sent=False)
        listing.template.printful_blueprint_id = ""
        listing.template.save()
        client, page = self.update(listing)
        client.create_sync_product.assert_not_called()
        self.assertContains(page, "no Printful product chosen")

    def test_it_needs_staff_and_post(self):
        listing = self.listing()
        self.assertEqual(Client().post(f"/manage/listings/{listing.pk}/update-printful/").status_code, 302)
        self.assertEqual(self.c.get(f"/manage/listings/{listing.pk}/update-printful/").status_code, 405)


@override_settings(STAFF_2FA_REQUIRED=False)
class PreviewPanelTests(TestCase):
    def setUp(self):
        self.c = Client()
        self.c.force_login(get_user_model().objects.create_user("cur", password="x-12345-yz", is_staff=True))
        tpl = ProductTemplate.objects.create(name="Tee", product_type="tee", printful_blueprint_id="456")
        self.listing = Listing.objects.create(design=Design.objects.create(title="W"), template=tpl, product_type="tee",
                                              color="Khaki", printful_product_id="555")
        ListingSize.objects.create(listing=self.listing, label="S", printful_catalog_variant_id="1")

    def panel(self, preview, query=""):
        client = mock.MagicMock(is_mock=False)
        client.get_sync_product.return_value = {"sync_product": {"id": 555}, "sync_variants": [
            {"id": 1, "external_id": "w::S", "size": "S", "color": "Khaki", "product": {}, "files": preview}]}
        with mock.patch.object(printful, "get_client", return_value=client):
            return self.c.post(f"/manage/listings/{self.listing.pk}/preview-panel/{query}")

    def test_with_no_preview_yet_and_wait_it_asks_again_in_twenty_seconds(self):
        html = self.panel([], "?wait=1&n=0").content.decode()
        self.assertIn('hx-trigger="load delay:20s"', html)
        self.assertIn("n=1", html)
        self.assertIn("checks again by itself", html)

    def test_it_stops_asking_after_five_tries(self):
        html = self.panel([], "?wait=1&n=5").content.decode()
        self.assertNotIn("hx-trigger", html)
        self.assertIn("No preview yet", html)

    def test_a_plain_refresh_asks_once_and_does_not_poll(self):
        html = self.panel([]).content.decode()
        self.assertNotIn("hx-trigger", html)

    def test_the_editor_starts_polling_only_after_an_update(self):
        page = self.c.get(f"/manage/listings/{self.listing.pk}/").content.decode()
        self.assertNotIn('hx-trigger="load delay:20s"', page)
        page = self.c.get(f"/manage/listings/{self.listing.pk}/?preview=wait").content.decode()
        self.assertIn('hx-trigger="load delay:20s"', page)

    def test_it_needs_staff_and_post(self):
        self.assertEqual(Client().post(f"/manage/listings/{self.listing.pk}/preview-panel/").status_code, 302)
        self.assertEqual(self.c.get(f"/manage/listings/{self.listing.pk}/preview-panel/").status_code, 405)
