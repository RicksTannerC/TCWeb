"""The payments context on its own: the checkout request the business builds and how a payment event adds up."""

from decimal import Decimal

from django.test import SimpleTestCase

from . import api


class CheckoutRequestTests(SimpleTestCase):
    def build(self, *items, **over):
        kw = dict(email="a@b.test", success_url="https://x/ok?ref={session_id}", cancel_url="https://x/cart/")
        kw.update(over)
        return api.checkout_request(7, items, **kw)

    def test_each_line_is_described_in_the_same_words_for_every_gateway(self):
        req = self.build(("Pillars", "tee", "Black", "M", 2, Decimal("40")), ("Sticker", "sticker", "", "", 1, Decimal("4")))
        self.assertEqual([line.description for line in req.lines], ["Tee, Black, M", "Sticker"])
        self.assertEqual((req.lines[0].quantity, req.lines[0].unit_price), (2, Decimal("40")))

    def test_an_item_with_nothing_to_say_is_still_described(self):
        self.assertEqual(self.build(("X", "", "", "", 1, Decimal("1"))).lines[0].description, "Item")

    def test_the_order_ref_is_text_and_shipping_is_the_promised_free_standard(self):
        req = self.build(("X", "tee", "", "M", 1, Decimal("1")))
        self.assertEqual(req.order_ref, "7")
        self.assertEqual((req.shipping.amount, req.shipping.min_days, req.shipping.max_days), (0, 10, 14))
        self.assertEqual(req.countries, ("US",))
        self.assertFalse(req.collect_tax)
        self.assertTrue(self.build(("X", "tee", "", "M", 1, Decimal("1")), collect_tax=True).collect_tax)

    def test_no_email_is_an_empty_string_not_none(self):
        self.assertEqual(self.build(("X", "tee", "", "M", 1, Decimal("1")), email=None).email, "")

    def test_the_return_link_carries_the_session_token(self):
        self.assertEqual(api.success_url_with_session("https://x/ok"), "https://x/ok?ref=" + api.SESSION_ID_TOKEN)


class PaymentEventTests(SimpleTestCase):
    def test_items_total_is_what_is_left_after_tax_and_shipping(self):
        event = api.PaymentEvent(api.PaymentEventKind.PAID, "1", "s", "p", total=Decimal("90"), tax=Decimal("5"),
                                 shipping=Decimal("5"))
        self.assertEqual(event.items_total, Decimal("80"))
