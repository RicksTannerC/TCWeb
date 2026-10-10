"""Printful's own render of the art on the shirt, shown on the listing page so the
placement, size and colour can be checked before listing. Stub replies only."""

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

from . import printful
from .models import Design, Listing, ListingSize, ProductTemplate

CDN = "https://files.cdn.printful.com"


def reply(color="Ivory"):
    """A sync-product reply in the shape Printful returns."""
    def variant(i, size, col, preview):
        return {"id": 9000 + i, "external_id": f"x::{size}", "name": f"Jack-o / {col} / {size}",
                "size": size, "color": col, "variant_id": 100 + i,
                "files": [
                    {"type": "default", "preview_url": f"{CDN}/art-{i}.png", "thumbnail_url": f"{CDN}/art-{i}-t.png"},
                    {"type": "preview", "preview_url": preview, "thumbnail_url": preview + "-t"},
                ]}
    return {
        "sync_product": {"id": 477, "name": "Jack-o", "thumbnail_url": f"{CDN}/thumb.png"},
        "sync_variants": [
            variant(1, "S", "Black", f"{CDN}/black-S.jpg"),
            variant(2, "S", "Ivory", f"{CDN}/ivory-S.jpg"),
            variant(3, "M", "Ivory", f"{CDN}/ivory-M.jpg"),
        ],
    }


class ExtractTests(TestCase):
    def test_thumbnail_plus_the_previews_of_the_listings_colour(self):
        got = printful.extract_previews(reply(), "Ivory")
        self.assertEqual([p["url"] for p in got], [f"{CDN}/thumb.png", f"{CDN}/ivory-S.jpg"])
        self.assertEqual(got[1]["label"], "Ivory")

    def test_another_colours_preview_is_not_used(self):
        urls = [p["url"] for p in printful.extract_previews(reply(), "Ivory")]
        self.assertNotIn(f"{CDN}/black-S.jpg", urls)

    def test_art_files_are_not_mistaken_for_previews(self):
        urls = [p["url"] for p in printful.extract_previews(reply(), "Ivory")]
        self.assertFalse(any("art-" in u for u in urls))

    def test_no_colour_set_uses_the_first_variant_with_a_preview(self):
        urls = [p["url"] for p in printful.extract_previews(reply(), "")]
        self.assertIn(f"{CDN}/black-S.jpg", urls)

    def test_a_missing_preview_just_yields_fewer_images(self):
        r = reply()
        for sv in r["sync_variants"]:
            sv["files"] = [f for f in sv["files"] if f["type"] != "preview"]
        self.assertEqual([p["url"] for p in printful.extract_previews(r, "Ivory")], [f"{CDN}/thumb.png"])

    def test_nonsense_replies_do_not_raise(self):
        for junk in (None, [], "x", {}, {"sync_variants": None}, {"sync_variants": ["a"]},
                     {"sync_product": "x", "sync_variants": [{"files": "no"}]}):
            self.assertEqual(printful.extract_previews(junk, "Ivory"), [], junk)

    def test_only_https_images_are_kept(self):
        r = reply()
        r["sync_product"]["thumbnail_url"] = "http://insecure.test/t.png"
        r["sync_variants"][1]["files"][1]["preview_url"] = 'javascript:alert(1)'
        r["sync_variants"][1]["files"][1]["thumbnail_url"] = 'https://x.test/a.png" onerror="alert(1)'
        self.assertEqual(printful.extract_previews(r, "Ivory"), [])

    def test_at_most_six(self):
        r = {"sync_variants": [{"name": "J / Ivory / M", "files": [
            {"type": "preview", "preview_url": f"{CDN}/p{i}.jpg"} for i in range(10)]}]}
        self.assertEqual(len(printful.extract_previews(r, "Ivory")), 6)


def make_listing(connected=True, color="Ivory"):
    tpl, _ = ProductTemplate.objects.get_or_create(name="Tee", defaults={"product_type": "tee"})
    listing = Listing.objects.create(design=Design.objects.create(title="Jack-o"), template=tpl, product_type="tee",
                                     color=color, printful_product_id="477" if connected else "")
    ListingSize.objects.create(listing=listing, label="M")
    return listing


class StoreTests(TestCase):
    def stub(self, result=None, error=None):
        client = mock.MagicMock(is_mock=False)
        if error:
            client.get_sync_product.side_effect = printful.PrintfulError(error)
        else:
            client.get_sync_product.return_value = result if result is not None else reply()
        return client

    def test_refresh_preview_stores_the_images_and_when(self):
        listing = make_listing()
        with mock.patch.object(printful, "get_client", return_value=self.stub()):
            n = printful.refresh_preview(listing)
        listing.refresh_from_db()
        self.assertEqual(n, 2)
        self.assertEqual(len(listing.printful_preview), 2)
        self.assertIsNotNone(listing.printful_preview_checked)

    def test_refreshing_sizes_keeps_the_preview_at_no_extra_call(self):
        listing = make_listing()
        client = self.stub()
        with mock.patch.object(printful, "get_client", return_value=client):
            printful.refresh_sync_variants(listing)
        listing.refresh_from_db()
        self.assertEqual(len(listing.printful_preview), 2)
        self.assertEqual(client.get_sync_product.call_count, 1)

    def test_sending_a_listing_reads_the_product_back_and_keeps_its_preview(self):
        listing = make_listing(connected=False)
        client = self.stub()
        client.create_sync_product.return_value = {"id": 477, "variants": 1}  # the summary reply
        with mock.patch.object(printful, "get_client", return_value=client):
            printful.sync_listing(listing)
        listing.refresh_from_db()
        self.assertEqual(len(listing.printful_preview), 2)

    def test_not_connected_raises_a_clear_error(self):
        with self.assertRaisesMessage(printful.PrintfulError, "isn't connected"):
            printful.refresh_preview(make_listing(connected=False))


@override_settings(STAFF_2FA_REQUIRED=False)
class PreviewPageTests(TestCase):
    def setUp(self):
        self.c = Client()
        self.c.force_login(get_user_model().objects.create_user("cur", password="x-12345-yz", is_staff=True))

    def refresh(self, listing, client):
        with mock.patch.object(printful, "get_client", return_value=client):
            r = self.c.post(f"/manage/listings/{listing.pk}/refresh-preview/")
        return r, self.c.get(r["Location"])

    def stub(self, result=None, error=None):
        client = mock.MagicMock(is_mock=False)
        if error:
            client.get_sync_product.side_effect = printful.PrintfulError(error)
        else:
            client.get_sync_product.return_value = result if result is not None else reply()
        return client

    def test_the_panel_shows_the_images_after_a_refresh(self):
        listing = make_listing()
        r, page = self.refresh(listing, self.stub())
        self.assertRedirects(r, f"/manage/listings/{listing.pk}/#printful-preview", fetch_redirect_response=False)
        self.assertContains(page, "How it looks on Printful")
        self.assertContains(page, f'src="{CDN}/ivory-S.jpg"')
        self.assertContains(page, "Printful&#x27;s preview updated (2 images)")
        self.assertContains(page, "before you list it")

    def test_nothing_yet_says_to_try_again_and_the_panel_asks_for_a_refresh(self):
        listing = make_listing()
        _, page = self.refresh(listing, self.stub(result={"sync_product": {}, "sync_variants": []}))
        self.assertContains(page, "hasn&#x27;t produced a preview yet")
        self.assertContains(page, "No preview yet")

    def test_a_printful_error_is_reported_not_a_crash(self):
        listing = make_listing()
        r, page = self.refresh(listing, self.stub(error="boom"))
        self.assertEqual(r.status_code, 302)
        self.assertContains(page, "boom")

    def test_the_panel_only_exists_for_a_listing_on_printful(self):
        self.assertNotContains(self.c.get(f"/manage/listings/{make_listing(connected=False).pk}/"),
                               "How it looks on Printful")
        self.assertContains(self.c.get(f"/manage/listings/{make_listing().pk}/"), "How it looks on Printful")

    def test_post_only_and_staff_only(self):
        listing = make_listing()
        self.assertEqual(self.c.get(f"/manage/listings/{listing.pk}/refresh-preview/").status_code, 405)
        self.assertNotEqual(Client().post(f"/manage/listings/{listing.pk}/refresh-preview/").status_code, 200)

    def test_hostile_stored_urls_cannot_break_out_of_the_page(self):
        listing = make_listing()
        listing.printful_preview = [{"label": '"><script>alert(1)</script>', "url": 'https://x.test/a.png"><script>x</script>'}]
        listing.save()
        html = self.c.get(f"/manage/listings/{listing.pk}/").content.decode()
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertNotIn("<script>x</script>", html)
