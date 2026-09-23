"""Design slugs, the upload intake, and the product-template dashboard."""

import os
import tempfile
from decimal import Decimal
from io import BytesIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from PIL import Image

from .console_views import format_sizes, parse_sizes
from .models import Design, Listing, ListingSize, ProductTemplate, ProductType, Status, unique_slug

TEE_SIZES = [{"label": "M", "width_in": 20, "height_in": 29}, {"label": "L", "width_in": 22, "height_in": 30}]


def png(name="art.png", color="red"):
    buf = BytesIO()
    Image.new("RGB", (8, 8), color).save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


class SlugTests(TestCase):
    def test_same_title_gets_a_free_slug_instead_of_crashing(self):
        slugs = [Design.objects.create(title="Pillars").slug for _ in range(3)]
        self.assertEqual(slugs, ["pillars", "pillars-2", "pillars-3"])

    def test_title_with_nothing_sluggable_still_gets_a_slug(self):
        a = Design.objects.create(title="!!!")
        b = Design.objects.create(title="???")
        self.assertEqual((a.slug, b.slug), ("design", "design-2"))

    def test_resaving_keeps_the_slug_and_explicit_slugs_are_respected(self):
        d = Design.objects.create(title="Pillars")
        Design.objects.create(title="Pillars")
        d.title = "Pillars renamed"
        d.save()
        self.assertEqual(Design.objects.get(pk=d.pk).slug, "pillars")
        self.assertEqual(Design.objects.create(title="x", slug="custom").slug, "custom")

    def test_template_slugs_are_unique_too(self):
        a = ProductTemplate.objects.create(name="Tee!", product_type=ProductType.TEE)
        b = ProductTemplate.objects.create(name="Tee?", product_type=ProductType.TEE)
        self.assertNotEqual(a.slug, b.slug)

    def test_helper_truncates_long_text(self):
        slug = unique_slug(Design, "word " * 100, max_length=140)
        self.assertLessEqual(len(slug), 140)


class ParseSizesTests(TestCase):
    def test_parses_label_width_height(self):
        sizes, err = parse_sizes("S, 18, 28\nM, 20.5, 29\n\nOne size")
        self.assertIsNone(err)
        self.assertEqual(sizes, [
            {"label": "S", "width_in": 18, "height_in": 28},
            {"label": "M", "width_in": 20.5, "height_in": 29},
            {"label": "One size"},
        ])

    def test_round_trips(self):
        text = "S, 18, 28\nM, 20.5, 29"
        sizes, _ = parse_sizes(text)
        self.assertEqual(format_sizes(sizes), text)

    def test_rejects_bad_input_with_a_helpful_message(self):
        for text, fragment in [
            ("", "at least one size"),
            ("M, wide, 29", "isn't a number"),
            ("M, 20, 29, 5", "label, width, height"),
            ("M, 20\nm, 21", "same label"),
            ("M, -3", "between 0 and 1000"),
            ("A" * 17 + ", 1", "16 characters"),
        ]:
            sizes, err = parse_sizes(text)
            self.assertIsNone(sizes, text)
            self.assertIn(fragment, err, text)


@override_settings(STAFF_2FA_REQUIRED=False)
class IntakeTests(TestCase):
    def setUp(self):
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        self.enterContext(override_settings(
            MEDIA_ROOT=os.path.join(media.name, "public"),
            PRIVATE_MEDIA_ROOT=os.path.join(media.name, "private"),
        ))
        self.media = os.path.join(media.name, "private")   # where the originals go
        self.staff = get_user_model().objects.create_user("curator", password="x-12345-yz", is_staff=True)
        self.c = Client()
        self.c.force_login(self.staff)
        self.tee = ProductTemplate.objects.create(
            name="Tee", product_type=ProductType.TEE, base_cost=Decimal("11"), shipping_est=Decimal("5"),
            default_sizes=TEE_SIZES)
        self.sticker = ProductTemplate.objects.create(
            name="Sticker", product_type=ProductType.STICKER, base_cost=Decimal("1.8"), shipping_est=Decimal("0.5"),
            default_sizes=[{"label": '3"', "width_in": 3, "height_in": 3}])

    def files_on_disk(self):
        return [f for _, _, fs in os.walk(self.media) for f in fs]

    def msgs(self, response):
        return [(m.level_tag, str(m)) for m in get_messages(response.wsgi_request)]

    def upload(self, *files):
        return self.c.post("/manage/listings/intake/", {"artwork": list(files)})

    def test_creates_a_design_with_a_listing_per_template(self):
        r = self.upload(png("Deep-Field_north.png"))
        self.assertRedirects(r, "/manage/listings/", fetch_redirect_response=False)
        design = Design.objects.get()
        self.assertEqual(design.title, "Deep Field North")
        self.assertTrue(design.artwork.name.startswith("designs/"))
        listings = Listing.objects.filter(design=design)
        self.assertEqual(listings.count(), 2)
        tee = listings.get(product_type=ProductType.TEE)
        self.assertEqual((tee.status, tee.price, tee.sizes.count()), (Status.DRAFT, Decimal("40"), 2))

    def test_uploading_the_same_file_again_no_longer_errors(self):
        for _ in range(3):
            r = self.upload(png("E0999265-CDAE.png"))
            self.assertEqual(r.status_code, 302)
        self.assertEqual(Design.objects.count(), 3)
        self.assertEqual(len({d.slug for d in Design.objects.all()}), 3)
        self.assertEqual(Listing.objects.count(), 6)
        self.assertTrue(any("share a title" in m for _, m in self.msgs(r)))

    def test_a_batch_makes_one_design_per_file(self):
        r = self.upload(png("a.png"), png("b.png", "blue"), png("c.png", "green"))
        self.assertEqual(Design.objects.count(), 3)
        self.assertIn("Created 3 draft design(s)", self.msgs(r)[0][1])

    def test_non_images_are_skipped_with_a_message_and_the_rest_carry_on(self):
        bad = SimpleUploadedFile("logo.png", b"this is not really a png", content_type="image/png")
        text = SimpleUploadedFile("notes.txt", b"hello", content_type="text/plain")
        r = self.upload(png("ok.png"), bad, text)
        self.assertEqual(Design.objects.count(), 1)
        errors = [m for level, m in self.msgs(r) if level == "error"]
        self.assertTrue(errors and "logo.png" in errors[0] and "notes.txt" in errors[0])
        self.assertEqual(len(self.files_on_disk()), 1)

    def test_a_failure_rolls_back_that_file_completely_and_others_still_work(self):
        real_create = ListingSize.objects.create
        calls = {"n": 0}

        def flaky(*a, **kw):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("boom")
            return real_create(*a, **kw)

        with mock.patch.object(ListingSize.objects, "create", side_effect=flaky),                 self.assertLogs("shop.console_views", level="ERROR"):
            r = self.upload(png("first.png"), png("second.png", "blue"))
        self.assertEqual([d.title for d in Design.objects.all()], ["Second"])   # first left nothing behind
        self.assertEqual(Listing.objects.exclude(design__title="Second").count(), 0)
        self.assertEqual(len(self.files_on_disk()), 1)                           # no orphan file
        errors = [m for level, m in self.msgs(r) if level == "error"]
        self.assertTrue(errors and "first.png" in errors[0])

    def test_no_templates_means_nothing_is_uploaded_and_you_are_pointed_to_templates(self):
        Listing.objects.all().delete()
        ProductTemplate.objects.all().delete()
        r = self.upload(png("art.png"))
        self.assertRedirects(r, "/manage/catalogue/setup/#templates", fetch_redirect_response=False)
        self.assertEqual(Design.objects.count(), 0)
        self.assertEqual(self.files_on_disk(), [])
        self.assertIn("Set up a product template first", self.msgs(r)[0][1])

    def test_only_a_tee_template_still_works(self):
        self.sticker.delete()
        self.upload(png("art.png"))
        self.assertEqual(Listing.objects.count(), 1)

    def test_zero_cost_templates_trigger_a_warning(self):
        self.tee.base_cost = self.tee.shipping_est = Decimal("0")
        self.tee.save()
        r = self.upload(png("art.png"))
        self.assertTrue(any(level == "warning" and "$0" in m for level, m in self.msgs(r)))

    def test_no_file_is_a_friendly_error_not_a_crash(self):
        r = self.c.post("/manage/listings/intake/", {})
        self.assertEqual(r.status_code, 302)
        self.assertIn("No files received", self.msgs(r)[0][1])

    def test_listings_page_explains_when_templates_are_missing(self):
        self.assertNotContains(self.c.get("/manage/listings/"), "No product templates yet")
        Listing.objects.all().delete()
        ProductTemplate.objects.all().delete()
        self.assertContains(self.c.get("/manage/listings/"), "No product templates yet")


@override_settings(STAFF_2FA_REQUIRED=False)
class TemplateDashboardTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user("curator", password="x-12345-yz", is_staff=True)
        self.c = Client()
        self.c.force_login(self.staff)

    def form(self, **over):
        data = {"name": "Standard tee", "product_type": "tee", "base_cost": "11.00", "shipping_est": "5.00",
                "sizes": "S, 18, 28\nM, 20, 29", "print_placement": "front"}
        data.update(over)
        return data

    def test_requires_staff_login(self):
        for path in ("/manage/templates/", "/manage/templates/new/"):
            r = Client().get(path)
            self.assertEqual(r.status_code, 302)
            self.assertIn("/admin/login/", r["Location"])

    def test_empty_state_and_nav_link(self):
        r = self.c.get("/manage/catalogue/setup/")
        self.assertContains(r, "No templates yet")
        self.assertContains(r, 'href="/manage/catalogue/setup/"')     # console nav

    def test_old_templates_url_redirects_to_the_merged_page(self):
        r = self.c.get("/manage/templates/")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r["Location"], "/manage/catalogue/setup/#templates")

    def test_create_saves_costs_and_sizes(self):
        r = self.c.post("/manage/templates/new/", self.form())
        self.assertRedirects(r, "/manage/catalogue/setup/#templates", fetch_redirect_response=False)
        t = ProductTemplate.objects.get()
        self.assertEqual((t.name, t.product_type, t.base_cost, t.shipping_est), ("Standard tee", "tee", Decimal("11.00"), Decimal("5.00")))
        self.assertEqual(t.default_sizes, [{"label": "S", "width_in": 18, "height_in": 28}, {"label": "M", "width_in": 20, "height_in": 29}])
        page = self.c.get("/manage/catalogue/setup/")
        self.assertContains(page, "Standard tee")
        self.assertContains(page, "$40")            # (11 + 5) x 2.5

    def test_dollar_signs_are_accepted_in_money_fields(self):
        self.c.post("/manage/templates/new/", self.form(base_cost="$11", shipping_est="$5"))
        self.assertEqual(ProductTemplate.objects.get().base_cost, Decimal("11"))

    def test_invalid_input_is_rejected_and_the_form_keeps_what_you_typed(self):
        r = self.c.post("/manage/templates/new/", self.form(name="", base_cost="abc", shipping_est="-2", sizes="M, wide"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(ProductTemplate.objects.count(), 0)
        for fragment in ("Give the template a name", "Base cost must be", "Shipping estimate must be", "isn&#x27;t a number"):
            self.assertContains(r, fragment)
        self.assertContains(r, "M, wide")

    def test_duplicate_names_are_rejected_case_insensitively(self):
        self.c.post("/manage/templates/new/", self.form())
        r = self.c.post("/manage/templates/new/", self.form(name="standard TEE"))
        self.assertContains(r, "already has that name")
        self.assertEqual(ProductTemplate.objects.count(), 1)

    def test_edit_updates_and_can_keep_its_own_name(self):
        self.c.post("/manage/templates/new/", self.form())
        t = ProductTemplate.objects.get()
        r = self.c.post(f"/manage/templates/{t.pk}/", self.form(base_cost="12.50"))
        self.assertRedirects(r, "/manage/catalogue/setup/#templates", fetch_redirect_response=False)
        t.refresh_from_db()
        self.assertEqual(t.base_cost, Decimal("12.50"))
        self.assertContains(self.c.get(f"/manage/templates/{t.pk}/"), "S, 18, 28")

    def test_editing_a_template_does_not_touch_existing_listings(self):
        t = ProductTemplate.objects.create(name="Tee", product_type="tee", base_cost=Decimal("11"), shipping_est=Decimal("5"), default_sizes=TEE_SIZES)
        design = Design.objects.create(title="A")
        listing = Listing.objects.create(design=design, template=t, product_type="tee", base_cost=t.base_cost, shipping_est=t.shipping_est)
        self.c.post(f"/manage/templates/{t.pk}/", self.form(name="Tee", base_cost="20"))
        listing.refresh_from_db()
        self.assertEqual(listing.base_cost, Decimal("11"))

    def test_delete_unused_template_but_not_one_in_use(self):
        used = ProductTemplate.objects.create(name="Used", product_type="tee", base_cost=Decimal("1"), default_sizes=TEE_SIZES)
        Listing.objects.create(design=Design.objects.create(title="A"), template=used, product_type="tee")
        free = ProductTemplate.objects.create(name="Free", product_type="sticker", default_sizes=TEE_SIZES)
        self.c.post(f"/manage/templates/{free.pk}/delete/")
        self.assertFalse(ProductTemplate.objects.filter(pk=free.pk).exists())
        r = self.c.post(f"/manage/templates/{used.pk}/delete/")
        self.assertTrue(ProductTemplate.objects.filter(pk=used.pk).exists())
        self.assertTrue(any("used by existing listings" in str(m) for m in get_messages(r.wsgi_request)))

    def test_delete_requires_post(self):
        t = ProductTemplate.objects.create(name="T", product_type="tee", default_sizes=TEE_SIZES)
        self.assertEqual(self.c.get(f"/manage/templates/{t.pk}/delete/").status_code, 405)
        self.assertTrue(ProductTemplate.objects.filter(pk=t.pk).exists())

    def test_warnings_for_zero_cost_and_tee_over_the_ceiling(self):
        ProductTemplate.objects.create(name="Free tee", product_type="tee", default_sizes=TEE_SIZES)
        ProductTemplate.objects.create(name="Fancy tee", product_type="tee", base_cost=Decimal("17"), shipping_est=Decimal("5"), default_sizes=TEE_SIZES)
        page = self.c.get("/manage/catalogue/setup/")
        self.assertContains(page, "Costs are $0")
        self.assertContains(page, "over the $40 tee ceiling")

    def test_missing_product_types_are_called_out(self):
        ProductTemplate.objects.create(name="Tee", product_type="tee", default_sizes=TEE_SIZES)
        self.assertContains(self.c.get("/manage/catalogue/setup/"), "No <strong>Sticker</strong> template yet")

    def test_unknown_template_is_404(self):
        self.assertEqual(self.c.get("/manage/templates/999/").status_code, 404)
