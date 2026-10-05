"""A listing that was sent to Printful must end up with Printful's id for each size
(Printful's reply to 'create product' doesn't include them), and a reprint that
can't be built must say so instead of crashing and leaving stray rows.
Stub clients only -- nothing here reaches Printful."""

from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

from . import fulfillment, printful
from .models import Design, Listing, ListingSize, ProductTemplate, Status
from .orders import Fulfillment, Order, OrderItem, OrderStatus


def make_listing(connected=False, sync_ids=None, catalog_ids=("4011", "4012")):
    tpl = ProductTemplate.objects.create(name="Tee", product_type="tee", printful_blueprint_id="586")
    listing = Listing.objects.create(
        design=Design.objects.create(title="Jack-o"), template=tpl, product_type="tee", color="Ivory",
        status=Status.LIVE, price=Decimal("40"), printful_product_id="477732182" if connected else "")
    for i, label in enumerate(("M", "L")):
        ListingSize.objects.create(
            listing=listing, label=label, printful_catalog_variant_id=catalog_ids[i] if catalog_ids else "",
            printful_variant_id=(sync_ids or {}).get(label, ""))
    return listing


def make_order(listing, status=OrderStatus.APPROVED):
    order = Order.objects.create(status=status, name="Ada", email="a@b.c", shipping_address={
        "line1": "1 Main St", "city": "Afton", "state": "WY", "postal_code": "83110", "country": "US"})
    size = listing.sizes.get(label="M")
    item = OrderItem.objects.create(order=order, listing=listing, listing_size=size, design_title="Jack-o",
                                    product_type="tee", size_label="M", quantity=1, unit_price=Decimal("40"))
    return order, item


def failed_fulfilment(order, item):
    ful = Fulfillment.objects.create(order=order, supplier="printful", status=Fulfillment.Status.PROBLEM,
                                     problem_note="Printful rejected the order: no variant")
    ful.items.set([item])
    return ful


def summary_client(read_back=None, read_back_error=None):
    """A stub whose 'create product' reply is Printful's real summary shape (no per-size ids)."""
    client = mock.MagicMock(is_mock=False)
    client.create_sync_product.return_value = {"id": 555, "external_id": "x", "name": "Jack-o", "variants": 2, "synced": 2}
    if read_back_error:
        client.get_sync_product.side_effect = printful.PrintfulError(read_back_error)
    else:
        client.get_sync_product.return_value = {"sync_product": {"id": 555}, "sync_variants": read_back or []}
    client.create_order.return_value = {"id": 777}
    return client


class SyncIdsTests(TestCase):
    def send(self, listing, client, **kw):
        with mock.patch.object(printful, "get_client", return_value=client):
            return printful.sync_listing(listing, **kw)

    def sizes(self, listing):
        return dict(listing.sizes.values_list("label", "printful_variant_id"))

    def test_a_summary_reply_is_followed_by_a_read_back_that_stores_each_sizes_id(self):
        listing = make_listing()
        client = summary_client(read_back=[
            {"id": 9001, "external_id": "jack-o::M", "name": "Jack-o - Ivory / M"},
            {"id": 9002, "external_id": "jack-o::L", "name": "Jack-o - Ivory / L"}])
        self.send(listing, client)
        client.get_sync_product.assert_called_once_with("555")
        self.assertEqual(self.sizes(listing), {"M": "9001", "L": "9002"})
        self.assertEqual(listing.printful_product_id, "555")

    def test_the_read_back_also_works_when_only_the_name_says_which_size(self):
        listing = make_listing()
        client = summary_client(read_back=[
            {"id": 9001, "name": "Jack-o - Ivory / M"}, {"id": 9002, "name": "Jack-o - Ivory / L"}])
        self.send(listing, client)
        self.assertEqual(self.sizes(listing), {"M": "9001", "L": "9002"})

    def test_when_the_reply_already_has_the_ids_nothing_extra_is_read(self):
        listing = make_listing()
        client = mock.MagicMock(is_mock=False)
        client.create_sync_product.return_value = {
            "sync_product": {"id": 555}, "sync_variants": [
                {"id": 1, "external_id": "jack-o::M"}, {"id": 2, "external_id": "jack-o::L"}]}
        self.send(listing, client)
        client.get_sync_product.assert_not_called()
        self.assertEqual(self.sizes(listing), {"M": "1", "L": "2"})

    def test_a_failed_read_back_leaves_sizes_blank_but_the_listing_connected(self):
        listing = make_listing()
        self.send(listing, summary_client(read_back_error="down"))
        self.assertEqual(self.sizes(listing), {"M": "", "L": ""})
        self.assertEqual(listing.printful_product_id, "555")

    def test_a_resend_never_keeps_the_old_products_ids(self):
        listing = make_listing(connected=True, sync_ids={"M": "17708", "L": "17709"})
        self.send(listing, summary_client(read_back_error="down"), replace=True)
        self.assertEqual(self.sizes(listing), {"M": "", "L": ""})  # blank, not the old product's

    def test_a_resend_stores_the_new_products_ids(self):
        listing = make_listing(connected=True, sync_ids={"M": "17708", "L": "17709"})
        client = summary_client(read_back=[{"id": 8001, "name": "Jack-o - Ivory / M"}, {"id": 8002, "name": "Jack-o - Ivory / L"}])
        self.send(listing, client, replace=True)
        self.assertEqual(self.sizes(listing), {"M": "8001", "L": "8002"})

    def test_then_an_order_can_actually_be_built_and_submitted(self):
        """The whole chain that failed in practice: send -> order -> approve."""
        listing = make_listing()
        client = summary_client(read_back=[{"id": 9001, "name": "Jack-o - Ivory / M"}, {"id": 9002, "name": "Jack-o - Ivory / L"}])
        self.send(listing, client)
        listing.refresh_from_db()
        order, item = make_order(listing, status=OrderStatus.PENDING_APPROVAL)
        with mock.patch.object(printful, "get_client", return_value=client):
            fulfillment.approve_and_submit(order)
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.SUBMITTED)
        line = client.create_order.call_args[0][0]["items"][0]
        self.assertEqual(line["sync_variant_id"], 9001)


@override_settings(STAFF_2FA_REQUIRED=False)
class SendWarnsViewTests(TestCase):
    def setUp(self):
        self.c = Client()
        self.c.force_login(get_user_model().objects.create_user("cur", password="x-12345-yz", is_staff=True))

    def post(self, listing, client, action="printful/"):
        with mock.patch.object(printful, "get_client", return_value=client):
            r = self.c.post(f"/manage/listings/{listing.pk}/{action}")
        return self.c.get(r["Location"])

    def test_send_warns_when_sizes_could_not_be_read_back(self):
        listing = make_listing()
        page = self.post(listing, summary_client(read_back_error="down"))
        self.assertContains(page, "weren&#x27;t read back for: M, L")
        self.assertContains(page, "Refresh sizes from Printful")

    def test_no_warning_when_every_size_got_its_id(self):
        listing = make_listing()
        page = self.post(listing, summary_client(read_back=[
            {"id": 1, "name": "Jack-o - Ivory / M"}, {"id": 2, "name": "Jack-o - Ivory / L"}]))
        self.assertNotContains(page, "read back for")

    def test_resend_warns_too(self):
        listing = make_listing(connected=True, sync_ids={"M": "1", "L": "2"})
        page = self.post(listing, summary_client(read_back_error="down"), action="resend-to-printful/")
        self.assertContains(page, "weren&#x27;t read back for: M, L")


@override_settings(STAFF_2FA_REQUIRED=False)
class ReprintTests(TestCase):
    def setUp(self):
        self.c = Client()
        self.c.force_login(get_user_model().objects.create_user("cur", password="x-12345-yz", is_staff=True))

    def reprint(self, ful, client):
        with mock.patch.object(printful, "get_client", return_value=client):
            r = self.c.post(f"/manage/fulfillments/{ful.pk}/reprint/", {"reason": "retry"})
        self.assertEqual(r.status_code, 302)  # never a 500
        return self.c.get(r["Location"])

    def test_a_size_without_a_printful_id_gives_a_message_not_an_error_page(self):
        listing = make_listing(connected=True, sync_ids={})  # connected, sizes have no sync id (the real case)
        order, item = make_order(listing)
        ful = failed_fulfilment(order, item)
        client = mock.MagicMock(is_mock=False)
        page = self.reprint(ful, client)
        self.assertContains(page, "Couldn&#x27;t reprint")
        self.assertContains(page, "Jack-o (M) has no Printful variant")
        self.assertContains(page, "Nothing was sent to Printful")
        client.create_order.assert_not_called()

    def test_that_failure_creates_no_stray_fulfilment(self):
        listing = make_listing(connected=True, sync_ids={})
        order, item = make_order(listing)
        ful = failed_fulfilment(order, item)
        self.reprint(ful, mock.MagicMock(is_mock=False))
        self.reprint(ful, mock.MagicMock(is_mock=False))
        self.assertEqual(order.fulfillments.count(), 1)

    def test_a_good_reprint_is_submitted_and_the_order_moves_on(self):
        listing = make_listing(connected=True, sync_ids={"M": "9001", "L": "9002"})
        order, item = make_order(listing, status=OrderStatus.APPROVED)
        ful = failed_fulfilment(order, item)
        client = mock.MagicMock(is_mock=False)
        client.create_order.return_value = {"id": 777}
        page = self.reprint(ful, client)
        new = order.fulfillments.exclude(pk=ful.pk).get()
        self.assertEqual((new.status, new.partner_order_id), ("submitted", "777"))
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.SUBMITTED)
        self.assertContains(page, "sent to Printful")

    def test_a_reprint_of_an_order_already_in_production_does_not_rewind_it(self):
        listing = make_listing(connected=True, sync_ids={"M": "9001", "L": "9002"})
        order, item = make_order(listing, status=OrderStatus.IN_PRODUCTION)
        ful = failed_fulfilment(order, item)
        client = mock.MagicMock(is_mock=False)
        client.create_order.return_value = {"id": 777}
        self.reprint(ful, client)
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.IN_PRODUCTION)

    def test_when_printful_refuses_the_reprint_it_is_kept_as_a_problem_and_says_so(self):
        listing = make_listing(connected=True, sync_ids={"M": "9001", "L": "9002"})
        order, item = make_order(listing)
        ful = failed_fulfilment(order, item)
        client = mock.MagicMock(is_mock=False)
        client.create_order.side_effect = printful.PrintfulError("address invalid")
        page = self.reprint(ful, client)
        new = order.fulfillments.exclude(pk=ful.pk).get()
        self.assertEqual(new.status, "problem")
        self.assertIn("address invalid", new.problem_note)
        self.assertContains(page, "didn&#x27;t accept it")
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.APPROVED)

    def test_the_mock_client_still_reprints_for_local_development(self):
        listing = make_listing(connected=True, sync_ids={"M": "9001", "L": "9002"})
        order, item = make_order(listing)
        ful = failed_fulfilment(order, item)
        with mock.patch.object(printful, "get_client", return_value=printful.MockPrintful()):
            self.c.post(f"/manage/fulfillments/{ful.pk}/reprint/", {"reason": "dev"})
        self.assertEqual(order.fulfillments.exclude(pk=ful.pk).get().status, "submitted")


@override_settings(STAFF_2FA_REQUIRED=False)
class MissingIdsBannerTests(TestCase):
    """A listing on Printful whose sizes lack Printful ids must say so before an order finds out."""

    def setUp(self):
        self.c = Client()
        self.c.force_login(get_user_model().objects.create_user("cur", password="x-12345-yz", is_staff=True))

    def page(self, listing):
        return self.c.get(f"/manage/listings/{listing.pk}/").content.decode()

    def test_warns_and_names_the_sizes_when_a_connected_listing_has_no_ids(self):
        html = self.page(make_listing(connected=True, sync_ids={}))
        self.assertIn("Orders for this listing will fail", html)
        self.assertIn("M, L have no Printful size id", html)
        self.assertIn("hiding the listing", html)  # it is live

    def test_names_only_the_sizes_that_are_missing(self):
        html = self.page(make_listing(connected=True, sync_ids={"M": "1"}))
        self.assertIn("L has no Printful size id", html)

    def test_no_warning_once_every_size_has_its_id(self):
        html = self.page(make_listing(connected=True, sync_ids={"M": "1", "L": "2"}))
        self.assertNotIn("Orders for this listing will fail", html)

    def test_no_warning_for_a_listing_that_is_not_on_printful_yet(self):
        html = self.page(make_listing(connected=False))
        self.assertNotIn("Orders for this listing will fail", html)
