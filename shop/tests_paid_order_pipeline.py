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


class SyncListingReplyShapeTests(TestCase):
    """sync_listing must store the ids from Printful's real nested reply."""

    def test_real_nested_reply_shape_stores_product_and_sync_variant_ids(self):
        design = Design.objects.create(title="Wanderer")
        tpl = ProductTemplate.objects.create(name="Tee", product_type="tee")
        listing = Listing.objects.create(design=design, template=tpl, product_type="tee")
        ListingSize.objects.create(listing=listing, label="M", printful_variant_id="17145")
        client = mock.MagicMock(is_mock=False)
        client.create_sync_product.return_value = {
            "sync_product": {"id": 474865517, "external_id": listing.slug},
            "sync_variants": [{"id": 5123456789, "external_id": f"{listing.slug}::M", "variant_id": 17145}],
        }
        with mock.patch.object(printful, "get_client", return_value=client):
            printful.sync_listing(listing)
        listing.refresh_from_db()
        self.assertEqual(listing.printful_product_id, "474865517")
        self.assertEqual(listing.sizes.get(label="M").printful_variant_id, "5123456789")


from django.contrib.auth import get_user_model  # noqa: E402


@override_settings(STAFF_2FA_REQUIRED=False)
class RefreshSizesAndPlacementTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user("curator", password="x-12345-yz", is_staff=True)
        self.c = Client()
        self.c.force_login(self.staff)

    def connected_listing(self, color="Khaki", labels=("S", "M")):
        tpl = ProductTemplate.objects.create(name="Tee", product_type="tee", print_placement="front")
        listing = Listing.objects.create(design=Design.objects.create(title="Wanderer"), template=tpl,
                                         product_type="tee", color=color, printful_product_id="474865517")
        for i, label in enumerate(labels):
            ListingSize.objects.create(listing=listing, label=label, printful_variant_id=str(17144 + i))
        return listing

    def fake_client(self, variants):
        client = mock.MagicMock(is_mock=False)
        client.get_sync_product.return_value = {"sync_product": {"id": 474865517}, "sync_variants": variants}
        return client

    def refresh(self, listing, variants):
        with mock.patch.object(printful, "get_client", return_value=self.fake_client(variants)):
            return self.c.post(f"/manage/listings/{listing.pk}/refresh-printful-sizes/", follow=True)

    def test_refresh_stores_real_sync_variant_ids_by_name(self):
        listing = self.connected_listing()
        r = self.refresh(listing, [
            {"id": 5001, "name": "Wanderer - Khaki / S"}, {"id": 5002, "name": "Wanderer - Khaki / M"},
            {"id": 5003, "name": "Wanderer - Black / M"},
        ])
        self.assertContains(r, "Refreshed all 2")
        ids = dict(listing.sizes.values_list("label", "printful_variant_id"))
        self.assertEqual(ids, {"S": "5001", "M": "5002"})

    def test_refresh_uses_size_and_color_fields_when_present(self):
        listing = self.connected_listing(labels=("M",))
        self.refresh(listing, [{"id": 7, "size": "M", "color": "Khaki"}, {"id": 8, "size": "M", "color": "Black"}])
        self.assertEqual(listing.sizes.get().printful_variant_id, "7")

    def test_refresh_uses_our_own_external_id_first(self):
        listing = self.connected_listing(labels=("M",))
        self.refresh(listing, [{"id": 9, "external_id": f"{listing.slug}::M"}])
        self.assertEqual(listing.sizes.get().printful_variant_id, "9")

    def test_ambiguous_size_is_left_alone_not_guessed(self):
        listing = self.connected_listing(color="", labels=("M",))
        r = self.refresh(listing, [{"id": 1, "size": "M", "color": "Khaki"}, {"id": 2, "size": "M", "color": "Black"}])
        self.assertEqual(listing.sizes.get().printful_variant_id, "17144")
        self.assertContains(r, "no sizes that match")

    def test_partial_match_warns_and_only_updates_matched(self):
        listing = self.connected_listing()
        r = self.refresh(listing, [{"id": 5002, "name": "Wanderer - Khaki / M"}])
        self.assertContains(r, "Refreshed 1 size")
        self.assertEqual(listing.sizes.get(label="S").printful_variant_id, "17144")

    def test_not_connected_listing_gets_a_clear_error(self):
        listing = self.connected_listing()
        listing.printful_product_id = ""
        listing.save()
        r = self.refresh(listing, [])
        self.assertContains(r, "isn&#x27;t connected")

    def test_refresh_button_only_shows_on_connected_listings(self):
        listing = self.connected_listing()
        self.assertContains(self.c.get(f"/manage/listings/{listing.pk}/"), "Refresh sizes from Printful")
        listing.printful_product_id = ""
        listing.save()
        self.assertNotContains(self.c.get(f"/manage/listings/{listing.pk}/"), "Refresh sizes from Printful")

    def test_mock_client_supports_refresh(self):
        listing = self.connected_listing()
        matched, unmatched = printful.refresh_sync_variants(listing)
        self.assertEqual((matched, unmatched), (["S", "M"], []))

    # --- front / back ---
    def form(self, listing, **over):
        data = {"title": "Wanderer", "color": "Khaki", "base_cost": "11", "shipping_est": "5", "price": "40",
                "print_scale_pct": "100", "print_position": "center"}
        data.update(over)
        return self.c.post(f"/manage/listings/{listing.pk}/", data)

    def test_listing_can_be_set_to_the_back(self):
        listing = self.connected_listing()
        self.form(listing, print_placement="back")
        listing.refresh_from_db()
        self.assertEqual(listing.print_placement, "back")
        self.assertEqual(listing.print_file_payload()["type"], "back")

    def test_blank_falls_back_to_the_templates_placement(self):
        listing = self.connected_listing()
        self.form(listing, print_placement="back")
        self.form(listing, print_placement="")
        listing.refresh_from_db()
        self.assertEqual(listing.print_file_payload()["type"], "front")

    def test_invalid_or_missing_placement_keeps_the_previous_value(self):
        listing = self.connected_listing()
        self.form(listing, print_placement="back")
        self.form(listing, print_placement="chest_tattoo")
        self.form(listing)
        listing.refresh_from_db()
        self.assertEqual(listing.print_placement, "back")

    def test_edit_page_shows_the_choice(self):
        listing = self.connected_listing()
        listing.print_placement = "back"
        listing.save()
        page = self.c.get(f"/manage/listings/{listing.pk}/")
        self.assertContains(page, '<option value="back" selected>')
        self.assertContains(page, "Template default (Front)")


@override_settings(STAFF_2FA_REQUIRED=False)
class FulfilmentNoteColorTests(TestCase):
    """A note on a healthy fulfilment (e.g. 'Reprint of #1') is not an error."""

    def page(self, status):
        from .orders import Fulfillment
        order = make_order()
        f = Fulfillment.objects.create(order=order, supplier="printful", status=status,
                                       problem_note="Reprint of fulfilment #1: Test fix")
        f.items.set(order.items.all())
        c = Client()
        c.force_login(get_user_model().objects.create_user("cur", password="x-12345-yz", is_staff=True))
        return c.get(f"/manage/orders/{order.pk}/").content.decode()

    def test_note_on_a_submitted_fulfilment_is_green(self):
        html = self.page("submitted")
        self.assertIn('class="form-note success">Reprint of', html)

    def test_note_on_a_problem_fulfilment_stays_red(self):
        html = self.page("problem")
        self.assertIn('class="form-note error">Reprint of', html)


@override_settings(STAFF_2FA_REQUIRED=False)
class RefundCancelsPrintfulTests(TestCase):
    """Refunding must also cancel the print order, or Printful prints and
    ships (and charges you for) an order the customer got their money back on."""

    def setUp(self):
        self.c = Client()
        self.c.force_login(get_user_model().objects.create_user("cur", password="x-12345-yz", is_staff=True))

    def submitted(self, status="submitted", partner="177915062"):
        from .orders import Fulfillment
        order = make_order()
        order.status = OrderStatus.SUBMITTED
        order.save()
        ful = Fulfillment.objects.create(order=order, supplier="printful", status=status, partner_order_id=partner)
        ful.items.set(order.items.all())
        return order, ful

    def cancel_client(self, error=None):
        client = mock.MagicMock(is_mock=False)
        if error:
            client.cancel_order.side_effect = printful.PrintfulError(error)
        return client

    def test_refund_cancels_the_printful_order(self):
        order, ful = self.submitted()
        client = self.cancel_client()
        with mock.patch.object(printful, "get_client", return_value=client):
            r = self.c.post(f"/manage/orders/{order.pk}/refund/", {"reason": "wrong shirt"}, follow=True)
        client.cancel_order.assert_called_once_with("177915062")
        order.refresh_from_db(); ful.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.REFUNDED)
        self.assertEqual(ful.status, "cancelled")
        self.assertContains(r, "Printful order 177915062 cancelled")

    def test_if_printful_wont_cancel_the_refund_stands_and_you_are_told(self):
        order, ful = self.submitted(status="in_production")
        with mock.patch.object(printful, "get_client", return_value=self.cancel_client("already in production")):
            r = self.c.post(f"/manage/orders/{order.pk}/refund/", {"reason": "x"}, follow=True)
        order.refresh_from_db(); ful.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.REFUNDED)
        self.assertEqual(ful.status, "in_production")
        self.assertContains(r, "Cancel it in the Printful dashboard by hand")
        self.assertContains(r, "already in production")

    def test_shipped_orders_are_not_cancelled(self):
        order, ful = self.submitted(status="shipped")
        client = self.cancel_client()
        with mock.patch.object(printful, "get_client", return_value=client):
            self.c.post(f"/manage/orders/{order.pk}/refund/", {"reason": "x"})
        client.cancel_order.assert_not_called()

    def test_a_stripe_failure_changes_nothing_and_shows_a_message(self):
        import stripe
        from . import payments
        order, ful = self.submitted()
        client = self.cancel_client()
        with mock.patch.object(printful, "get_client", return_value=client), \
                mock.patch.object(payments, "refund", side_effect=stripe.InvalidRequestError("already refunded", "x")):
            r = self.c.post(f"/manage/orders/{order.pk}/refund/", {"reason": "x"}, follow=True)
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.SUBMITTED)
        client.cancel_order.assert_not_called()
        self.assertContains(r, "Stripe couldn")

    def test_refunding_twice_is_a_noop(self):
        order, ful = self.submitted()
        client = self.cancel_client()
        with mock.patch.object(printful, "get_client", return_value=client):
            self.c.post(f"/manage/orders/{order.pk}/refund/", {"reason": "x"})
            self.c.post(f"/manage/orders/{order.pk}/refund/", {"reason": "x"})
        client.cancel_order.assert_called_once()

    def test_printfuls_own_cancel_echo_does_not_flip_our_cancelled_fulfilment_to_problem(self):
        order, ful = self.submitted(status="cancelled")
        fulfillment.apply_partner_event("order_canceled", {"order": {"id": 177915062, "external_id": order.reference}})
        ful.refresh_from_db()
        self.assertEqual(ful.status, "cancelled")

    def test_cancel_button_cancels_without_refunding(self):
        order, ful = self.submitted()
        client = self.cancel_client()
        with mock.patch.object(printful, "get_client", return_value=client):
            r = self.c.post(f"/manage/fulfillments/{ful.pk}/cancel/", follow=True)
        order.refresh_from_db(); ful.refresh_from_db()
        self.assertEqual(ful.status, "cancelled")
        self.assertEqual(order.status, OrderStatus.SUBMITTED)  # payment untouched
        self.assertContains(r, "cancelled")

    def test_cancel_button_only_shows_when_cancellable(self):
        order, ful = self.submitted()
        self.assertContains(self.c.get(f"/manage/orders/{order.pk}/"), "Cancel on Printful")
        ful.status = "shipped"; ful.save()
        self.assertNotContains(self.c.get(f"/manage/orders/{order.pk}/"), "Cancel on Printful")

    def test_cancel_endpoint_refuses_a_shipped_fulfilment(self):
        order, ful = self.submitted(status="shipped")
        client = self.cancel_client()
        with mock.patch.object(printful, "get_client", return_value=client):
            self.c.post(f"/manage/fulfillments/{ful.pk}/cancel/")
        client.cancel_order.assert_not_called()
