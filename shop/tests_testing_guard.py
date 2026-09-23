"""settings.TESTING: a hard, code-level guarantee that the test suite can
never reach a real third-party API, regardless of what's in the environment.

See config/settings.py (TESTING = "test" in sys.argv[:2]) and the incident
this exists to prevent: TCWEB_ENV_FILE was briefly a permanent environment
variable, so a plain `manage.py test` silently ran with the real
PRINTFUL_API_KEY and made real, read-only catalog calls without being asked.
"""

from django.test import TestCase, override_settings

from . import payments, printful


class TestingFlagIsSetTests(TestCase):
    def test_testing_is_true_under_the_test_runner(self):
        from django.conf import settings
        self.assertTrue(settings.TESTING)


@override_settings(PRINTFUL_API_KEY="a-real-looking-key")
class PrintfulGuardTests(TestCase):
    def test_a_real_key_is_not_enough_while_testing(self):
        self.assertFalse(printful.configured())
        self.assertIsInstance(printful.get_client(), printful.MockPrintful)

    @override_settings(TESTING=False)
    def test_without_the_testing_guard_the_same_key_would_be_used(self):
        # Proves the guard -- not the absence of a key -- is what's holding
        # this closed; TESTING=False is the only thing that changed.
        self.assertTrue(printful.configured())
        self.assertIsInstance(printful.get_client(), printful.RealPrintful)


@override_settings(STRIPE_SECRET_KEY="sk_live_a-real-looking-key")
class StripeGuardTests(TestCase):
    def test_a_real_key_is_not_enough_while_testing(self):
        self.assertFalse(payments.stripe_ready())

    @override_settings(TESTING=False)
    def test_without_the_testing_guard_the_same_key_would_be_used(self):
        self.assertTrue(payments.stripe_ready())
