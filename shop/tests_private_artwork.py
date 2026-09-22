"""Print-ready originals are private: stored outside public media, shown only in the console."""

import os
import tempfile
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings

from . import printful
from .fulfillment import _line
from .models import Design, Listing, ListingSize, ProductTemplate, ProductType
from .storage import get_private_storage
from .tests_2fa import totp_now
from .tests_templates_intake import TEE_SIZES, png

SVG = b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10" fill="#4b5034"/></svg>'


def svg(name="pillars.svg", data=SVG):
    return SimpleUploadedFile(name, data, content_type="image/svg+xml")


class PrivateBase(TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.public = os.path.join(tmp.name, "public")
        self.private = os.path.join(tmp.name, "private")
        self.enterContext(override_settings(
            MEDIA_ROOT=self.public, PRIVATE_MEDIA_ROOT=self.private, STAFF_2FA_REQUIRED=False))
        self.staff = get_user_model().objects.create_user("curator", password="x-12345-yz", is_staff=True, is_superuser=True)
        self.c = Client()
        self.c.force_login(self.staff)
        self.tee = ProductTemplate.objects.create(
            name="Tee", product_type=ProductType.TEE, base_cost=Decimal("11"), shipping_est=Decimal("5"),
            default_sizes=TEE_SIZES)

    def files_under(self, root):
        return [os.path.join(d, f) for d, _, fs in os.walk(root) for f in fs]

    def design_with(self, name, data):
        d = Design.objects.create(title="Pillars")
        d.artwork.save(name, ContentFile(data), save=True)
        return d


class SvgIntakeTests(PrivateBase):
    def upload(self, *files):
        return self.c.post("/manage/listings/intake/", {"artwork": list(files)})

    def test_svg_is_accepted_and_stored_privately(self):
        self.upload(svg())
        design = Design.objects.get()
        self.assertTrue(design.artwork.name.endswith(".svg"))
        self.assertEqual(len(self.files_under(self.private)), 1)
        self.assertEqual(self.files_under(self.public), [])          # nothing in public media
        self.assertEqual(Listing.objects.filter(design=design).count(), 1)

    def test_png_originals_are_private_too(self):
        self.upload(png("art.png"))
        self.assertEqual(len(self.files_under(self.private)), 1)
        self.assertEqual(self.files_under(self.public), [])

    def test_unsafe_or_broken_svgs_are_rejected(self):
        bad = {
            "script.svg": b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
            "js-link.svg": b'<svg xmlns="http://www.w3.org/2000/svg"><a href="javascript:alert(1)"><rect/></a></svg>',
            "entity.svg": b'<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY a "aaaa">]><svg xmlns="http://www.w3.org/2000/svg">&a;</svg>',
            "notsvg.svg": b"<html><body>hi</body></html>",
            "broken.svg": b"<svg xmlns='http://www.w3.org/2000/svg'><rect></svg>",
            "empty.svg": b"",
        }
        r = self.upload(*[svg(n, d) for n, d in bad.items()], png("ok.png"))
        self.assertEqual([d.title for d in Design.objects.all()], ["Ok"])
        self.assertEqual(len(self.files_under(self.private)), 1)
        from django.contrib.messages import get_messages
        text = " ".join(str(m) for m in get_messages(r.wsgi_request))
        for name in bad:
            self.assertIn(name, text)


class ArtworkViewTests(PrivateBase):
    def test_serves_an_svg_with_a_locked_down_policy(self):
        d = self.design_with("pillars.svg", SVG)
        r = self.c.get(f"/manage/designs/{d.pk}/artwork/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "image/svg+xml")
        self.assertEqual(b"".join(r.streaming_content), SVG)
        self.assertIn("sandbox", r["Content-Security-Policy"])
        self.assertIn("default-src 'none'", r["Content-Security-Policy"])
        self.assertEqual(r["X-Content-Type-Options"], "nosniff")
        self.assertIn("no-store", r["Cache-Control"])

    def test_serves_a_png_with_its_own_type(self):
        f = png("a.png")
        d = self.design_with("a.png", f.read())
        r = self.c.get(f"/manage/designs/{d.pk}/artwork/")
        self.assertEqual(r["Content-Type"], "image/png")
        r.close()

    def test_requires_a_signed_in_staff_user(self):
        d = self.design_with("pillars.svg", SVG)
        url = f"/manage/designs/{d.pk}/artwork/"
        r = Client().get(url)
        self.assertEqual(r.status_code, 302)
        self.assertIn("/admin/login/", r["Location"])
        customer = get_user_model().objects.create_user("customer", password="x-12345-yz")
        other = Client()
        other.force_login(customer)
        self.assertEqual(other.get(url).status_code, 302)

    @override_settings(STAFF_2FA_REQUIRED=True)
    def test_password_alone_is_not_enough(self):
        d = self.design_with("pillars.svg", SVG)
        r = self.c.get(f"/manage/designs/{d.pk}/artwork/")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r["Location"].startswith("/manage/2fa/"))

    def test_missing_pieces_are_404_not_500(self):
        self.assertEqual(self.c.get("/manage/designs/999/artwork/").status_code, 404)
        empty = Design.objects.create(title="Empty")
        self.assertEqual(self.c.get(f"/manage/designs/{empty.pk}/artwork/").status_code, 404)
        d = self.design_with("gone.svg", SVG)
        os.remove(self.files_under(self.private)[0])
        self.assertEqual(self.c.get(f"/manage/designs/{d.pk}/artwork/").status_code, 404)

    def test_console_pages_use_the_view_not_a_file_url(self):
        d = self.design_with("pillars.svg", SVG)
        Listing.objects.create(design=d, template=self.tee, product_type="tee")
        html = self.c.get("/manage/listings/").content.decode()
        self.assertIn(f"/manage/designs/{d.pk}/artwork/", html)
        self.assertNotIn("private", html.lower().replace("private, no-store", ""))

    def test_the_raw_admin_change_page_still_loads(self):
        d = self.design_with("pillars.svg", SVG)
        r = self.c.get(f"/admin/shop/design/{d.pk}/change/")
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "artwork")


class NoPublicAccessTests(PrivateBase):
    def test_files_have_no_public_url_and_are_outside_media(self):
        d = self.design_with("pillars.svg", SVG)
        with self.assertRaises(ValueError):
            d.artwork.url
        self.assertTrue(self.files_under(self.private))
        self.assertFalse(get_private_storage().location.startswith(self.public))
        self.assertEqual(Client().get(f"/media/{d.artwork.name}").status_code, 404)
        self.assertEqual(Client().get(f"/{d.artwork.name}").status_code, 404)

    def test_storage_follows_the_setting(self):
        self.assertEqual(get_private_storage().location, os.path.abspath(self.private))

    @override_settings(
        CONSOLE_HOST="manage.example.test", ALLOWED_HOSTS=["manage.example.test", "shop.example.test", "testserver"],
        SITE_BASE_URL="https://shop.example.test")
    def test_only_the_console_host_can_show_it(self):
        d = self.design_with("pillars.svg", SVG)
        console = Client(HTTP_HOST="manage.example.test")
        console.force_login(self.staff)
        r = console.get(f"/designs/{d.pk}/artwork/")
        self.assertEqual(r.status_code, 200)
        r.close()
        public = Client(HTTP_HOST="shop.example.test")
        public.force_login(self.staff)
        for path in (f"/designs/{d.pk}/artwork/", f"/manage/designs/{d.pk}/artwork/"):
            self.assertEqual(public.get(path).status_code, 404, path)


class PrintfulGuardTests(PrivateBase):
    """sync_listing() and order fulfillment lines, now that print_file_url is real."""

    def listing(self, with_art=True):
        d = self.design_with("pillars.svg", SVG) if with_art else Design.objects.create(title="No art")
        listing = Listing.objects.create(design=d, template=self.tee, product_type="tee")
        ListingSize.objects.create(listing=listing, label="M")
        return listing

    def test_real_printful_is_sent_a_working_signed_link_for_the_art(self):
        client = mock.MagicMock(is_mock=False)
        client.create_sync_product.return_value = {"id": 1, "sync_variants": []}
        listing = self.listing()
        with mock.patch.object(printful, "get_client", return_value=client):
            printful.sync_listing(listing)
        payload = client.create_sync_product.call_args[0][0]
        url = payload["sync_variants"][0]["files"][0]["url"]
        self.assertTrue(url.startswith(settings.SITE_BASE_URL))
        r = Client().get(urlsplit(url).path)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(b"".join(r.streaming_content), SVG)

    def test_mock_printful_still_works_locally(self):
        with mock.patch.object(printful, "get_client", return_value=printful.MockPrintful()):
            result = printful.sync_listing(self.listing())
        self.assertTrue(result)

    def test_listing_without_artwork_is_unaffected(self):
        client = mock.MagicMock(is_mock=False)
        client.create_sync_product.return_value = {"id": 1, "sync_variants": []}
        with mock.patch.object(printful, "get_client", return_value=client):
            printful.sync_listing(self.listing(with_art=False))
        payload = client.create_sync_product.call_args[0][0]
        self.assertEqual(payload["sync_variants"][0]["files"], [])

    def test_order_fulfillment_lines_now_carry_a_working_signed_link(self):
        item = SimpleNamespace(listing=self.listing(), quantity=1, design_title="Pillars", unit_price=Decimal("40"))
        url = _line(item)["files"][0]["url"]
        r = Client().get(urlsplit(url).path)
        self.assertEqual(r.status_code, 200)
        r.close()

    def test_order_lines_have_no_url_when_the_design_has_no_artwork(self):
        item = SimpleNamespace(listing=self.listing(with_art=False), quantity=1, design_title="No art", unit_price=Decimal("40"))
        self.assertEqual(_line(item)["files"], [])
