"""The contract every `PaymentGateway` must keep, run against the in-memory gateway and Stripe's adapter (with
Stripe's SDK calls replaced by local stand-ins and webhooks signed locally). A new provider is ready to plug in
when it passes this class too. Nothing here reaches Stripe or needs a real key."""

import contextlib
import hashlib
import hmac
import json
import time
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

import stripe
from django.test import SimpleTestCase

from tshirtbrand.adapters.payments.memory.gateway import SECRET as MEMORY_SECRET
from tshirtbrand.adapters.payments.memory.gateway import MemoryGateway
from tshirtbrand.adapters.payments.stripe.gateway import StripeGateway
from tshirtbrand.core.payments.api import (
    SESSION_ID_TOKEN, STANDARD_SHIPPING, CheckoutLine, CheckoutRequest, CheckoutSession, PaymentError,
    PaymentEvent, PaymentEventKind, RefundResult,
)

WEBHOOK_SECRET = "whsec_test_local_only"
ADDRESS = {"line1": "1 Main St", "city": "Afton", "state": "WY", "postal_code": "83110", "country": "US"}


def sample_request(**over):
    values = dict(
        order_ref="42",
        lines=(CheckoutLine("Pillars", "Tee, Black, M", 2, Decimal("40.00")),),
        email="buyer@example.com",
        success_url=f"https://shop.test/checkout/success/?ref={SESSION_ID_TOKEN}",
        cancel_url="https://shop.test/cart/",
    )
    values.update(over)
    return CheckoutRequest(**values)


class GatewayContract:
    """Mixin: subclasses supply the gateway and the ways to feed it a webhook."""

    def make_gateway(self):
        raise NotImplementedError

    def paid_webhook(self, order_ref):
        """(payload, signature) for a genuine payment of 80.00 (tax 0, shipping 0) for `order_ref`."""
        raise NotImplementedError

    def other_webhook(self):
        """(payload, signature) for a genuine event the shop has no use for."""
        raise NotImplementedError

    def tampered_webhook(self):
        """(payload, signature) that must not be trusted."""
        raise NotImplementedError

    def provider_down(self):
        """Context manager: while active, the provider refuses create_checkout and refund calls."""
        raise NotImplementedError

    def setUp(self):
        self.gw = self.make_gateway()

    # ---- checkout

    def test_checkout_returns_a_session_with_an_id_and_a_url(self):
        session = self.gw.create_checkout(sample_request())
        self.assertIsInstance(session, CheckoutSession)
        self.assertTrue(session.id)
        self.assertTrue(session.url.startswith("http"))

    def test_the_return_token_never_leaks_into_the_url(self):
        self.assertNotIn(SESSION_ID_TOKEN, self.gw.create_checkout(sample_request()).url)

    def test_a_provider_failure_is_a_payment_error(self):
        with self.provider_down(), self.assertRaises(PaymentError):
            self.gw.create_checkout(sample_request())

    # ---- events

    def test_a_paid_webhook_becomes_a_payment_event(self):
        event = self.gw.parse_event(*self.paid_webhook("42"))
        self.assertIsInstance(event, PaymentEvent)
        self.assertEqual(event.kind, PaymentEventKind.PAID)
        self.assertEqual((event.order_ref, event.email, event.name), ("42", "buyer@example.com", "Ada Buyer"))
        self.assertEqual(event.address["postal_code"], "83110")
        self.assertEqual((event.total, event.tax, event.shipping), (Decimal("80"), Decimal("0"), Decimal("0")))
        self.assertEqual(event.items_total, Decimal("80"))
        self.assertTrue(event.session_id)
        self.assertTrue(event.payment_ref)

    def test_a_genuine_event_the_shop_ignores_is_none(self):
        self.assertIsNone(self.gw.parse_event(*self.other_webhook()))

    def test_an_untrusted_webhook_is_a_payment_error(self):
        with self.assertRaises(PaymentError):
            self.gw.parse_event(*self.tampered_webhook())

    def test_garbage_is_a_payment_error_not_a_crash(self):
        for payload in (b"", b"not json", b"[]", b"null"):
            with self.assertRaises(PaymentError, msg=payload):
                self.gw.parse_event(payload, "nope")

    # ---- refunds

    def test_a_full_and_a_partial_refund(self):
        full = self.gw.refund("pi_1")
        self.assertIsInstance(full, RefundResult)
        self.assertIsNone(full.amount)
        partial = self.gw.refund("pi_1", Decimal("12.50"))
        self.assertEqual(partial.amount, Decimal("12.50"))

    def test_nothing_to_refund_sends_nothing(self):
        self.assertTrue(self.gw.refund("").simulated)

    def test_a_provider_failure_on_refund_is_a_payment_error(self):
        with self.provider_down(), self.assertRaises(PaymentError):
            self.gw.refund("pi_1")


class MemoryGatewayContract(GatewayContract, SimpleTestCase):
    def make_gateway(self):
        return MemoryGateway()

    def paid_webhook(self, order_ref):
        body = {"event": "paid", "order": order_ref, "session": "mem_1", "payment": "pay_1",
                "email": "buyer@example.com", "name": "Ada Buyer", "address": ADDRESS, "total": "80"}
        return json.dumps(body).encode(), MEMORY_SECRET

    def other_webhook(self):
        return json.dumps({"event": "dispute"}).encode(), MEMORY_SECRET

    def tampered_webhook(self):
        return self.paid_webhook("42")[0], "wrong-signature"

    @contextlib.contextmanager
    def provider_down(self):
        # the in-memory provider refuses an empty basket and a non-positive refund
        original = self.gw.create_checkout
        self.gw.create_checkout = lambda req: original(CheckoutRequest(**{**req.__dict__, "lines": ()}))
        original_refund = self.gw.refund
        self.gw.refund = lambda ref, amount=None: original_refund(ref, Decimal("-1"))
        yield


def stripe_signed(event):
    body = json.dumps(event)
    ts = str(int(time.time()))
    sig = hmac.new(WEBHOOK_SECRET.encode(), f"{ts}.{body}".encode(), hashlib.sha256).hexdigest()
    return body.encode(), f"t={ts},v1={sig}"


def stripe_completed(order_ref, **session):
    base = {
        "id": "cs_test_1", "object": "checkout.session",
        "metadata": {"order_id": str(order_ref)}, "client_reference_id": None,
        "payment_intent": "pi_1", "amount_total": 8000,
        "total_details": {"amount_tax": 0, "amount_shipping": 0},
        "customer_details": {"email": "buyer@example.com", "name": "Ada Buyer", "address": ADDRESS},
    }
    base.update(session)
    return {"id": "evt_1", "object": "event", "type": "checkout.session.completed", "data": {"object": base}}


class StripeGatewayContract(GatewayContract, SimpleTestCase):
    def make_gateway(self):
        create = mock.patch("stripe.checkout.Session.create", return_value=SimpleNamespace(
            id="cs_test_1", url="https://checkout.stripe.test/c/cs_test_1"))
        refund = mock.patch("stripe.Refund.create", return_value=SimpleNamespace(id="re_1"))
        self.create_mock, self.refund_mock = create.start(), refund.start()
        self.addCleanup(create.stop)
        self.addCleanup(refund.stop)
        return StripeGateway(secret_key="sk_test_x", webhook_secret=WEBHOOK_SECRET)

    def paid_webhook(self, order_ref):
        return stripe_signed(stripe_completed(order_ref))

    def other_webhook(self):
        return stripe_signed({"id": "evt_2", "object": "event", "type": "charge.dispute.created", "data": {"object": {}}})

    def tampered_webhook(self):
        return self.paid_webhook("42")[0], "t=1,v1=bad"

    @contextlib.contextmanager
    def provider_down(self):
        self.create_mock.side_effect = stripe.PermissionError("wrong key type")
        self.refund_mock.side_effect = stripe.InvalidRequestError("already refunded", "x")
        yield


class StripeWireFormat(SimpleTestCase):
    """What Stripe is actually sent and what is read from what it sends back."""

    def setUp(self):
        create = mock.patch("stripe.checkout.Session.create", return_value=SimpleNamespace(id="cs_1", url="https://s"))
        refund = mock.patch("stripe.Refund.create", return_value=SimpleNamespace(id="re_1"))
        self.create, self.refund_call = create.start(), refund.start()
        self.addCleanup(create.stop)
        self.addCleanup(refund.stop)
        self.gw = StripeGateway(secret_key="sk_test_x", webhook_secret=WEBHOOK_SECRET)

    def sent(self, **over):
        self.gw.create_checkout(sample_request(**over))
        return self.create.call_args.kwargs

    def test_line_items_are_in_cents_and_tax_exclusive(self):
        item = self.sent()["line_items"][0]
        self.assertEqual(item["quantity"], 2)
        self.assertEqual(item["price_data"]["unit_amount"], 4000)
        self.assertEqual(item["price_data"]["currency"], "usd")
        self.assertEqual(item["price_data"]["tax_behavior"], "exclusive")
        self.assertEqual(item["price_data"]["product_data"], {"name": "Pillars", "description": "Tee, Black, M"})

    def test_the_order_ref_travels_with_the_session(self):
        sent = self.sent()
        self.assertEqual(sent["client_reference_id"], "42")
        self.assertEqual(sent["metadata"], {"order_id": "42"})
        self.assertEqual(sent["customer_email"], "buyer@example.com")
        self.assertIsNone(self.sent(email="")["customer_email"])

    def test_the_key_is_passed_per_call_not_stored_globally(self):
        self.assertEqual(self.sent()["api_key"], "sk_test_x")
        self.assertNotEqual(stripe.api_key, "sk_test_x")

    def test_the_return_link_uses_stripes_own_placeholder(self):
        self.assertEqual(self.sent()["success_url"], "https://shop.test/checkout/success/?ref={CHECKOUT_SESSION_ID}")
        self.assertEqual(self.sent()["cancel_url"], "https://shop.test/cart/")

    def test_free_standard_shipping_with_the_promised_days(self):
        rate = self.sent()["shipping_options"][0]["shipping_rate_data"]
        self.assertEqual(rate["fixed_amount"], {"amount": 0, "currency": "usd"})
        self.assertEqual(rate["display_name"], STANDARD_SHIPPING.label)
        self.assertEqual(rate["delivery_estimate"],
                         {"minimum": {"unit": "day", "value": 10}, "maximum": {"unit": "day", "value": 14}})
        self.assertEqual(self.sent()["shipping_address_collection"], {"allowed_countries": ["US"]})

    def test_automatic_tax_only_when_asked(self):
        self.assertNotIn("automatic_tax", self.sent())
        self.assertEqual(self.sent(collect_tax=True)["automatic_tax"], {"enabled": True})

    def test_without_a_key_it_is_simulated_and_never_calls_stripe(self):
        gw = StripeGateway(secret_key="", webhook_secret=WEBHOOK_SECRET)
        self.assertTrue(gw.simulated)
        with self.assertRaises(PaymentError):
            gw.create_checkout(sample_request())
        self.assertTrue(gw.refund("pi_1", Decimal("5")).simulated)
        self.create.assert_not_called()
        self.refund_call.assert_not_called()

    def test_without_a_key_it_still_verifies_a_signed_webhook(self):
        gw = StripeGateway(secret_key="", webhook_secret=WEBHOOK_SECRET)
        self.assertEqual(gw.parse_event(*stripe_signed(stripe_completed(7))).order_ref, "7")

    def test_a_webhook_with_no_secret_configured_is_never_trusted(self):
        gw = StripeGateway(secret_key="sk_test_x", webhook_secret="")
        with self.assertRaises(PaymentError):
            gw.parse_event(*stripe_signed(stripe_completed(7)))

    def test_refund_amounts_go_in_cents(self):
        self.gw.refund("pi_9", Decimal("12.50"))
        self.assertEqual(self.refund_call.call_args.kwargs,
                         {"api_key": "sk_test_x", "payment_intent": "pi_9", "reason": "requested_by_customer",
                          "amount": 1250})
        self.gw.refund("pi_9")
        self.assertNotIn("amount", self.refund_call.call_args.kwargs)

    def test_the_order_ref_can_come_from_either_field(self):
        event = self.gw.parse_event(*stripe_signed(stripe_completed(None, client_reference_id="31", metadata={})))
        self.assertEqual(event.order_ref, "31")

    def test_a_payment_with_no_order_ref_is_ignored(self):
        self.assertIsNone(self.gw.parse_event(*stripe_signed(stripe_completed(None, metadata={}))))

    def test_shipping_details_win_over_billing_for_the_address(self):
        ship = {"address": {**ADDRESS, "line1": "9 Ship Rd"}}
        event = self.gw.parse_event(*stripe_signed(stripe_completed(5, shipping_details=ship)))
        self.assertEqual(event.address["line1"], "9 Ship Rd")

    def test_tax_and_shipping_are_read_from_the_totals(self):
        event = self.gw.parse_event(*stripe_signed(stripe_completed(
            5, amount_total=9000, total_details={"amount_tax": 500, "amount_shipping": 500})))
        self.assertEqual((event.total, event.tax, event.shipping, event.items_total),
                         (Decimal("90"), Decimal("5"), Decimal("5"), Decimal("80")))
