"""Brute-force throttling on staff sign-in: password step, second-factor step, IPs."""

import io
import logging
import time
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, RequestFactory, TestCase, override_settings
from django.utils import timezone
from django_otp.oath import TOTP
from django_otp.plugins.otp_totp.models import TOTPDevice

from . import login_throttle
from .console import FailedLogin

HTTPS = {"HTTP_X_FORWARDED_PROTO": "https"}
PASSWORD = "pw-12345-xyz"
LOCKED = "Too many sign-in attempts"


def totp_now(device):
    t = TOTP(device.bin_key, device.step, device.t0, device.digits, device.drift)
    t.time = time.time()
    return f"{t.token():0{device.digits}d}"


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])  # many logins
class ThrottleTestCase(TestCase):
    """Common setup; the clock is patched so a test can move time without sleeping."""

    def setUp(self):
        log = logging.getLogger("shop.login_throttle")  # keep lock warnings out of the test output
        self.addCleanup(log.setLevel, log.level)
        log.setLevel(logging.ERROR)
        User = get_user_model()
        self.staff = User.objects.create_user("curator", password=PASSWORD, is_staff=True, is_superuser=True)
        self.device = TOTPDevice.objects.create(user=self.staff, name="authenticator", confirmed=True)
        self.now = timezone.now()
        patcher = mock.patch("django.utils.timezone.now", side_effect=lambda: self.now)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.c = Client(**HTTPS)

    def advance(self, **delta):
        self.now += timedelta(**delta)

    def attempt(self, username="curator", password=PASSWORD, client=None, **extra):
        return (client or self.c).post("/admin/login/", {"username": username, "password": password}, **extra)

    def fail(self, times, username="curator", **extra):
        for _ in range(times):
            self.attempt(username, "wrong-password", **extra)

    def errors(self, response):
        return [str(e) for e in response.context["form"].non_field_errors()]

    def assertSignedIn(self, client=None):
        self.assertIn("_auth_user_id", (client or self.c).session)

    def assertNotSignedIn(self, client=None):
        self.assertNotIn("_auth_user_id", (client or self.c).session)


class PasswordStepTests(ThrottleTestCase):
    def test_lock_engages_at_the_threshold(self):
        self.fail(4)
        r = self.attempt("curator", "wrong-password")  # the 5th failure
        self.assertNotContains(r, LOCKED)
        r = self.attempt("curator", "wrong-password")
        self.assertContains(r, LOCKED)
        self.assertContains(r, "Try again in 15 minutes.")

    def test_locked_user_is_rejected_even_with_the_right_password(self):
        self.fail(5)
        with mock.patch("django.contrib.auth.forms.authenticate") as auth:
            r = self.attempt()
            auth.assert_not_called()  # the password was never evaluated
        self.assertContains(r, LOCKED)
        self.assertNotSignedIn()

    def test_other_usernames_are_not_locked_by_one_username(self):
        self.fail(5)
        User = get_user_model()
        User.objects.create_user("someone", password=PASSWORD, is_staff=True)
        r = self.attempt("someone")
        self.assertEqual(r.status_code, 302)

    def test_lock_ends_one_window_after_the_most_recent_failure(self):
        self.fail(4)
        self.advance(minutes=10)
        self.attempt("curator", "wrong-password")  # most recent failure, at t+10
        self.advance(minutes=10)  # t+20: more than 15 minutes after the first failures
        self.assertContains(self.attempt(), LOCKED)
        self.advance(minutes=4)  # t+24: still inside the 15 minutes after t+10
        self.assertContains(self.attempt(), LOCKED)
        self.advance(minutes=2)  # t+26
        r = self.attempt()
        self.assertEqual(r.status_code, 302)
        self.assertSignedIn()

    def test_attempts_during_a_lock_do_not_extend_it(self):
        self.fail(5)
        for _ in range(3):
            self.advance(minutes=4)
            self.assertContains(self.attempt(), LOCKED)  # t+4, t+8, t+12
        self.advance(minutes=4)  # t+16: 15 minutes after the last real failure
        self.assertEqual(self.attempt().status_code, 302)

    def test_the_message_counts_down(self):
        self.fail(5)
        self.advance(minutes=10)
        self.assertContains(self.attempt(), "Try again in 5 minutes.")
        self.advance(minutes=4, seconds=30)
        self.assertContains(self.attempt(), "Try again in 1 minute.")

    def test_a_success_clears_the_counter(self):
        self.fail(4)
        self.assertEqual(self.attempt().status_code, 302)
        self.assertFalse(FailedLogin.objects.filter(username="curator").exists())
        other = Client(**HTTPS)
        self.fail(4, client=other)
        self.assertEqual(self.attempt(client=other).status_code, 302)  # 4 failures again: still not locked

    def test_per_ip_limit_applies_across_usernames(self):
        for i in range(15):
            self.attempt(f"guess{i}", "wrong-password", HTTP_CF_CONNECTING_IP="203.0.113.7")
        # Same IP: even the real owner with the right password is turned away.
        r = self.attempt(HTTP_CF_CONNECTING_IP="203.0.113.7")
        self.assertContains(r, LOCKED)
        # A different visitor is unaffected.
        r = self.attempt(client=Client(**HTTPS), HTTP_CF_CONNECTING_IP="203.0.113.99")
        self.assertEqual(r.status_code, 302)

    def test_14_failures_from_one_ip_is_not_a_lock(self):
        for i in range(14):
            self.attempt(f"guess{i}", "wrong-password", HTTP_CF_CONNECTING_IP="203.0.113.7")
        self.assertEqual(self.attempt(HTTP_CF_CONNECTING_IP="203.0.113.7").status_code, 302)

    def test_a_spoofed_header_cannot_dodge_the_ip_limit(self):
        # Arrives from a non-loopback address: CF-Connecting-IP is ignored.
        for i in range(15):
            self.attempt(
                f"guess{i}", "wrong-password",
                REMOTE_ADDR="198.51.100.9", HTTP_CF_CONNECTING_IP=f"203.0.113.{i}",
            )
        r = self.attempt(REMOTE_ADDR="198.51.100.9", HTTP_CF_CONNECTING_IP="203.0.113.200")
        self.assertContains(r, LOCKED)
        self.assertEqual(
            set(FailedLogin.objects.values_list("ip", flat=True)), {"198.51.100.9"}
        )

    def test_unknown_usernames_are_throttled_like_real_ones(self):
        for attempt_no in range(1, 8):
            ghost = self.attempt("ghost", "wrong-password")
            real = self.attempt("curator", "wrong-password", client=Client(**HTTPS))
            self.assertEqual(ghost.status_code, real.status_code)
            self.assertEqual(self.errors(ghost), self.errors(real), attempt_no)
        self.assertContains(self.attempt("ghost", "x"), LOCKED)
        self.assertContains(self.attempt("curator", "x", client=Client(**HTTPS)), LOCKED)

    def test_username_case_does_not_dodge_the_counter(self):
        for name in ("curator", "Curator", "CURATOR", "curator ", "cUrAtOr"):
            self.attempt(name, "wrong-password")
        self.assertContains(self.attempt(), LOCKED)

    def test_can_be_switched_off(self):
        with override_settings(LOGIN_THROTTLE_ENABLED=False):
            self.fail(30)
            self.assertEqual(self.attempt().status_code, 302)
            self.assertEqual(FailedLogin.objects.count(), 0)

    def test_thresholds_are_settings(self):
        with override_settings(LOGIN_THROTTLE_USER_FAILURES=2):
            self.fail(2)
            self.assertContains(self.attempt(), LOCKED)
        self.advance(minutes=1)
        with override_settings(LOGIN_THROTTLE_USER_FAILURES=2, LOGIN_THROTTLE_WINDOW_SECONDS=30):
            self.assertEqual(self.attempt().status_code, 302)  # 1 minute > the 30 s window

    def test_lock_logs_a_warning_without_the_password(self):
        with self.assertLogs("shop.login_throttle", "WARNING") as logs:
            self.fail(5, HTTP_CF_CONNECTING_IP="203.0.113.7")
        text = "\n".join(logs.output)
        self.assertIn("'curator'", text)
        self.assertIn("203.0.113.7", text)
        self.assertNotIn("wrong-password", text)

    def test_logging_in_without_failures_records_nothing(self):
        # force_login (used all over the suite) and a clean sign-in leave no rows.
        for _ in range(20):
            Client(**HTTPS).force_login(self.staff)
        self.assertEqual(self.attempt().status_code, 302)
        self.assertEqual(FailedLogin.objects.count(), 0)


class ClientIpTests(TestCase):
    def ip(self, remote, cf=None):
        extra = {"REMOTE_ADDR": remote}
        if cf is not None:
            extra["HTTP_CF_CONNECTING_IP"] = cf
        return login_throttle.client_ip(RequestFactory().get("/", **extra))

    def test_header_is_used_only_when_remote_addr_is_loopback(self):
        self.assertEqual(self.ip("127.0.0.1", "203.0.113.7"), "203.0.113.7")
        self.assertEqual(self.ip("::1", "2001:db8::5"), "2001:db8::5")
        self.assertEqual(self.ip("::ffff:127.0.0.1", "203.0.113.7"), "203.0.113.7")
        self.assertEqual(self.ip("198.51.100.9", "203.0.113.7"), "198.51.100.9")
        self.assertEqual(self.ip("10.0.0.5", "203.0.113.7"), "10.0.0.5")

    def test_falls_back_to_remote_addr(self):
        self.assertEqual(self.ip("127.0.0.1"), "127.0.0.1")
        self.assertEqual(self.ip("127.0.0.1", ""), "127.0.0.1")
        self.assertEqual(self.ip("127.0.0.1", "not-an-ip"), "127.0.0.1")
        self.assertEqual(self.ip("198.51.100.9"), "198.51.100.9")


class SecondFactorStepTests(ThrottleTestCase):
    def sign_in(self, client=None):
        client = client or self.c
        self.assertEqual(self.attempt(client=client).status_code, 302)
        return client

    def wrong_codes(self, times, client=None):
        for _ in range(times):
            (client or self.c).post("/manage/2fa/", {"token": "000000"})

    def test_wrong_codes_lock_and_the_right_code_is_then_refused(self):
        self.sign_in()
        self.wrong_codes(5)
        self.assertEqual(
            FailedLogin.objects.filter(username="curator", kind=FailedLogin.Kind.OTP).count(), 5
        )
        r = self.c.post("/manage/2fa/", {"token": totp_now(self.device)})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, LOCKED)
        self.assertEqual(self.c.get("/manage/").status_code, 302)

    def test_the_lock_ends_and_the_code_works_again(self):
        self.sign_in()
        self.wrong_codes(5)
        self.advance(minutes=16)
        r = self.c.post("/manage/2fa/", {"token": totp_now(self.device)})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.c.get("/manage/").status_code, 200)

    def test_an_otp_lock_also_blocks_the_password_step(self):
        self.sign_in()
        self.wrong_codes(5)
        r = self.attempt(client=Client(**HTTPS))
        self.assertContains(r, LOCKED)

    def test_a_right_password_does_not_reset_the_code_failures(self):
        self.sign_in()
        self.wrong_codes(4)
        second = self.sign_in(Client(**HTTPS))  # password is still accepted: 4 < 5
        self.wrong_codes(1, second)
        self.assertContains(second.post("/manage/2fa/", {"token": totp_now(self.device)}), LOCKED)
        self.assertContains(self.attempt(client=Client(**HTTPS)), LOCKED)

    def test_a_right_code_clears_the_counter(self):
        self.sign_in()
        self.wrong_codes(3)
        self.advance(minutes=1)  # django-otp's own per-device delay, not ours
        r = self.c.post("/manage/2fa/", {"token": totp_now(self.device)})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(FailedLogin.objects.count(), 0)

    def test_failures_mix_with_password_failures_per_username(self):
        self.fail(3)
        self.sign_in()  # clears the password failures
        self.fail(2)
        self.wrong_codes(3)  # 2 password + 3 code failures = 5
        self.assertContains(self.attempt(client=Client(**HTTPS)), LOCKED)


class HousekeepingTests(ThrottleTestCase):
    def test_old_rows_are_pruned_when_a_failure_is_recorded(self):
        old = FailedLogin.objects.create(username="old", ip="1.1.1.1", created_at=self.now - timedelta(days=2))
        recent = FailedLogin.objects.create(username="recent", ip="1.1.1.1", created_at=self.now - timedelta(hours=23))
        self.fail(1)
        self.assertFalse(FailedLogin.objects.filter(pk=old.pk).exists())
        self.assertTrue(FailedLogin.objects.filter(pk=recent.pk).exists())

    def test_username_is_stored_lowercased_and_truncated(self):
        self.attempt("MiXeD" + "x" * 300, "wrong-password")
        row = FailedLogin.objects.get()
        self.assertEqual(len(row.username), 150)
        self.assertTrue(row.username.startswith("mixedxxx"))
        self.assertEqual(row.kind, FailedLogin.Kind.PASSWORD)

    def test_rows_survive_without_any_in_memory_state(self):
        # Lockouts are read from the database on each attempt, so a restart
        # (a fresh process) sees exactly the same lock.
        self.fail(5)
        self.assertEqual(FailedLogin.objects.filter(username="curator").count(), 5)
        self.assertContains(self.attempt(client=Client(**HTTPS)), LOCKED)


class ClearLockoutsCommandTests(ThrottleTestCase):
    def run_cmd(self, *args):
        out = io.StringIO()
        call_command("clear_login_lockouts", *args, stdout=out)
        return out.getvalue()

    def test_clears_everything(self):
        self.fail(5)
        self.assertContains(self.attempt(), LOCKED)
        out = self.run_cmd()
        self.assertIn("5", out)
        self.assertEqual(FailedLogin.objects.count(), 0)
        self.assertEqual(self.attempt().status_code, 302)

    def test_clears_one_username(self):
        self.fail(5)
        self.fail(2, username="ghost")
        self.run_cmd("--username", "Curator")
        self.assertFalse(FailedLogin.objects.filter(username="curator").exists())
        self.assertEqual(FailedLogin.objects.filter(username="ghost").count(), 2)
        self.assertEqual(self.attempt().status_code, 302)

    def test_clears_an_ip_lock_without_username(self):
        for i in range(15):
            self.attempt(f"guess{i}", "wrong-password", HTTP_CF_CONNECTING_IP="203.0.113.7")
        self.assertContains(self.attempt(HTTP_CF_CONNECTING_IP="203.0.113.7"), LOCKED)
        self.run_cmd()
        self.assertEqual(self.attempt(HTTP_CF_CONNECTING_IP="203.0.113.7").status_code, 302)
