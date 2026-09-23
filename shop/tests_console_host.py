"""The private console host: console at the root, nothing else served there."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django_otp.plugins.otp_totp.models import TOTPDevice

from .console import VisitLog
from .tests_2fa import totp_now

CONSOLE = "manage.example.test"
PUBLIC = "shop.example.test"
SETTINGS = dict(
    CONSOLE_HOST=CONSOLE,
    ALLOWED_HOSTS=[CONSOLE, PUBLIC, "testserver", "127.0.0.1", "localhost"],
    SITE_BASE_URL="https://shop.example.test",
)


def client(host):
    return Client(HTTP_HOST=host, HTTP_X_FORWARDED_PROTO="https")


@override_settings(**SETTINGS)
class ConsoleHostTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user(
            "curator", password="pw-12345-xyz", is_staff=True, is_superuser=True)
        self.device = TOTPDevice.objects.create(user=self.staff, name="a", confirmed=True)

    def signed_in_console(self):
        c = client(CONSOLE)
        self.assertTrue(c.login(username="curator", password="pw-12345-xyz"))
        c.post("/2fa/", {"token": totp_now(self.device)})
        return c

    # --- layout on the console host --------------------------------------
    def test_root_is_the_console_and_needs_login(self):
        r = client(CONSOLE).get("/")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r["Location"], "/admin/login/?next=/")

    def test_login_page_and_robots_are_served(self):
        c = client(CONSOLE)
        self.assertEqual(c.get("/admin/login/").status_code, 200)
        self.assertContains(c.get("/robots.txt"), "Disallow: /")

    def test_shop_is_not_served_on_the_console_host(self):
        c = client(CONSOLE)
        for path in ("/shop/", "/cart/", "/contact/", "/checkout/", "/pages/about/", "/order/abc/"):
            self.assertEqual(c.get(path).status_code, 404, path)

    def test_old_manage_urls_redirect_to_the_root_layout(self):
        c = client(CONSOLE)
        self.assertEqual(c.get("/manage/")["Location"], "/")
        self.assertEqual(c.get("/manage/orders/?page=2")["Location"], "/orders/?page=2")

    def test_password_alone_is_not_enough_and_2fa_lives_at_root(self):
        c = client(CONSOLE)
        c.login(username="curator", password="pw-12345-xyz")
        self.assertEqual(c.get("/orders/")["Location"], "/2fa/?next=/orders/")
        self.assertTrue(c.get("/admin/")["Location"].startswith("/2fa/"))
        r = c.get("/orders/", HTTP_HX_REQUEST="true")
        self.assertEqual(r.status_code, 401)
        self.assertTrue(r["HX-Redirect"].startswith("/2fa/"))

    def test_verified_staff_use_the_console_without_a_manage_prefix(self):
        c = self.signed_in_console()
        for path in ("/", "/orders/", "/listings/", "/catalogue/setup/",
                     "/money/", "/content/", "/admin/"):
            self.assertEqual(c.get(path).status_code, 200, path)

    def test_old_merged_page_urls_still_redirect_on_the_console_host(self):
        c = self.signed_in_console()
        for path, target in (
            ("/collections/", "/catalogue/setup/#collections"),
            ("/templates/", "/catalogue/setup/#templates"),
            ("/pricing/", "/money/#pricing"),
            ("/books/", "/money/#books"),
            ("/messages/", "/content/#messages"),
            ("/pages/", "/content/#pages"),
        ):
            r = c.get(path)
            self.assertEqual(r.status_code, 302, path)
            self.assertEqual(r["Location"], target, path)

    def test_console_links_have_no_manage_prefix_and_shop_link_is_public(self):
        html = self.signed_in_console().get("/").content.decode()
        self.assertNotIn('href="/manage', html)
        self.assertIn('href="/orders/"', html)
        self.assertIn('href="/listings/"', html)
        self.assertIn('href="https://shop.example.test/shop/"', html)

    def test_verify_redirects_to_next_and_defaults_to_the_dashboard(self):
        c = client(CONSOLE)
        c.login(username="curator", password="pw-12345-xyz")
        r = c.post("/2fa/", {"token": totp_now(self.device), "next": "/orders/"})
        self.assertEqual(r["Location"], "/orders/")
        # django-otp refuses to accept the same code twice; allow it for this second sign-in.
        self.device.refresh_from_db()
        self.device.last_t = -1
        self.device.save()
        c2 = client(CONSOLE)
        c2.login(username="curator", password="pw-12345-xyz")
        r = c2.post("/2fa/", {"token": totp_now(self.device), "next": "https://evil.example/"})
        self.assertEqual(r["Location"], "/")

    def test_console_page_views_are_not_counted_as_shop_visits(self):
        c = self.signed_in_console()
        before = VisitLog.objects.count()
        c.get("/")
        c.get("/orders/")
        self.assertEqual(VisitLog.objects.count(), before)

    def test_non_staff_are_sent_to_the_public_shop(self):
        get_user_model().objects.create_user("customer", password="pw-12345-xyz")
        c = client(CONSOLE)
        c.login(username="customer", password="pw-12345-xyz")
        self.assertEqual(c.get("/2fa/")["Location"], "https://shop.example.test")

    # --- other hosts -------------------------------------------------------
    def test_public_host_no_longer_serves_console_or_admin(self):
        c = client(PUBLIC)
        for path in ("/manage/", "/manage/orders/", "/admin/", "/admin/login/"):
            self.assertEqual(c.get(path).status_code, 404, path)

    def test_public_host_still_serves_the_shop(self):
        c = client(PUBLIC)
        for path in ("/", "/shop/", "/cart/", "/contact/", "/robots.txt"):
            self.assertEqual(c.get(path).status_code, 200, path)

    def test_local_hosts_keep_the_old_layout(self):
        for host in ("127.0.0.1:8000", "localhost", "testserver"):
            r = client(host).get("/manage/")
            self.assertEqual(r.status_code, 302, host)
            self.assertIn("/admin/login/", r["Location"])

    def test_public_names_reverse_the_same_in_either_layout(self):
        for conf in ("config.urls", "config.urls_console"):
            self.assertEqual(reverse("shop:order_track", args=["tok"], urlconf=conf), "/order/tok/")
            self.assertEqual(reverse("shop:index", urlconf=conf), "/shop/")


class DefaultLayoutUnchangedTests(TestCase):
    """With CONSOLE_HOST unset (the default) nothing about routing changes."""

    def test_single_host_layout(self):
        c = client("testserver")
        self.assertEqual(c.get("/shop/").status_code, 200)
        self.assertEqual(c.get("/manage/")["Location"].split("?")[0], "/admin/login/")
        self.assertEqual(c.get("/admin/login/").status_code, 200)
        self.assertEqual(c.get("/orders/").status_code, 404)  # console is only under /manage/
        self.assertEqual(reverse("shop:manage_dashboard"), "/manage/")
        self.assertEqual(reverse("shop:manage_2fa"), "/manage/2fa/")
