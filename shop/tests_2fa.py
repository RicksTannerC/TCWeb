"""Two-factor gate on /manage/ and /admin/."""

import io
import time

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase, override_settings
from django_otp.oath import TOTP
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice

HTTPS = {"HTTP_X_FORWARDED_PROTO": "https"}


def totp_now(device):
    t = TOTP(device.bin_key, device.step, device.t0, device.digits, device.drift)
    t.time = time.time()
    return f"{t.token():0{device.digits}d}"


class TwoFactorTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_user("curator", password="pw-12345-xyz", is_staff=True, is_superuser=True)
        self.plain = User.objects.create_user("customer", password="pw-12345-xyz")
        self.device = TOTPDevice.objects.create(user=self.staff, name="authenticator", confirmed=True)
        self.backup = StaticDevice.objects.create(user=self.staff, name="backup", confirmed=True)
        StaticToken.objects.create(device=self.backup, token="abcd2345")
        self.c = Client(**HTTPS)

    def login(self, user="curator"):
        self.assertTrue(self.c.login(username=user, password="pw-12345-xyz"))

    # --- the gate --------------------------------------------------------
    def test_anonymous_still_goes_to_normal_login(self):
        r = self.c.get("/manage/")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/admin/login/", r["Location"])

    def test_password_alone_is_not_enough_for_console(self):
        self.login()
        r = self.c.get("/manage/orders/")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r["Location"], "/manage/2fa/?next=/manage/orders/")

    def test_password_alone_is_not_enough_for_django_admin(self):
        self.login()
        r = self.c.get("/admin/")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r["Location"].startswith("/manage/2fa/"))

    def test_console_post_is_blocked_too(self):
        self.login()
        r = self.c.post("/manage/orders/1/approve/")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r["Location"].startswith("/manage/2fa/"))

    def test_htmx_request_gets_hx_redirect(self):
        self.login()
        r = self.c.get("/manage/orders/", HTTP_HX_REQUEST="true")
        self.assertEqual(r.status_code, 401)
        self.assertTrue(r["HX-Redirect"].startswith("/manage/2fa/"))

    def test_public_site_and_webhooks_are_untouched(self):
        self.login()
        for path in ("/", "/shop/", "/cart/", "/contact/", "/robots.txt"):
            self.assertEqual(self.c.get(path).status_code, 200, path)

    def test_non_staff_is_not_sent_to_2fa(self):
        self.login("customer")
        r = self.c.get("/manage/")
        self.assertNotIn("/manage/2fa/", r.get("Location", ""))

    # --- verifying -------------------------------------------------------
    def test_valid_totp_unlocks_console_and_admin(self):
        self.login()
        r = self.c.post("/manage/2fa/", {"token": totp_now(self.device), "next": "/manage/orders/"})
        self.assertRedirects(r, "/manage/orders/", fetch_redirect_response=False)
        self.assertEqual(self.c.get("/manage/").status_code, 200)
        self.assertEqual(self.c.get("/admin/").status_code, 200)

    def test_wrong_code_is_rejected(self):
        self.login()
        r = self.c.post("/manage/2fa/", {"token": "000000"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "didn")
        self.assertEqual(self.c.get("/manage/").status_code, 302)

    def test_backup_code_works_once(self):
        self.login()
        r = self.c.post("/manage/2fa/", {"token": "ABCD 2345"})  # case/space tolerant
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.c.get("/manage/").status_code, 200)
        other = Client(**HTTPS)
        other.login(username="curator", password="pw-12345-xyz")
        r = other.post("/manage/2fa/", {"token": "abcd2345"})
        self.assertEqual(r.status_code, 200)  # already used

    def test_repeated_failures_throttle_even_the_right_code(self):
        self.login()
        for _ in range(5):
            self.c.post("/manage/2fa/", {"token": "000000"})
        r = self.c.post("/manage/2fa/", {"token": totp_now(self.device)})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.c.get("/manage/").status_code, 302)

    def test_open_redirect_is_refused(self):
        self.login()
        r = self.c.post("/manage/2fa/", {"token": totp_now(self.device), "next": "https://evil.example/x"})
        self.assertEqual(r["Location"], "/manage/")

    def test_verification_expires(self):
        self.login()
        self.c.post("/manage/2fa/", {"token": totp_now(self.device)})
        self.assertEqual(self.c.get("/manage/").status_code, 200)
        session = self.c.session
        session["_2fa_verified_at"] = time.time() - 60 * 60 * 13
        session.save()
        self.assertEqual(self.c.get("/manage/").status_code, 302)

    def test_user_without_a_device_is_locked_out_with_instructions(self):
        get_user_model().objects.create_user("newbie", password="pw-12345-xyz", is_staff=True)
        self.login("newbie")
        r = self.c.get("/manage/")
        self.assertEqual(r.status_code, 302)
        page = self.c.get(r["Location"])
        self.assertContains(page, "otp_setup newbie")
        self.assertEqual(self.c.post("/manage/2fa/", {"token": "123456"}).status_code, 200)
        self.assertEqual(self.c.get("/manage/").status_code, 302)

    @override_settings(STAFF_2FA_REQUIRED=False)
    def test_can_be_switched_off_for_local_dev(self):
        self.login()
        self.assertEqual(self.c.get("/manage/").status_code, 200)


class OtpSetupCommandTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("curator", password="x-12345-yz", is_staff=True)

    def run_cmd(self, *args):
        out = io.StringIO()
        call_command("otp_setup", *args, stdout=out)
        return out.getvalue()

    def test_enrolls_and_prints_qr_key_and_codes(self):
        out = self.run_cmd("curator")
        self.assertTrue(TOTPDevice.objects.filter(user=self.user, confirmed=True).exists())
        self.assertEqual(StaticToken.objects.filter(device__user=self.user).count(), 8)
        device = TOTPDevice.objects.get(user=self.user)
        self.assertIn("Two-factor enabled", out)
        self.assertIn("█", out.replace("▀", "█").replace("▄", "█"))  # ascii QR rendered

    def test_refuses_to_overwrite_without_reset(self):
        self.run_cmd("curator")
        with self.assertRaises(CommandError):
            self.run_cmd("curator")

    def test_reset_replaces_devices(self):
        self.run_cmd("curator")
        old = TOTPDevice.objects.get(user=self.user).key
        self.run_cmd("curator", "--reset")
        self.assertEqual(TOTPDevice.objects.filter(user=self.user).count(), 1)
        self.assertNotEqual(TOTPDevice.objects.get(user=self.user).key, old)

    def test_rejects_unknown_and_non_staff_users(self):
        get_user_model().objects.create_user("customer", password="x-12345-yz")
        for name in ("ghost", "customer"):
            with self.assertRaises(CommandError):
                self.run_cmd(name)
