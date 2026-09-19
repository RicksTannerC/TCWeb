"""The public media folder: mockups are served, and nothing else is."""

import os
import tempfile
from decimal import Decimal

from django.core.files.base import ContentFile
from django.test import Client, TestCase, override_settings

from .models import Design, Listing, ListingImage, ProductTemplate, Status
from .tests_templates_intake import TEE_SIZES, png

PNG = png().read()


@override_settings(STAFF_2FA_REQUIRED=False)
class PublicMediaTests(TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.public = os.path.join(tmp.name, "public")
        self.private = os.path.join(tmp.name, "private")
        self.enterContext(override_settings(MEDIA_ROOT=self.public, PRIVATE_MEDIA_ROOT=self.private))
        os.makedirs(os.path.join(self.public, "listings"))
        os.makedirs(os.path.join(self.private, "designs"))
        self.write(self.public, "listings/mock.png", PNG)
        self.write(self.public, "listings/photo.JPG", PNG)
        self.write(self.public, "listings/evil.svg", b"<svg xmlns='http://www.w3.org/2000/svg'><script>1</script></svg>")
        self.write(self.public, "listings/page.html", b"<script>alert(1)</script>")
        self.write(self.public, "listings/notes.txt", b"hello")
        self.write(self.public, "listings/noext", b"hello")
        self.write(self.private, "designs/original.png", PNG)

    def write(self, root, rel, data):
        with open(os.path.join(root, rel), "wb") as fh:
            fh.write(data)

    def get(self, path, client=None):
        r = (client or Client()).get(path)
        r.close()
        return r

    def test_an_image_is_served_to_anyone_with_safe_headers(self):
        r = Client().get("/media/listings/mock.png")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "image/png")
        self.assertEqual(b"".join(r.streaming_content), PNG)
        self.assertEqual(r["X-Content-Type-Options"], "nosniff")
        self.assertIn("public", r["Cache-Control"])
        self.assertIn("max-age=86400", r["Cache-Control"])

    def test_extension_check_is_case_insensitive(self):
        self.assertEqual(self.get("/media/listings/photo.JPG").status_code, 200)

    def test_only_plain_images_are_served(self):
        for name in ("evil.svg", "page.html", "notes.txt", "noext"):
            self.assertEqual(self.get(f"/media/listings/{name}").status_code, 404, name)

    def test_missing_files_and_bare_directory_are_404(self):
        for path in ("/media/listings/nope.png", "/media/listings/", "/media/"):
            self.assertEqual(self.get(path).status_code, 404, path)

    def test_the_private_originals_cannot_be_reached_through_media(self):
        for path in (
            "/media/designs/original.png",
            "/media/../private/designs/original.png",
            "/media/listings/..%2f..%2fprivate%2fdesigns%2foriginal.png",
            "/media/listings/%2e%2e/%2e%2e/private/designs/original.png",
        ):
            r = self.get(path)
            self.assertIn(r.status_code, (400, 404), path)      # refused, never served
            self.assertNotEqual(r.status_code, 200, path)

    @override_settings(
        CONSOLE_HOST="manage.example.test", SITE_BASE_URL="https://shop.example.test",
        ALLOWED_HOSTS=["manage.example.test", "shop.example.test", "testserver"])
    def test_served_from_both_hosts(self):
        for host in ("shop.example.test", "manage.example.test"):
            self.assertEqual(self.get("/media/listings/mock.png", Client(HTTP_HOST=host)).status_code, 200, host)
        # ...but not the non-image, and still not the original
        console = Client(HTTP_HOST="manage.example.test")
        self.assertEqual(self.get("/media/listings/evil.svg", console).status_code, 404)
        self.assertEqual(self.get("/media/designs/original.png", console).status_code, 404)

    def test_a_live_listing_shows_its_mockup_and_the_image_loads(self):
        tpl = ProductTemplate.objects.create(name="Tee", product_type="tee", base_cost=Decimal("15"),
                                             shipping_est=Decimal("6"), default_sizes=TEE_SIZES)
        design = Design.objects.create(title="Pillars")
        listing = Listing.objects.create(design=design, template=tpl, product_type="tee",
                                         status=Status.LIVE, price=Decimal("40"))
        image = ListingImage(listing=listing, kind=ListingImage.Kind.MOCKUP)
        image.image.save("mockup.png", ContentFile(PNG), save=True)
        self.assertTrue(image.image.url.startswith("/media/listings/"))
        for page in ("/shop/", f"/shirts/{listing.slug}/"):
            html = Client().get(page).content.decode()
            self.assertIn(image.image.url, html, page)
        self.assertEqual(self.get(image.image.url).status_code, 200)
