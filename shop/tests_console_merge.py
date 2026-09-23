"""The merged console pages (Catalogue setup, Money, Content) and the new
dropdown nav, per the design-review request to combine related pages and
collapse the top nav."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import Client, TestCase, override_settings

from .console import ContactMessage, OverheadEntry, Page
from .models import Collection, Design, Listing, ProductTemplate, ProductType, Status


@override_settings(STAFF_2FA_REQUIRED=False)
class ConsoleBase(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user("curator", password="x-12345-yz", is_staff=True)
        self.c = Client()
        self.c.force_login(self.staff)


class CatalogueSetupPageTests(ConsoleBase):
    def test_shows_templates_and_collections_on_one_page(self):
        ProductTemplate.objects.create(name="Tee", product_type="tee", default_sizes=[{"label": "M"}])
        Collection.objects.create(name="Deep Field")
        r = self.c.get("/manage/catalogue/setup/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Tee")
        self.assertContains(r, "Deep Field")
        self.assertContains(r, 'id="templates"')
        self.assertContains(r, 'id="collections"')

    def test_collection_create_lands_back_on_the_merged_page(self):
        r = self.c.post("/manage/collections/create/", {"name": "New World"})
        self.assertRedirects(r, "/manage/catalogue/setup/#collections", fetch_redirect_response=False)
        self.assertTrue(Collection.objects.filter(name="New World").exists())

    def test_collection_toggle_lands_back_on_the_merged_page(self):
        col = Collection.objects.create(name="Deep Field")
        r = self.c.post(f"/manage/collections/{col.pk}/toggle/")
        self.assertRedirects(r, "/manage/catalogue/setup/#collections", fetch_redirect_response=False)
        col.refresh_from_db()
        self.assertEqual(col.status, Status.LIVE)


class MoneyPageTests(ConsoleBase):
    def test_shows_pricing_and_books_on_one_page(self):
        tpl = ProductTemplate.objects.create(name="Tee", product_type="tee",
                                              base_cost=Decimal("11"), shipping_est=Decimal("5"))
        Listing.objects.create(design=Design.objects.create(title="Pillars"), template=tpl,
                                product_type="tee", status=Status.LIVE, price=Decimal("40"))
        r = self.c.get("/manage/money/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Pillars")
        self.assertContains(r, "Pricing workspace")
        self.assertContains(r, "Books")
        self.assertContains(r, 'id="pricing"')
        self.assertContains(r, 'id="books"')

    def test_pricing_update_lands_back_on_the_merged_page(self):
        tpl = ProductTemplate.objects.create(name="Tee", product_type="tee",
                                              base_cost=Decimal("11"), shipping_est=Decimal("5"))
        listing = Listing.objects.create(design=Design.objects.create(title="Pillars"), template=tpl,
                                          product_type="tee", status=Status.LIVE, price=Decimal("40"))
        r = self.c.post("/manage/pricing/update/", {f"price_{listing.pk}": "45.00"})
        self.assertRedirects(r, "/manage/money/#pricing", fetch_redirect_response=False)
        listing.refresh_from_db()
        self.assertEqual(listing.price, Decimal("45.00"))

    def test_overhead_add_and_delete_land_back_on_the_merged_page(self):
        r = self.c.post("/manage/books/overhead/add/", {
            "label": "Ink", "amount": "12.50", "category": OverheadEntry.Category.OTHER})
        self.assertRedirects(r, "/manage/money/#books", fetch_redirect_response=False)
        entry = OverheadEntry.objects.get()
        r = self.c.post(f"/manage/books/overhead/{entry.pk}/delete/")
        self.assertRedirects(r, "/manage/money/#books", fetch_redirect_response=False)
        self.assertFalse(OverheadEntry.objects.exists())


class ContentPageTests(ConsoleBase):
    def test_shows_messages_and_pages_on_one_page(self):
        ContactMessage.objects.create(name="Al", email="al@example.com", body="Hi")
        Page.objects.create(title="About", body="...")
        r = self.c.get("/manage/content/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Al")
        self.assertContains(r, "About")
        self.assertContains(r, 'id="messages"')
        self.assertContains(r, 'id="pages"')

    def test_show_query_param_still_filters_messages_on_the_merged_page(self):
        ContactMessage.objects.create(name="Open one", email="a@example.com", body="Hi", handled=False)
        ContactMessage.objects.create(name="Handled one", email="b@example.com", body="Hi", handled=True)
        open_page = self.c.get("/manage/content/?show=open")
        self.assertContains(open_page, "Open one")
        self.assertNotContains(open_page, "Handled one")
        all_page = self.c.get("/manage/content/?show=all")
        self.assertContains(all_page, "Open one")
        self.assertContains(all_page, "Handled one")

    def test_message_toggle_returns_to_wherever_the_form_was_on(self):
        m = ContactMessage.objects.create(name="Al", email="a@example.com", body="Hi")
        r = self.c.post(f"/manage/messages/{m.pk}/toggle/", {"next": "/manage/content/?show=all"})
        self.assertRedirects(r, "/manage/content/?show=all", fetch_redirect_response=False)
        m.refresh_from_db()
        self.assertTrue(m.handled)

    def test_old_inbox_url_redirects_preserving_the_query_string(self):
        r = self.c.get("/manage/messages/?show=all")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r["Location"], "/manage/content/?show=all#messages")


class NavTests(ConsoleBase):
    def test_top_level_nav_is_the_five_agreed_destinations(self):
        html = self.c.get("/manage/").content.decode()
        for label, href in [
            ("Dashboard", "/manage/"), ("Orders", "/manage/orders/"),
            ("Money", "/manage/money/"), ("Content", "/manage/content/"),
        ]:
            self.assertIn(f'href="{href}"', html)
        self.assertIn("Catalogue", html)
        self.assertIn(f'href="/manage/listings/"', html)
        self.assertIn(f'href="/manage/catalogue/setup/"', html)
        # the old flat links are gone from the nav (still exist as URLs, just not linked from here)
        for gone in ("Collections</a>", "Pricing</a>", ">Templates<", ">Books<", ">Messages<", ">Pages<"):
            self.assertNotIn(gone, html)

    def test_catalogue_group_shows_active_on_its_sub_pages(self):
        for path in ("/manage/listings/", "/manage/catalogue/setup/"):
            html = self.c.get(path).content.decode()
            self.assertIn("has-active", html)

    def test_money_and_content_links_show_current_page(self):
        html = self.c.get("/manage/money/").content.decode()
        self.assertIn('href="/manage/money/" aria-current="page"', html)
        html = self.c.get("/manage/content/").content.decode()
        self.assertIn('href="/manage/content/" aria-current="page"', html)
