"""The Django ORM adapters keep the promises the core's repository ports make."""

from decimal import Decimal

from django.test import TestCase

from shop.models import Design, Listing, ListingSize, ProductTemplate, Status
from shop.orders import Fulfillment, Order
from tshirtbrand.core.catalogue.api import ListingView
from tshirtbrand.core.fulfilment.api import Preview
from tshirtbrand.core.ordering.api import FulfilmentChange, FulfilmentStatus as F, NewItem, OrderStatus as O
from tshirtbrand.core.payments.api import PaymentEvent, PaymentEventKind

from .django_orm.listings import DjangoListingRepository
from .django_orm.orders import DjangoOrderRepository


def make_listing(status=Status.DRAFT):
    tpl = ProductTemplate.objects.create(name="Tee", product_type="tee", printful_blueprint_id="71")
    listing = Listing.objects.create(design=Design.objects.create(title="Pillars"), template=tpl, product_type="tee",
                                     color="Black", price=Decimal("40"), status=status)
    ListingSize.objects.create(listing=listing, label="S", printful_catalog_variant_id="c1", printful_variant_id="old1")
    ListingSize.objects.create(listing=listing, label="M", price_override=Decimal("45"))
    return listing


class OrderRepositoryTests(TestCase):
    repo = DjangoOrderRepository()

    def place(self):
        listing = make_listing()
        size = listing.sizes.first()
        item = NewItem(listing.pk, size.pk, "Pillars", "tee", "Black", "S", 2, Decimal("40"), Decimal("11"))
        return self.repo.create_order("a@b.test", (item,), Decimal("80"))

    def test_a_placed_order_waits_for_payment_with_its_items_copied(self):
        order_id = self.place()
        view = self.repo.order(order_id)
        self.assertEqual((view.status, len(view.item_ids), view.fulfilments), (O.PENDING_PAYMENT, 1, ()))
        order = Order.objects.get(pk=order_id)
        self.assertEqual((order.items_total, order.grand_total, order.email), (Decimal("80"), Decimal("80"), "a@b.test"))
        item = order.items.get()
        self.assertEqual((item.design_title, item.size_label, item.quantity, item.unit_supplier_cost),
                         ("Pillars", "S", 2, Decimal("11")))

    def test_recording_a_payment_stores_the_customer_and_the_money(self):
        order_id = self.place()
        self.repo.record_payment(order_id, PaymentEvent(
            PaymentEventKind.PAID, str(order_id), "cs_1", "pi_1", email="buyer@b.test", name="Ada",
            address={"line1": "1 Main", "postal_code": "83110"}, total=Decimal("90"), tax=Decimal("5"),
            shipping=Decimal("5")))
        order = Order.objects.get(pk=order_id)
        self.assertEqual((order.status, order.stripe_session_id, order.stripe_payment_intent, order.name),
                         (O.PENDING_APPROVAL.value, "cs_1", "pi_1", "Ada"))
        self.assertEqual((order.grand_total, order.tax_total, order.shipping_total, order.items_total),
                         (Decimal("90"), Decimal("5"), Decimal("5"), Decimal("80")))
        self.assertEqual(self.repo.order(order_id).payment_ref, "pi_1")
        self.assertEqual(self.repo.order(order_id).recipient.address1, "1 Main")

    def test_an_unknown_order_is_a_lookup_error(self):
        with self.assertRaises(LookupError):
            self.repo.order(999)

    def test_fulfilments_are_found_by_the_suppliers_id_else_by_ours(self):
        order_id = self.place()
        fid = self.repo.add_fulfilment(order_id, "memory", (1,), problem_note="n")
        self.repo.update_fulfilment(fid, FulfilmentChange(status=F.SUBMITTED, supplier_order_id="S-1"))
        by_supplier = self.repo.find_fulfilment("S-1")
        self.assertEqual((by_supplier.id, by_supplier.status, by_supplier.problem_note), (fid, F.SUBMITTED, "n"))
        self.assertEqual(self.repo.find_fulfilment("", order_id, fid).id, fid)
        self.assertIsNone(self.repo.find_fulfilment("", order_id, fid + 1))
        self.assertIsNone(self.repo.find_fulfilment("", order_id + 1, fid))
        self.assertIsNone(self.repo.find_fulfilment("", None, None))
        self.assertIsNone(self.repo.find_fulfilment("nope"))

    def test_an_update_changes_only_what_it_names(self):
        order_id = self.place()
        fid = self.repo.add_fulfilment(order_id, "memory", ())
        self.repo.update_fulfilment(fid, FulfilmentChange(
            status=F.SHIPPED, tracking_number="T1", carrier="UPS", supplier_cost=Decimal("19.09"), problem_note=""))
        self.repo.update_fulfilment(fid, FulfilmentChange(tracking_url="https://t.test/1"))
        ful = Fulfillment.objects.get(pk=fid)
        self.assertEqual((ful.status, ful.tracking_number, ful.tracking_url, ful.carrier, ful.supplier_cost_actual),
                         ("shipped", "T1", "https://t.test/1", "UPS", Decimal("19.09")))

    def test_a_note_is_appended_never_replacing_the_curators(self):
        order_id = self.place()
        Order.objects.filter(pk=order_id).update(curator_note="first")
        self.repo.set_order_status(order_id, O.APPROVED, note="second")
        self.repo.set_order_status(order_id, O.SUBMITTED)
        order = Order.objects.get(pk=order_id)
        self.assertEqual((order.status, order.curator_note), ("submitted", "first\nsecond"))


class ListingRepositoryTests(TestCase):
    repo = DjangoListingRepository()

    def test_a_listing_is_read_as_a_plain_view(self):
        listing = make_listing()
        view = self.repo.listing(listing.pk)
        self.assertIsInstance(view, ListingView)
        self.assertEqual((view.slug, view.title, view.color, view.product_id, view.status, view.is_connected),
                         (listing.slug, "Pillars", "Black", "", "draft", False))
        self.assertEqual([(s.label, s.price, s.catalog_variant_id, s.variant_id) for s in view.sizes],
                         [("S", Decimal("40"), "c1", "old1"), ("M", Decimal("45"), "", "")])

    def test_an_unknown_listing_is_a_lookup_error(self):
        with self.assertRaises(LookupError):
            self.repo.listing(999)

    def test_variant_ids_clear_and_set_by_label(self):
        listing = make_listing()
        self.repo.clear_variant_ids(listing.pk)
        self.assertEqual([s.variant_id for s in self.repo.listing(listing.pk).sizes], ["", ""])
        self.repo.set_variant_ids(listing.pk, {"M": "new-M", "XXL": "ignored"})
        self.assertEqual([s.variant_id for s in self.repo.listing(listing.pk).sizes], ["", "new-M"])

    def test_the_product_and_previews_are_stored(self):
        listing = make_listing()
        self.repo.set_product(listing.pk, "477")
        self.repo.store_previews(listing.pk, (Preview("Black", "https://img.test/a.jpg"),))
        listing.refresh_from_db()
        self.assertEqual((listing.printful_product_id, listing.printful_preview),
                         ("477", [{"label": "Black", "url": "https://img.test/a.jpg"}]))
        self.assertIsNotNone(listing.printful_preview_checked)

    def test_marking_sent_sets_the_status_and_remembers_what_was_sent(self):
        listing = make_listing()
        self.repo.mark_sent(listing.pk, "hidden")
        listing.refresh_from_db()
        self.assertEqual((listing.status, listing.printful_sent_blueprint_id, listing.printful_sent_color,
                          listing.printful_sent_placement), ("hidden", "71", "Black", "front"))
        self.assertEqual(listing.printful_sent_prints, listing.print_signature())
