"""www.<shop> redirects to the bare domain, and can never be turned into an open redirect."""

from django.test import Client, TestCase, override_settings


@override_settings(ALLOWED_HOSTS=["shop.test", "manage.shop.test", "localhost", "testserver"],
                   CONSOLE_HOST="manage.shop.test")
class WwwRedirectTests(TestCase):
    def get(self, host, path="/", secure=True, **kw):
        return Client().get(path, HTTP_HOST=host, secure=secure, **kw)

    def test_www_goes_to_the_bare_domain_permanently(self):
        r = self.get("www.shop.test", "/shirts/jack-o/?utm_source=ig")
        self.assertEqual(r.status_code, 301)
        self.assertEqual(r["Location"], "https://shop.test/shirts/jack-o/?utm_source=ig")

    def test_scheme_follows_the_request(self):
        self.assertEqual(self.get("www.shop.test", secure=False)["Location"], "http://shop.test/")

    def test_it_works_even_though_www_is_not_in_allowed_hosts(self):
        # (it isn't: the redirect has to happen before host validation would reject it)
        r = self.get("www.shop.test")
        self.assertEqual(r.status_code, 301)

    def test_case_trailing_dot_and_port_are_tolerated(self):
        self.assertEqual(self.get("WWW.Shop.Test.:443")["Location"], "https://shop.test/")

    def test_the_bare_domain_is_not_redirected(self):
        self.assertEqual(self.get("shop.test").status_code, 200)

    def test_a_www_host_for_a_site_we_do_not_serve_is_not_redirected(self):
        r = self.get("www.other.test")
        self.assertNotEqual(r.status_code, 301)
        self.assertNotIn("Location", r)

    def test_the_private_console_host_is_never_redirected(self):
        r = self.get("www.manage.shop.test", "/")
        self.assertNotEqual(r.status_code, 301)

    def test_the_host_header_cannot_choose_the_destination(self):
        for host in ("www.shop.test@evil.test", "www.evil.test", "www.shop.test.evil.test", "www."):
            r = self.get(host)
            self.assertNotEqual(r.status_code, 301, host)
            self.assertNotIn("evil", r.get("Location", ""), host)

    def test_a_path_that_looks_like_another_host_stays_on_our_domain(self):
        r = self.get("www.shop.test", "//evil.test/x")
        self.assertEqual(r.status_code, 301)
        self.assertTrue(r["Location"].startswith("https://shop.test/"), r["Location"])

    def test_non_get_requests_keep_their_method(self):
        r = Client().post("/cart/add/1/", HTTP_HOST="www.shop.test", secure=True)
        self.assertEqual(r.status_code, 308)
        self.assertEqual(r["Location"], "https://shop.test/cart/add/1/")
