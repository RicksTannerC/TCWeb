"""The print partner's real charge (and the sales tax in it) is recorded per fulfilment
and drives the books; until it is known the listing's base cost is the estimate."""

from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

from . import fulfillment, printful
from .models import Design, Listing, ListingSize, ProductTemplate
from .orders import Fulfillment, Order, OrderItem, OrderStatus

REAL_REPLY = {"id": 179489366, "status": "pending", "costs": {
    "subtotal": "12.95", "discount": "0.00", "shipping": "4.99", "digitization": "0.00",
    "additional_fee": "0.00", "fulfillment_fee": "0.00", "tax": "1.15", "vat": "0.00", "total": "19.09"}}


def make_order(price="40", est_cost="15", status=OrderStatus.APPROVED, qty=1):
    tpl, _ = ProductTemplate.objects.get_or_create(name="Tee", defaults={"product_type": "tee"})
    listing = Listing.objects.create(design=Design.objects.create(title="Jack-o"), template=tpl,
                                     product_type="tee", printful_product_id="1")
    size = ListingSize.objects.create(listing=listing, label="M", printful_variant_id="55")
    order = Order.objects.create(status=status, email="a@b.c", name="Ada", items_total=Decimal(price) * qty,
                                 shipping_address={"line1": "1 Main", "city": "Afton", "state": "WY",
                                                   "postal_code": "83110", "country": "US"})
    item = OrderItem.objects.create(order=order, listing=listing, listing_size=size, design_title="Jack-o",
                                    product_type="tee", size_label="M", quantity=qty,
                                    unit_price=Decimal(price), unit_supplier_cost=Decimal(est_cost))
    return order, item


def ful(order, item, actual=None, tax=None, status="submitted"):
    f = Fulfillment.objects.create(order=order, supplier="printful", status=status,
                                   supplier_cost_actual=actual, supplier_tax=tax)
    f.items.set([item])
    return f


class RecordTests(TestCase):
    def test_the_real_reply_shape_is_stored_total_and_tax(self):
        order, item = make_order()
        f = ful(order, item)
        fulfillment.record_supplier_costs(f, REAL_REPLY)
        self.assertEqual((f.supplier_cost_actual, f.supplier_tax), (Decimal("19.09"), Decimal("1.15")))

    def test_vat_counts_as_tax_paid_too(self):
        order, item = make_order()
        f = ful(order, item)
        fulfillment.record_supplier_costs(f, {"costs": {"total": "20.00", "tax": "0.00", "vat": "2.50"}})
        self.assertEqual(f.supplier_tax, Decimal("2.50"))

    def test_no_costs_block_or_nonsense_records_nothing(self):
        order, item = make_order()
        for reply in ({}, {"costs": None}, {"costs": {"total": "n/a"}}, {"costs": {"total": "0.00"}}, "oops"):
            f = ful(order, item)
            fulfillment.record_supplier_costs(f, reply)
            self.assertIsNone(f.supplier_cost_actual, reply)

    def test_approve_and_submit_records_what_printful_reports(self):
        order, item = make_order(status=OrderStatus.PENDING_APPROVAL)
        client = mock.MagicMock(is_mock=False)
        client.create_order.return_value = REAL_REPLY
        with mock.patch.object(printful, "get_client", return_value=client):
            fulfillment.approve_and_submit(order)
        f = order.fulfillments.get()
        self.assertEqual((f.supplier_cost_actual, f.supplier_tax), (Decimal("19.09"), Decimal("1.15")))

    def test_a_reprint_records_its_own_charge(self):
        order, item = make_order()
        failed = ful(order, item, status="problem")
        client = mock.MagicMock(is_mock=False)
        client.create_order.return_value = REAL_REPLY
        with mock.patch.object(printful, "get_client", return_value=client):
            new = fulfillment.reprint(failed, reason="retry")
        self.assertEqual(new.supplier_cost_actual, Decimal("19.09"))

    def test_the_mock_never_records_a_zero_cost(self):
        order, item = make_order(status=OrderStatus.PENDING_APPROVAL)
        with mock.patch.object(printful, "get_client", return_value=printful.MockPrintful()):
            fulfillment.approve_and_submit(order)
        self.assertIsNone(order.fulfillments.get().supplier_cost_actual)


class OrderCostTests(TestCase):
    def test_estimate_is_used_until_a_real_charge_is_recorded(self):
        order, item = make_order(est_cost="15")
        self.assertEqual(order.supplier_cost, Decimal("15.00"))
        self.assertTrue(order.supplier_cost_is_estimate)
        self.assertEqual(order.supplier_tax, Decimal("0.00"))

    def test_the_real_charge_replaces_the_estimate_and_sets_the_margin(self):
        order, item = make_order(price="40", est_cost="15")
        ful(order, item, actual=Decimal("19.09"), tax=Decimal("1.15"))
        order = Order.objects.get(pk=order.pk)
        self.assertEqual(order.supplier_cost, Decimal("19.09"))
        self.assertFalse(order.supplier_cost_is_estimate)
        self.assertEqual(order.supplier_tax, Decimal("1.15"))
        self.assertEqual(order.margin, Decimal("40.00") - Decimal("19.09"))

    def test_a_reprint_that_was_billed_counts_twice(self):
        order, item = make_order()
        ful(order, item, actual=Decimal("19.09"), tax=Decimal("1.15"))
        ful(order, item, actual=Decimal("19.09"), tax=Decimal("1.15"))
        order = Order.objects.get(pk=order.pk)
        self.assertEqual(order.supplier_cost, Decimal("38.18"))
        self.assertEqual(order.supplier_tax, Decimal("2.30"))

    def test_an_unrecorded_failed_fulfilment_does_not_hide_the_recorded_one(self):
        order, item = make_order()
        ful(order, item, status="problem")
        ful(order, item, actual=Decimal("19.09"), tax=Decimal("1.15"))
        self.assertEqual(Order.objects.get(pk=order.pk).supplier_cost, Decimal("19.09"))


@override_settings(STAFF_2FA_REQUIRED=False)
class BooksTests(TestCase):
    def setUp(self):
        self.c = Client()
        self.c.force_login(get_user_model().objects.create_user("cur", password="x-12345-yz", is_staff=True))

    def test_books_use_the_real_cost_and_show_printfuls_tax_separately_from_tax_collected(self):
        a, ai = make_order(price="40", est_cost="15")
        ful(a, ai, actual=Decimal("19.09"), tax=Decimal("1.15"))
        a.tax_total = Decimal("2.00")
        a.save()
        make_order(price="30", est_cost="12")  # still an estimate
        r = self.c.get("/manage/money/")
        ctx, html = r.context, r.content.decode()
        self.assertEqual(ctx["supplier_cost"], Decimal("31.09"))   # 19.09 real + 12.00 estimate
        self.assertEqual(ctx["supplier_tax"], Decimal("1.15"))
        self.assertEqual(ctx["tax_collected"], Decimal("2.00"))
        self.assertEqual(ctx["estimated_orders"], 1)
        self.assertEqual(ctx["net"], Decimal("70.00") - Decimal("31.09"))  # tax collected is not income
        self.assertIn("Sales tax Printful charged you", html)
        self.assertIn("1 order still estimated from base cost", html)
        self.assertIn("not income, not in Net", html)

    def test_when_everything_is_recorded_the_page_says_so(self):
        a, ai = make_order()
        ful(a, ai, actual=Decimal("19.09"), tax=Decimal("1.15"))
        self.assertIn("what Printful actually charged", self.c.get("/manage/money/").content.decode())

    def test_refunded_orders_stay_out_of_the_supplier_totals(self):
        a, ai = make_order(status=OrderStatus.REFUNDED)
        ful(a, ai, actual=Decimal("19.09"), tax=Decimal("1.15"))
        ctx = self.c.get("/manage/money/").context
        self.assertEqual(ctx["supplier_cost"], Decimal("0"))
        self.assertEqual(ctx["supplier_tax"], Decimal("0"))
