"""Printful's status webhook: unauthenticated by Printful's design, so the URL is the secret."""

import json
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import Client, TestCase, override_settings

from . import printful
from .models import Design, Listing, ProductTemplate
from .orders import Fulfillment, Order, OrderStatus


def shipped_order():
    tpl = ProductTemplate.objects.create(name="Tee", product_type="tee")
    Listing.objects.create(design=Design.objects.create(title="W"), template=tpl, product_type="tee")
    order = Order.objects.create(status=OrderStatus.SUBMITTED, email="a@b.c")
    ful = Fulfillment.objects.create(order=order, supplier="printful", status="submitted", partner_order_id="555")
    return order, ful


EVENT = {"type": "package_shipped", "data": {
    "order": {"id": 555, "external_id": "TTS-00001-1"},
    "shipment": {"tracking_number": "1Z999", "tracking_url": "https://t.example/1Z999", "carrier": "UPS"}}}


class WebhookTokenTests(TestCase):
    def post(self, token, body=EVENT):
        return Client().post(f"/webhooks/printful/{token}/", data=json.dumps(body), content_type="application/json")

    def test_the_right_token_applies_the_event(self):
        order, ful = shipped_order()
        r = self.post(printful.webhook_token())
        self.assertEqual(r.status_code, 200)
        ful.refresh_from_db()
        self.assertEqual((ful.status, ful.tracking_number, ful.carrier), ("shipped", "1Z999", "UPS"))

    def test_a_wrong_token_is_a_404_and_changes_nothing(self):
        order, ful = shipped_order()
        good = printful.webhook_token()
        wrong = "nope", "x" * 40, good[:-1] + ("0" if good[-1] != "0" else "1")
        for bad in wrong:
            self.assertEqual(self.post(bad).status_code, 404, bad)
        ful.refresh_from_db()
        self.assertEqual(ful.status, "submitted")

    def test_the_old_open_url_no_longer_exists(self):
        order, ful = shipped_order()
        r = Client().post("/webhooks/printful/", data=json.dumps(EVENT), content_type="application/json")
        self.assertEqual(r.status_code, 404)
        ful.refresh_from_db()
        self.assertEqual(ful.status, "submitted")

    def test_get_is_not_allowed_even_with_the_token(self):
        self.assertEqual(Client().get(f"/webhooks/printful/{printful.webhook_token()}/").status_code, 405)

    def test_garbage_json_with_the_right_token_is_a_400(self):
        r = Client().post(f"/webhooks/printful/{printful.webhook_token()}/", data="{nope",
                          content_type="application/json")
        self.assertEqual(r.status_code, 400)

    def test_no_cookie_or_csrf_needed(self):
        c = Client(enforce_csrf_checks=True)
        r = c.post(f"/webhooks/printful/{printful.webhook_token()}/", data=json.dumps({"type": ""}),
                   content_type="application/json")
        self.assertEqual(r.status_code, 200)


class TokenDerivationTests(TestCase):
    def test_it_is_stable_long_and_not_the_secret_key(self):
        from django.conf import settings

        t = printful.webhook_token()
        self.assertEqual(t, printful.webhook_token())
        self.assertEqual(len(t), 40)
        self.assertNotIn(settings.SECRET_KEY, t)
        with override_settings(SECRET_KEY="a-different-secret-key-for-this-test"):
            self.assertNotEqual(printful.webhook_token(), t)

    def test_the_url_is_absolute_on_the_public_site(self):
        with override_settings(SITE_BASE_URL="https://shop.test"):
            self.assertEqual(printful.webhook_url(),
                             f"https://shop.test/webhooks/printful/{printful.webhook_token()}/")


class CommandTests(TestCase):
    def run_cmd(self, *args):
        out = StringIO()
        call_command("printful_webhook", *args, stdout=out)
        return out.getvalue()

    def test_default_only_prints_the_url_and_contacts_nobody(self):
        with mock.patch.object(printful, "get_client", side_effect=AssertionError("must not be called")):
            self.assertIn(printful.webhook_url(), self.run_cmd())

    def test_register_sends_the_url_and_the_handled_event_types(self):
        client = mock.MagicMock(is_mock=False)
        client._get.return_value = {"url": printful.webhook_url(), "types": printful.WEBHOOK_TYPES}
        with mock.patch.object(printful, "get_client", return_value=client):
            out = self.run_cmd("--register")
        client.set_webhook.assert_called_once_with(printful.webhook_url(), printful.WEBHOOK_TYPES)
        self.assertIn("Matches this site: yes", out)

    def test_status_is_read_only_and_reports_a_mismatch(self):
        client = mock.MagicMock(is_mock=False)
        client._get.return_value = {"url": "https://old.example/hook", "types": []}
        with mock.patch.object(printful, "get_client", return_value=client):
            out = self.run_cmd("--status")
        client.set_webhook.assert_not_called()
        self.assertIn("Matches this site: NO", out)

    def test_nothing_is_contacted_in_mock_mode(self):
        self.assertIn("mock mode", self.run_cmd("--register"))

    def test_every_registered_type_is_one_the_site_handles(self):
        handled = {"package_shipped", "package_returned", "order_failed", "order_canceled", "order_put_hold",
                   "order_updated"}
        self.assertEqual(set(printful.WEBHOOK_TYPES), handled)
