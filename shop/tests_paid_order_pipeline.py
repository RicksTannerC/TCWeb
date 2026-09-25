"""Paid order -> Stripe webhook -> awaiting approval -> Printful order.

Regression for the first real payment: the webhook crashed on Stripe's
StripeObject (no .get), so the order never left pending_payment. These tests
sign payloads locally with a fake secret (pure HMAC, no network) so they go
through the real construct_event path and get a real StripeObject.
"""

import hashlib
import hmac
import json
import time
from decimal import Decimal
from unittest import mock

from django.test import Client, TestCase, override_settings

from . import fulfillment, printful
from .models import Design, Listing, ListingSize, ProductTemplate, Status
from .orders import Order, OrderItem, OrderStatus

SECRET = "whsec_test_local_only"


def _signed_post(client, event):
    body = json.dumps(event)
    ts = str(int(time.time()))
    sig = hmac.new(SECRET.encode(), f"{ts}.{body}".encode(), hashlib.sha256).hexdigest()
    return client.post("/webhooks/stripe/", data=body, content_type="application/json",
                       HTTP_STRIPE_SIGNATURE=f"t={ts},v1={sig}")


def _completed_event(order_id):
    return {
        "id": "evt_1", "object": "event", "type": "checkout.session.completed",
        "data": {"object": {
            "id": "cs_test_1", "object": "checkout.session",
            "metadata": {"order_id": str(order_id)}, "client_reference_id": None,
            "payment_intent": "pi_1", "amount_total": 4000,
            "total_details": {"amount_tax": 0, "amount_shipping": 0},
            "customer_details": {"email": "buyer@example.com", "name": "Ada Buyer",
                                 "address": {"line1": "1 Main St", "city": "Afton", "state": "WY",
                                             "postal_code": "83110", "country": "US"}},
        }},
    }


def make_order(*, variant_id="777", connected=False):
    tpl = ProductTemplate.objects.create(name="Tee", product_type="tee", base_cost=Decimal("11"))
    design = Design.objects.create(title="Pillars")
    listing = Listing.objects.create(design=design, template=tpl, product_type="tee",
                                     status=Status.LIVE, price=Decimal("40"),
                                     printful_product_id="999" if connected else "")
    size = ListingSize.objects.create(listing=listing, label="M", printful_variant_id=variant_id)
    order = Order.objects.create(status=OrderStatus.PENDING_PAYMENT)
    OrderItem.objects.create(order=order, listing=listing, listing_size=size, design_title="Pillars",
                             product_type="tee", size_label="M", quantity=1, unit_price=Decimal("40"))
    return order


@override_settings(STRIPE_WEBHOOK_SECRET=SECRET)
class StripeWebhookTests(TestCase):
    def test_a_real_signed_event_promotes_the_order(self):
        order = make_order()
        r = _signed_post(Client(), _completed_event(order.pk))
        self.assertEqual(r.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.PENDING_APPROVAL)
        self.assertEqual(order.email, "buyer@example.com")
        self.assertEqual(order.name, "Ada Buyer")
        self.assertEqual(order.shipping_address["postal_code"], "83110")
        self.assertEqual(order.stripe_payment_intent, "pi_1")
        self.assertEqual(order.grand_total, Decimal("40"))

    def test_replaying_the_same_event_is_harmless(self):
        order = make_order()
        _signed_post(Client(), _completed_event(order.pk))
        r = _signed_post(Client(), _completed_event(order.pk))
        self.assertEqual(r.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.PENDING_APPROVAL)

    def test_a_bad_signature_is_rejected_and_changes_nothing(self):
        order = make_order()
        r = Client().post("/webhooks/stripe/", data=json.dumps(_completed_event(order.pk)),
                          content_type="application/json", HTTP_STRIPE_SIGNATURE="t=1,v1=bad")
        self.assertEqual(r.status_code, 400)
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.PENDING_PAYMENT)


class LineTests(TestCase):
    def test_synced_listing_sends_the_ordered_sizes_sync_variant(self):
        order = make_order(variant_id="555", connected=True)
        line = fulfillment._line(order.items.get())
        self.assertEqual(line["sync_variant_id"], 555)
        self.assertNotIn("variant_id", line)

    def test_unsynced_listing_orders_from_the_catalog_variant_with_art(self):
        order = make_order(variant_id="4012", connected=False)
        with mock.patch.object(Design, "print_file_url", "https://example.test/art.png"):
            line = fulfillment._line(order.items.get())
        self.assertEqual(line["variant_id"], 4012)
        self.assertNotIn("sync_variant_id", line)
        self.assertEqual(line["files"][0]["url"], "https://example.test/art.png")

    def test_no_variant_id_raises_a_clear_error(self):
        order = make_order(variant_id="")
        with self.assertRaisesMessage(printful.PrintfulError, "Match sizes"):
            fulfillment._line(order.items.get())


class ApproveTests(TestCase):
    def approvable(self, **kw):
        order = make_order(**kw)
        order.status = OrderStatus.PENDING_APPROVAL
        order.name, order.email = "Ada", "a@b.c"
        order.shipping_address = {"line1": "1 Main St", "city": "Afton", "state": "WY",
                                  "postal_code": "83110", "country": "US"}
        order.save()
        return order

    def test_approve_submits_through_the_mock_client(self):
        order = self.approvable(variant_id="555", connected=True)
        fulfillment.approve_and_submit(order)
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.SUBMITTED)
        self.assertTrue(order.fulfillments.get().partner_order_id)

    def test_approve_with_an_unmatched_size_fails_cleanly_not_with_a_crash(self):
        order = self.approvable(variant_id="")
        fulfillment.approve_and_submit(order)
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.APPROVED)
        self.assertIn("Match sizes", order.curator_note)
        self.assertEqual(order.fulfillments.get().status, "problem")
