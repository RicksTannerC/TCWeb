"""A supplier event finds our fulfilment by the supplier's own order id, or failing that by the id we gave the order
when we submitted it (TTS-00012-5). The second route used to ask the database for a field that doesn't exist and
crash; it is also what makes an event with no supplier id match nothing instead of the wrong fulfilment."""

from django.test import TestCase

from tshirtbrand.core.fulfilment.api import EventKind, SupplierEvent
from tshirtbrand.core.ordering.api import external_id

from . import fulfillment
from .orders import Fulfillment, Order, OrderStatus


class EventMatchingTests(TestCase):
    def setUp(self):
        self.order = Order.objects.create(status=OrderStatus.SUBMITTED, email="a@b.test")
        self.ful = Fulfillment.objects.create(order=self.order, partner_order_id="", status=Fulfillment.Status.SUBMITTED)

    def event(self, **kw):
        return SupplierEvent(EventKind.IN_PRODUCTION, **kw)

    def test_the_id_we_gave_the_supplier_finds_the_fulfilment(self):
        got = fulfillment.apply_event(self.event(external_id=external_id(self.order.pk, self.ful.pk)))
        self.assertEqual(got, self.order)
        self.ful.refresh_from_db()
        self.assertEqual(self.ful.status, Fulfillment.Status.IN_PRODUCTION)

    def test_a_reprints_id_finds_its_fulfilment_too(self):
        reprint = Fulfillment.objects.create(order=self.order, status=Fulfillment.Status.SUBMITTED)
        fulfillment.apply_event(self.event(external_id=external_id(self.order.pk, reprint.pk, reprint=True)))
        reprint.refresh_from_db()
        self.ful.refresh_from_db()
        self.assertEqual((reprint.status, self.ful.status),
                         (Fulfillment.Status.IN_PRODUCTION, Fulfillment.Status.SUBMITTED))

    def test_an_event_naming_nothing_of_ours_is_ignored_not_a_crash(self):
        for ev in (self.event(), self.event(external_id="ORD-9"), self.event(external_id="TTS-00099-77"),
                   self.event(supplier_order_id="nope")):
            self.assertIsNone(fulfillment.apply_event(ev))
        self.ful.refresh_from_db()
        self.assertEqual(self.ful.status, Fulfillment.Status.SUBMITTED)   # a blank supplier id matched no one

    def test_an_id_for_another_order_does_not_match(self):
        other = Order.objects.create(status=OrderStatus.SUBMITTED, email="c@d.test")
        self.assertIsNone(fulfillment.apply_event(self.event(external_id=external_id(other.pk, self.ful.pk))))
