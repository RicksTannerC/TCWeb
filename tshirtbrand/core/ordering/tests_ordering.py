"""The ordering context on its own: the status rules, and every use case run against an in-memory order book, the
in-memory supplier and the in-memory payment gateway. No database, no network, no Django models."""

from dataclasses import replace
from decimal import Decimal

from django.test import SimpleTestCase

from tshirtbrand.adapters.payments.memory.gateway import MemoryGateway
from tshirtbrand.adapters.suppliers.memory.supplier import MemorySupplier
from tshirtbrand.core.fulfilment.api import (
    EventKind, OrderLine, Recipient, SubmittedOrder, SupplierError, SupplierEvent,
)
from tshirtbrand.core.payments.api import PaymentError, PaymentEvent, PaymentEventKind

from . import api
from .api import FulfilmentChange, FulfilmentStatus as F, FulfilmentView, OrderDesk, OrderStatus as O, OrderView


class RuleTests(SimpleTestCase):
    def test_references_round_trip_through_the_id_we_give_the_supplier(self):
        self.assertEqual(api.reference(12), "TTS-00012")
        self.assertEqual(api.external_id(12, 5), "TTS-00012-5")
        self.assertEqual(api.external_id(12, 5, reprint=True), "TTS-00012-5-reprint")
        self.assertEqual(api.parse_external_id("TTS-00012-5"), (12, 5))
        self.assertEqual(api.parse_external_id("TTS-00012-5-reprint"), (12, 5))

    def test_ids_that_are_not_ours_parse_to_nothing(self):
        for junk in ("", None, "TTS-00012", "ORD-1-2", "TTS-x-y", "nonsense"):
            self.assertIsNone(api.parse_external_id(junk), junk)

    def test_only_a_us_address_with_the_basics_looks_complete(self):
        good = {"line1": "1 Main", "city": "Afton", "state": "WY", "postal_code": "83110"}
        self.assertTrue(api.address_looks_complete(good))
        self.assertTrue(api.address_looks_complete({**good, "country": "US"}))
        self.assertFalse(api.address_looks_complete({**good, "country": "CA"}))
        self.assertFalse(api.address_looks_complete({**good, "city": ""}))
        self.assertFalse(api.address_looks_complete(None))

    def test_every_order_holds_for_approval_today(self):
        self.assertTrue(api.should_hold(object()))

    def test_a_fulfilment_can_be_cancelled_only_while_it_sits_at_the_supplier(self):
        def view(status, supplier_order_id="9"):
            return FulfilmentView(1, 1, "memory", supplier_order_id, status, "", ())
        for status in (F.SUBMITTED, F.IN_PRODUCTION, F.PROBLEM):
            self.assertTrue(view(status).can_cancel, status)
        for status in (F.PENDING, F.SHIPPED, F.DELIVERED, F.CANCELLED):
            self.assertFalse(view(status).can_cancel, status)
        self.assertFalse(view(F.SUBMITTED, "").can_cancel)   # never reached the supplier


class RollupTests(SimpleTestCase):
    def test_the_order_follows_its_fulfilments(self):
        cases = [
            ([F.SUBMITTED], O.SUBMITTED), ([F.PENDING], O.SUBMITTED),
            ([F.IN_PRODUCTION], O.IN_PRODUCTION), ([F.SUBMITTED, F.IN_PRODUCTION], O.IN_PRODUCTION),
            ([F.SHIPPED], O.SHIPPED), ([F.SHIPPED, F.DELIVERED], O.SHIPPED),
            ([F.SHIPPED, F.IN_PRODUCTION], O.IN_PRODUCTION), ([F.DELIVERED, F.DELIVERED], O.DELIVERED),
        ]
        for statuses, expected in cases:
            self.assertEqual(api.rollup(O.SUBMITTED, statuses), expected, statuses)

    def test_a_problem_pins_the_order_where_it_is(self):
        self.assertEqual(api.rollup(O.SUBMITTED, [F.PROBLEM, F.SHIPPED]), O.SUBMITTED)
        self.assertEqual(api.rollup(O.IN_PRODUCTION, [F.PROBLEM]), O.IN_PRODUCTION)

    def test_cancelled_fulfilments_are_ignored_and_none_left_changes_nothing(self):
        self.assertEqual(api.rollup(O.SUBMITTED, [F.CANCELLED, F.SHIPPED]), O.SHIPPED)
        self.assertEqual(api.rollup(O.REFUNDED, [F.CANCELLED]), O.REFUNDED)
        self.assertEqual(api.rollup(O.APPROVED, []), O.APPROVED)


class EventTests(SimpleTestCase):
    def test_what_each_event_does_to_a_fulfilment(self):
        shipped = api.change_for_event(SupplierEvent(EventKind.SHIPPED, tracking_number="T1", tracking_url="u", carrier="UPS"))
        self.assertEqual((shipped.status, shipped.tracking_number, shipped.carrier), (F.SHIPPED, "T1", "UPS"))
        self.assertEqual(api.change_for_event(SupplierEvent(EventKind.IN_PRODUCTION)).status, F.IN_PRODUCTION)
        for kind in (EventKind.RETURNED, EventKind.FAILED, EventKind.ON_HOLD, EventKind.CANCELED):
            change = api.change_for_event(SupplierEvent(kind, reason="why"))
            self.assertEqual((change.status, change.problem_note), (F.PROBLEM, "why"), kind)


# ------------------------------------------------------------------ the use cases, over in-memory collaborators

class MemoryOrders:
    """An order book in a dict."""

    def __init__(self):
        self.status, self.note, self.fulfilments = O.PENDING_APPROVAL, "", {}
        self.next_id = 1
        self.payment_ref = "pi_1"
        self.items = (101, 102)

    def order(self, order_id):
        return OrderView(order_id, self.status, self.payment_ref, Recipient("Ada"), self.items,
                         tuple(self.fulfilments.values()))

    def create_order(self, email, items, items_total):
        self.created = (email, items, items_total)
        self.status = O.PENDING_PAYMENT
        return 1

    def set_checkout_session(self, order_id, session_id):
        self.session_id = session_id

    def record_payment(self, order_id, event):
        self.paid_by = event
        self.status = O.PENDING_APPROVAL

    def find_fulfilment(self, supplier_order_id, order_id=None, fulfilment_id=None):
        if supplier_order_id:
            for f in self.fulfilments.values():
                if f.supplier_order_id == supplier_order_id:
                    return f
        return self.fulfilments.get(fulfilment_id) if order_id is not None else None

    def add_fulfilment(self, order_id, supplier, item_ids, problem_note=""):
        fid, self.next_id = self.next_id, self.next_id + 1
        self.fulfilments[fid] = FulfilmentView(fid, order_id, supplier, "", F.PENDING, problem_note, tuple(item_ids))
        return fid

    def update_fulfilment(self, fulfilment_id, change):
        old = self.fulfilments[fulfilment_id]
        self.fulfilments[fulfilment_id] = replace(old, **{
            name: value for name, value in (
                ("status", change.status), ("supplier_order_id", change.supplier_order_id),
                ("problem_note", change.problem_note)) if value is not None})

    def set_order_status(self, order_id, status, note=None):
        self.status = status
        if note:
            self.note = (self.note + f"\n{note}").strip()


class Lines:
    def __init__(self):
        self.broken = set()

    def line_for(self, item_id):
        if item_id in self.broken:
            raise SupplierError(f"item {item_id} has no variant")
        return OrderLine(quantity=1, name=f"item {item_id}", unit_price=Decimal("40"), product_variant_id=str(item_id))


class Notes:
    def __init__(self):
        self.sent = []

    def order_status_changed(self, order_id):
        self.sent.append(order_id)


class DeskCase(SimpleTestCase):
    def setUp(self):
        self.book, self.supplier, self.lines = MemoryOrders(), MemorySupplier(), Lines()
        self.notes, self.gateway = Notes(), MemoryGateway()
        self.desk = OrderDesk(self.book, self.supplier, self.lines, self.notes, self.gateway)

    def only(self):
        return next(iter(self.book.fulfilments.values()))


class PlaceAndPayTests(DeskCase):
    def item(self, qty, price):
        return api.NewItem(listing_id=1, size_id=2, name="Pillars", product_type="tee", color="Black", size_label="M",
                           quantity=qty, unit_price=Decimal(price), unit_supplier_cost=Decimal("11"))

    def paid(self, order_ref="1"):
        return PaymentEvent(PaymentEventKind.PAID, order_ref, "cs_1", "pi_1", email="a@b.test", total=Decimal("80"))

    def test_placing_an_order_totals_its_items(self):
        self.assertEqual(self.desk.place_order(None, [self.item(2, "40.00"), self.item(1, "5.50")]), 1)
        email, items, total = self.book.created
        self.assertEqual((email, len(items), total), ("", 2, Decimal("85.50")))
        self.assertEqual(self.book.status, O.PENDING_PAYMENT)

    def test_the_checkout_session_is_remembered_for_the_return_link(self):
        self.desk.remember_checkout_session(1, "cs_9")
        self.assertEqual(self.book.session_id, "cs_9")

    def test_a_confirmed_payment_promotes_the_order_once(self):
        self.desk.place_order("a@b.test", [self.item(2, "40")])
        self.assertEqual(self.desk.confirm_payment(self.paid()), (1, True))
        self.assertEqual(self.book.status, O.PENDING_APPROVAL)
        self.assertEqual(self.desk.confirm_payment(self.paid()), (1, False))   # the provider told us twice

    def test_a_payment_for_nothing_of_ours_is_ignored(self):
        self.assertEqual(self.desk.confirm_payment(self.paid("not-a-number")), (None, False))

    def test_a_payment_for_an_order_already_past_payment_changes_nothing(self):
        self.book.status = O.SHIPPED
        self.assertEqual(self.desk.confirm_payment(self.paid()), (1, False))
        self.assertEqual(self.book.status, O.SHIPPED)
        self.assertFalse(hasattr(self.book, "paid_by"))


class ApproveTests(DeskCase):
    def test_approval_creates_a_fulfilment_and_submits_it(self):
        self.desk.approve_and_submit(1, note="ok to go")
        ful = self.only()
        self.assertEqual((ful.status, ful.supplier, ful.item_ids), (F.SUBMITTED, "memory", (101, 102)))
        self.assertTrue(ful.supplier_order_id)
        self.assertEqual((self.book.status, self.book.note), (O.SUBMITTED, "ok to go"))

    def test_only_an_order_awaiting_approval_can_be_approved(self):
        self.book.status = O.SHIPPED
        with self.assertRaisesMessage(ValueError, "TTS-00001 is not awaiting approval"):
            self.desk.approve_and_submit(1)
        self.assertEqual(self.book.fulfilments, {})

    def test_a_supplier_refusal_leaves_a_problem_and_an_approved_order(self):
        self.lines.broken.add(102)
        self.desk.approve_and_submit(1)
        ful = self.only()
        self.assertEqual(ful.status, F.PROBLEM)
        self.assertIn("rejected the order: item 102 has no variant", ful.problem_note)
        self.assertEqual(self.book.status, O.APPROVED)
        self.assertIn("Submit failed", self.book.note)

    def test_the_id_we_give_the_supplier_points_back_at_the_fulfilment(self):
        self.desk.approve_and_submit(1)
        order_id, ful_id = api.parse_external_id(api.external_id(1, self.only().id))
        self.assertEqual((order_id, ful_id), (1, self.only().id))


class EventUseCaseTests(DeskCase):
    def submitted(self):
        self.desk.approve_and_submit(1)
        return self.only()

    def test_news_moves_the_fulfilment_and_the_order_and_tells_the_customer(self):
        ful = self.submitted()
        self.assertEqual(self.desk.apply_event(SupplierEvent(EventKind.IN_PRODUCTION, supplier_order_id=ful.supplier_order_id)), 1)
        self.assertEqual((self.only().status, self.book.status), (F.IN_PRODUCTION, O.IN_PRODUCTION))
        self.desk.apply_event(SupplierEvent(EventKind.SHIPPED, supplier_order_id=ful.supplier_order_id, tracking_number="T"))
        self.assertEqual((self.only().status, self.book.status), (F.SHIPPED, O.SHIPPED))
        self.assertEqual(self.notes.sent, [1, 1])

    def test_an_event_can_be_matched_by_the_id_we_gave_when_the_suppliers_is_unknown(self):
        ful = self.submitted()
        event = SupplierEvent(EventKind.IN_PRODUCTION, supplier_order_id="", external_id=api.external_id(1, ful.id))
        self.assertEqual(self.desk.apply_event(event), 1)
        self.assertEqual(self.only().status, F.IN_PRODUCTION)

    def test_an_event_that_matches_nothing_is_ignored(self):
        self.submitted()
        self.assertIsNone(self.desk.apply_event(SupplierEvent(EventKind.SHIPPED, supplier_order_id="nope", external_id="x")))
        self.assertIsNone(self.desk.apply_event(SupplierEvent(EventKind.SHIPPED)))   # no ids at all

    def test_a_problem_event_keeps_the_order_where_it_is(self):
        ful = self.submitted()
        self.desk.apply_event(SupplierEvent(EventKind.FAILED, supplier_order_id=ful.supplier_order_id, reason="no stock"))
        self.assertEqual((self.only().status, self.only().problem_note, self.book.status), (F.PROBLEM, "no stock", O.SUBMITTED))
        self.assertEqual(self.notes.sent, [])

    def test_the_echo_of_our_own_cancel_is_not_a_problem(self):
        ful = self.submitted()
        self.desk.cancel_fulfilment(ful.id, 1)
        self.desk.apply_event(SupplierEvent(EventKind.CANCELED, supplier_order_id=ful.supplier_order_id, reason="x"))
        self.assertEqual(self.only().status, F.CANCELLED)

    def test_a_failing_email_never_holds_up_the_order(self):
        ful = self.submitted()
        self.notes.order_status_changed = lambda order_id: 1 / 0
        self.desk.apply_event(SupplierEvent(EventKind.IN_PRODUCTION, supplier_order_id=ful.supplier_order_id))
        self.assertEqual(self.book.status, O.IN_PRODUCTION)

    def test_a_raw_webhook_body_goes_through_the_suppliers_own_reading_of_it(self):
        ful = self.submitted()
        body = {"event": "in_production", "order": ful.supplier_order_id}
        self.assertEqual(self.desk.handle_supplier_payload(body), 1)
        self.assertIsNone(self.desk.handle_supplier_payload({"garbage": True}))


class CancelRefundTests(DeskCase):
    def submitted(self):
        self.desk.approve_and_submit(1)
        return self.only()

    def test_cancelling_one_fulfilment_leaves_the_order_alone(self):
        ful = self.submitted()
        self.desk.cancel_fulfilment(ful.id, 1)
        self.assertEqual(self.only().status, F.CANCELLED)
        self.assertIn("Cancelled at", self.only().problem_note)
        self.assertEqual(self.book.status, O.SUBMITTED)

    def test_refunding_pays_back_then_cancels_what_can_be_cancelled(self):
        ful = self.submitted()
        cancelled, failures = self.desk.refund_order(1, reason="changed mind")
        self.assertEqual((cancelled, failures), ([ful.supplier_order_id], []))
        self.assertEqual(self.gateway.refunds, [("pi_1", None)])
        self.assertEqual(self.book.status, O.REFUNDED)
        self.assertIn("Refunded: changed mind", self.book.note)
        self.assertEqual(self.only().status, F.CANCELLED)

    def test_a_refused_refund_changes_nothing(self):
        self.submitted()

        def refuse(ref, amount=None):
            raise PaymentError("already refunded")
        self.gateway.refund = refuse
        with self.assertRaises(PaymentError):
            self.desk.refund_order(1, reason="x")
        self.assertEqual((self.book.status, self.only().status), (O.SUBMITTED, F.SUBMITTED))

    def test_refunding_twice_does_nothing_the_second_time(self):
        self.submitted()
        self.desk.refund_order(1, reason="x")
        self.assertEqual(self.desk.refund_order(1, reason="x"), ([], []))
        self.assertEqual(len(self.gateway.refunds), 1)

    def test_a_supplier_that_wont_cancel_is_reported_and_the_rest_still_cancel(self):
        ful = self.submitted()
        second = self.book.add_fulfilment(1, "memory", (101,))
        self.book.update_fulfilment(second, FulfilmentChange(status=F.SUBMITTED, supplier_order_id="other"))
        self.supplier.orders["other"] = object()
        real_cancel = self.supplier.cancel_order

        def cancel(order_id):
            if order_id == ful.supplier_order_id:
                raise SupplierError("already in production")
            return real_cancel(order_id)
        self.supplier.cancel_order = cancel
        cancelled, failures = self.desk.cancel_supplier_orders(1)
        self.assertEqual(cancelled, ["other"])
        self.assertEqual(failures, [f"{ful.supplier_order_id} (already in production)"])
        self.assertEqual(self.book.fulfilments[ful.id].status, F.SUBMITTED)


class ReprintTests(DeskCase):
    def test_a_reprint_is_a_second_submitted_fulfilment_of_the_same_items(self):
        self.desk.approve_and_submit(1)
        old = self.only()
        new_id = self.desk.reprint(old.id, 1, reason="smudged")
        new = self.book.fulfilments[new_id]
        self.assertEqual((new.status, new.item_ids), (F.SUBMITTED, old.item_ids))
        self.assertTrue(new.problem_note.startswith(f"Reprint of fulfilment #{old.id}: smudged"))
        self.assertEqual(self.book.fulfilments[old.id].status, F.SUBMITTED)   # a healthy original is left alone

    def test_lines_that_cannot_be_built_create_nothing(self):
        self.desk.approve_and_submit(1)
        old = self.only()
        self.lines.broken.add(101)
        with self.assertRaises(SupplierError):
            self.desk.reprint(old.id, 1)
        self.assertEqual(len(self.book.fulfilments), 1)

    def test_a_refused_reprint_is_kept_as_a_problem_with_the_reason(self):
        self.desk.approve_and_submit(1)
        old = self.only()
        self.supplier.submit_order = lambda request: (_ for _ in ()).throw(SupplierError("out of stock"))
        new_id = self.desk.reprint(old.id, 1, reason="r")
        new = self.book.fulfilments[new_id]
        self.assertEqual(new.status, F.PROBLEM)
        self.assertTrue(new.problem_note.endswith("— submit failed: out of stock"))

    def test_replacing_a_failed_attempt_unpins_the_order(self):
        self.lines.broken.add(102)
        self.desk.approve_and_submit(1)                    # fails: Problem + Approved
        failed = self.only()
        self.lines.broken.clear()
        new_id = self.desk.reprint(failed.id, 1, reason="retry")
        self.assertEqual(self.book.fulfilments[failed.id].status, F.CANCELLED)
        self.assertIn(f"Replaced by reprint #{new_id}", self.book.fulfilments[failed.id].problem_note)
        self.assertEqual(self.book.status, O.SUBMITTED)


class SimulateTests(DeskCase):
    def test_each_step_moves_everything_one_stage_and_ships_with_a_tracking_number(self):
        self.desk.approve_and_submit(1)
        self.desk.simulate_advance(1, stamp=7)
        self.assertEqual((self.only().status, self.book.status), (F.IN_PRODUCTION, O.IN_PRODUCTION))
        self.desk.simulate_advance(1, stamp=7)
        self.assertEqual((self.only().status, self.book.status), (F.SHIPPED, O.SHIPPED))
        self.desk.simulate_advance(1, stamp=7)
        self.assertEqual((self.only().status, self.book.status), (F.DELIVERED, O.DELIVERED))
        self.desk.simulate_advance(1, stamp=7)   # nothing further to do
        self.assertEqual(self.book.status, O.DELIVERED)


class CostRecordingTests(SimpleTestCase):
    def test_a_reported_cost_is_recorded_with_its_tax(self):
        change = api.submitted_change(SubmittedOrder("9", "pending", Decimal("19.09"), Decimal("1.15")))
        self.assertEqual((change.supplier_order_id, change.supplier_cost, change.supplier_tax),
                         ("9", Decimal("19.09"), Decimal("1.15")))

    def test_an_unreported_cost_records_nothing(self):
        change = api.submitted_change(SubmittedOrder("9", "pending", None, Decimal("1")))
        self.assertEqual((change.supplier_cost, change.supplier_tax), (None, None))
