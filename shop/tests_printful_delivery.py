"""The signed, expiring link that lets Printful fetch a private design original."""

import os
import tempfile
import time
from urllib.parse import urlsplit

from django.core.files.base import ContentFile
from django.test import Client, TestCase, override_settings

from .models import Design
from .printful_delivery import build_delivery_url, verify_token

SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10"/></svg>'


@override_settings(STAFF_2FA_REQUIRED=False)
class PrintfulDeliveryTests(TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.enterContext(override_settings(
            MEDIA_ROOT=os.path.join(tmp.name, "public"),
            PRIVATE_MEDIA_ROOT=os.path.join(tmp.name, "private"),
            SITE_BASE_URL="https://shop.example.test",
        ))
        self.design = Design.objects.create(title="Pillars")
        self.design.artwork.save("pillars.svg", ContentFile(SVG), save=True)

    def path(self, url):
        return urlsplit(url).path

    def test_no_artwork_means_no_url(self):
        empty = Design.objects.create(title="Empty")
        self.assertIsNone(build_delivery_url(empty))

    def test_url_is_absolute_and_under_the_public_site(self):
        url = build_delivery_url(self.design)
        self.assertTrue(url.startswith("https://shop.example.test/printful/artwork/"))

    def test_a_fresh_link_serves_the_file_unauthenticated(self):
        r = Client().get(self.path(build_delivery_url(self.design)))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "image/svg+xml")
        self.assertEqual(b"".join(r.streaming_content), SVG)
        self.assertEqual(r["X-Content-Type-Options"], "nosniff")
        self.assertIn("no-store", r["Cache-Control"])

    def test_it_is_not_gated_by_staff_login_or_two_factor(self):
        with override_settings(STAFF_2FA_REQUIRED=True):
            r = Client().get(self.path(build_delivery_url(self.design)))
        self.assertEqual(r.status_code, 200)
        r.close()

    @override_settings(PRINTFUL_ARTWORK_LINK_MAX_AGE=1)
    def test_link_expires(self):
        url = build_delivery_url(self.design)
        time.sleep(1.2)
        self.assertEqual(Client().get(self.path(url)).status_code, 404)

    def test_tampered_token_is_refused(self):
        url = build_delivery_url(self.design)
        broken = url[:-2] + ("a" if url[-2] != "a" else "b") + url[-1]
        self.assertEqual(Client().get(self.path(broken)).status_code, 404)

    def test_token_does_not_work_for_a_different_design(self):
        other = Design.objects.create(title="Other")
        other.artwork.save("other.svg", ContentFile(SVG), save=True)
        url = build_delivery_url(self.design)
        swapped = url.replace(f"/{self.design.pk}/", f"/{other.pk}/")
        self.assertEqual(Client().get(self.path(swapped)).status_code, 404)

    def test_link_dies_the_moment_the_artwork_is_replaced(self):
        url = build_delivery_url(self.design)
        self.design.artwork.save("new.svg", ContentFile(SVG + b"<!--v2-->"), save=True)
        self.assertEqual(Client().get(self.path(url)).status_code, 404)
        # ...but a freshly built link for the new file works.
        r = Client().get(self.path(build_delivery_url(self.design)))
        self.assertEqual(r.status_code, 200)
        r.close()

    def test_link_dies_if_the_design_is_deleted(self):
        url = build_delivery_url(self.design)
        self.design.delete()
        self.assertEqual(Client().get(self.path(url)).status_code, 404)

    def test_unknown_design_id_is_404_not_500(self):
        self.assertEqual(Client().get("/printful/artwork/999999/garbage/").status_code, 404)

    def test_verify_token_returns_the_design_object(self):
        url = build_delivery_url(self.design)
        token = url.rsplit("/artwork/", 1)[1].rstrip("/").split("/", 1)[1]
        self.assertEqual(verify_token(self.design.pk, token), self.design)

    def test_missing_file_on_disk_is_404_not_500(self):
        url = build_delivery_url(self.design)
        os.remove(self.design.artwork.path)
        self.assertEqual(Client().get(self.path(url)).status_code, 404)

    @override_settings(
        CONSOLE_HOST="manage.example.test", ALLOWED_HOSTS=["manage.example.test", "shop.example.test", "testserver"])
    def test_served_from_the_public_host_not_gated_by_the_console_host(self):
        url = build_delivery_url(self.design)
        path = self.path(url)
        r = Client(HTTP_HOST="shop.example.test").get(path)
        self.assertEqual(r.status_code, 200)
        r.close()
        # The console host serves only console/admin/media routes; this isn't one.
        self.assertEqual(Client(HTTP_HOST="manage.example.test").get(path).status_code, 404)
