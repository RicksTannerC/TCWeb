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
    # a sent listing carries a sync variant id; an unsent one a catalogue id
    ids = {"printful_variant_id": variant_id} if connected else {"printful_catalog_variant_id": variant_id}
    size = ListingSize.objects.create(listing=listing, label="M", **ids)
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


class UsProductionTests(TestCase):
    def check(self, data):
        with mock.patch.object(printful, "_cached_variants", return_value=data):
            return printful.us_production("456")

    def test_eu_only_list_shape_is_flagged(self):
        self.assertIs(self.check({"variants": [
            {"availability_status": [{"region": "EU", "status": "active"}, {"region": "UK", "status": "active"}]}]}), False)

    def test_us_in_list_shape_is_ok(self):
        self.assertIs(self.check({"variants": [
            {"availability_status": [{"region": "US", "status": "active"}, {"region": "EU", "status": "active"}]}]}), True)

    def test_mapping_shape_on_the_product_is_understood(self):
        self.assertIs(self.check({"product": {"availability_regions": {"EU": "Europe", "LV": "Latvia"}}, "variants": []}), False)
        self.assertIs(self.check({"product": {"availability_regions": {"US": "USA"}}, "variants": []}), True)

    def test_a_discontinued_us_entry_does_not_count(self):
        self.assertIs(self.check({"variants": [
            {"availability_status": [{"region": "US", "status": "discontinued"}, {"region": "EU", "status": "active"}]}]}), False)

    def test_no_availability_data_says_nothing_rather_than_warning(self):
        self.assertIsNone(self.check({"variants": [{"id": 1, "size": "M"}]}))
        self.assertIsNone(printful.us_production(""))

    def test_a_printful_error_says_nothing(self):
        with mock.patch.object(printful, "_cached_variants", side_effect=printful.PrintfulError("down")):
            self.assertIsNone(printful.us_production("456"))


@override_settings(STAFF_2FA_REQUIRED=False)
class UsWarningAndTrackingPageTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()  # the listing page caches Printful variants; don't leak that into other tests
        self.addCleanup(cache.clear)
        self.c = Client()
        self.c.force_login(get_user_model().objects.create_user("cur", password="x-12345-yz", is_staff=True))

    def listing(self):
        tpl = ProductTemplate.objects.create(name="Tee", product_type="tee", printful_blueprint_id="456",
                                             printful_blueprint_name="Stanley/Stella STTU169")
        return Listing.objects.create(design=Design.objects.create(title="W"), template=tpl, product_type="tee")

    def test_listing_page_warns_when_the_product_is_not_us_produced(self):
        listing = self.listing()
        with mock.patch.object(printful, "us_production", return_value=False):
            page = self.c.get(f"/manage/listings/{listing.pk}/")
        self.assertContains(page, "Not made in the US")
        self.assertContains(page, "Stanley/Stella STTU169")

    def test_no_warning_when_us_produced_or_unknown(self):
        listing = self.listing()
        for value in (True, None):
            with mock.patch.object(printful, "us_production", return_value=value):
                self.assertNotContains(self.c.get(f"/manage/listings/{listing.pk}/"), "Not made in the US")

    def test_tracking_page_hides_internal_notes_and_softens_problem(self):
        from .orders import Fulfillment
        order = make_order()
        f = Fulfillment.objects.create(order=order, supplier="printful", status="problem",
                                       problem_note="Printful rejected the order: Item 0: Sync variant not found")
        r = Client().get(f"/order/{order.track_token}/")
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertNotIn("Sync variant", html)
        self.assertNotIn("needs attention", html)
        self.assertIn("looking into it", html)


class OperatingEntityTests(TestCase):
    """The contracting business is named on the footer and in every email."""

    LLC = "The Tshirt Brand L.L.C."

    def test_footer_names_the_llc(self):
        html = Client().get("/").content.decode()
        self.assertIn(f"operated by {self.LLC}", html)
        self.assertNotIn("Wyoming, USA", html)

    def test_emails_identify_the_sender_and_postal_address(self):
        from django.core import mail
        from .emails import send_order_confirmation, send_subscribe_welcome
        from .orders import Subscriber
        order = make_order()
        order.email = "buyer@example.com"
        order.save()
        send_order_confirmation(order)
        send_subscribe_welcome(Subscriber.objects.create(email="fan@example.com"))
        self.assertEqual(len(mail.outbox), 2)
        for m in mail.outbox:
            self.assertIn(f"operated by {self.LLC}", m.body)

    def test_legal_name_is_configurable(self):
        with override_settings(SHOP_LEGAL_NAME="Other Co LLC"):
            self.assertIn("operated by Other Co LLC", Client().get("/").content.decode())



@override_settings(STAFF_2FA_REQUIRED=False)
class ResendToPrintfulTests(TestCase):
    """Editing the shirt/color in the console must be able to reach Printful."""

    def setUp(self):
        self.c = Client()
        self.c.force_login(get_user_model().objects.create_user("cur", password="x-12345-yz", is_staff=True))

    def sent_listing(self, color="Khaki", labels=("S", "M")):
        tpl = ProductTemplate.objects.create(name="Tee", product_type="tee", printful_blueprint_id="456")
        listing = Listing.objects.create(
            design=Design.objects.create(title="Wanderer"), template=tpl, product_type="tee", color=color,
            printful_product_id="474865517", printful_sent_blueprint_id="456", printful_sent_color=color,
            printful_sent_placement="front")
        for i, label in enumerate(labels):
            ListingSize.objects.create(listing=listing, label=label, printful_variant_id=str(9000 + i),
                                       printful_catalog_variant_id=str(4000 + i))
        return listing

    def resend(self, listing, client):
        with mock.patch.object(printful, "get_client", return_value=client):
            r = self.c.post(f"/manage/listings/{listing.pk}/resend-to-printful/")
        return self.c.get(r["Location"])  # render the result page with the real (mock) client, not this stub

    def new_product_client(self):
        client = mock.MagicMock(is_mock=False)

        def create(payload):
            return {"sync_product": {"id": 999},
                    "sync_variants": [{"id": 8000 + i, "external_id": v["external_id"]}
                                      for i, v in enumerate(payload["sync_variants"])]}
        client.create_sync_product.side_effect = create
        return client

    def test_resend_builds_a_new_product_from_the_current_catalogue_ids(self):
        listing = self.sent_listing()
        client = self.new_product_client()
        r = self.resend(listing, client)
        payload = client.create_sync_product.call_args[0][0]
        self.assertEqual([v["variant_id"] for v in payload["sync_variants"]], [4000, 4001])
        self.assertNotEqual(payload["sync_product"]["external_id"], listing.slug)  # fresh, unique
        listing.refresh_from_db()
        self.assertEqual(listing.printful_product_id, "999")
        self.assertEqual(dict(listing.sizes.values_list("label", "printful_variant_id")), {"S": "8000", "M": "8001"})
        self.assertContains(r, "old product (474865517)")

    def test_resend_never_deletes_the_old_product(self):
        listing = self.sent_listing()
        client = self.new_product_client()
        self.resend(listing, client)
        self.assertFalse([c for c in client.method_calls if "delete" in c[0] or "cancel" in c[0]])

    def test_resend_records_what_was_sent(self):
        listing = self.sent_listing()
        listing.color = "Black"
        listing.print_placement = "back"
        listing.save()
        self.resend(listing, self.new_product_client())
        listing.refresh_from_db()
        self.assertEqual((listing.printful_sent_color, listing.printful_sent_placement), ("Black", "back"))
        self.assertEqual(listing.printful_changes_not_sent, [])

    def test_resend_refuses_until_sizes_are_matched(self):
        listing = self.sent_listing()
        listing.sizes.update(printful_catalog_variant_id="")
        client = self.new_product_client()
        r = self.resend(listing, client)
        self.assertContains(r, "Match sizes to Printful variants first")
        client.create_sync_product.assert_not_called()
        listing.refresh_from_db()
        self.assertEqual(listing.printful_product_id, "474865517")

    def test_a_printful_failure_leaves_the_listing_on_its_old_product(self):
        listing = self.sent_listing()
        client = mock.MagicMock(is_mock=False)
        client.create_sync_product.side_effect = printful.PrintfulError("nope")
        r = self.resend(listing, client)
        self.assertContains(r, "wouldn")
        listing.refresh_from_db()
        self.assertEqual(listing.printful_product_id, "474865517")
        self.assertEqual(listing.sizes.get(label="S").printful_variant_id, "9000")

    def test_unsent_listing_is_told_to_use_send(self):
        listing = self.sent_listing()
        listing.printful_product_id = ""
        listing.save()
        r = self.resend(listing, self.new_product_client())
        self.assertContains(r, "on Printful yet")

    # ---- matching no longer touches the id orders use ----
    def test_matching_sizes_on_a_sent_listing_does_not_overwrite_the_sync_ids(self):
        listing = self.sent_listing(labels=("S", "M"))
        self.c.post(f"/manage/listings/{listing.pk}/match-printful-sizes/")
        self.assertEqual(dict(listing.sizes.values_list("label", "printful_variant_id")), {"S": "9000", "M": "9001"})

    # ---- out-of-sync banner ----
    def test_page_warns_when_color_or_shirt_changed_since_sending(self):
        listing = self.sent_listing()
        listing.color = "Black"
        listing.save()
        listing.template.printful_blueprint_id = "71"
        listing.template.save()
        page = self.c.get(f"/manage/listings/{listing.pk}/")
        self.assertContains(page, "Printful still has the old version")
        self.assertContains(page, "color (Khaki")
        self.assertContains(page, "shirt (product 456")

    def test_no_warning_when_in_step(self):
        listing = self.sent_listing()
        self.assertNotContains(self.c.get(f"/manage/listings/{listing.pk}/"), "Printful still has the old version")

    def test_sent_before_tracking_gets_a_gentle_note_not_an_alarm(self):
        listing = self.sent_listing()
        listing.printful_sent_blueprint_id = listing.printful_sent_color = listing.printful_sent_placement = ""
        listing.save()
        page = self.c.get(f"/manage/listings/{listing.pk}/")
        self.assertContains(page, "before the console tracked")
        self.assertNotContains(page, "Printful still has the old version")

    def test_resend_button_only_on_sent_listings(self):
        listing = self.sent_listing()
        self.assertContains(self.c.get(f"/manage/listings/{listing.pk}/"), "Re-send to Printful")
        listing.printful_product_id = ""
        listing.save()
        self.assertNotContains(self.c.get(f"/manage/listings/{listing.pk}/"), "Re-send to Printful")


class UnsentIdMigrationTests(TestCase):
    def test_unsent_listings_ids_move_to_the_catalogue_field(self):
        import importlib

        from django.apps import apps
        mig = importlib.import_module("shop.migrations.0012_move_unsent_variant_ids_to_catalog")
        tpl = ProductTemplate.objects.create(name="Tee", product_type="tee")
        unsent = Listing.objects.create(design=Design.objects.create(title="A"), template=tpl, product_type="tee")
        sent = Listing.objects.create(design=Design.objects.create(title="B"), template=tpl, product_type="tee",
                                      printful_product_id="1")
        a = ListingSize.objects.create(listing=unsent, label="M", printful_variant_id="4012")
        b = ListingSize.objects.create(listing=sent, label="M", printful_variant_id="9000")
        mig.move_unsent_ids(apps, None)
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual((a.printful_variant_id, a.printful_catalog_variant_id), ("", "4012"))
        self.assertEqual((b.printful_variant_id, b.printful_catalog_variant_id), ("9000", ""))
