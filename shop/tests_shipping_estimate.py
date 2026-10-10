"""The delivery estimate Stripe shows at checkout matches the Shipping & Returns page."""

from decimal import Decimal
from unittest import mock

from django.test import RequestFactory, TestCase, override_settings

from . import payments
from .models import Design, Listing, ListingSize, ProductTemplate
from .orders import Order, OrderItem


@override_settings(STRIPE_SECRET_KEY="sk_test_x", STRIPE_PUBLISHABLE_KEY="pk_test_x", TESTING=False)
class CheckoutDeliveryEstimateTests(TestCase):
    def test_stripe_is_told_7_to_9_calendar_days(self):
        tpl = ProductTemplate.objects.create(name="Tee", product_type="tee")
        listing = Listing.objects.create(design=Design.objects.create(title="W"), template=tpl, product_type="tee")
        size = ListingSize.objects.create(listing=listing, label="M")
        order = Order.objects.create()
        OrderItem.objects.create(order=order, listing=listing, listing_size=size, design_title="W",
                                 product_type="tee", size_label="M", quantity=1, unit_price=Decimal("40"))
        request = RequestFactory().post("/checkout/")
        with mock.patch("stripe.checkout.Session.create", return_value=mock.Mock(id="cs_x", url="https://x")) as create:
            payments.create_checkout_session(request, order)
        est = create.call_args.kwargs["shipping_options"][0]["shipping_rate_data"]["delivery_estimate"]
        self.assertEqual(est, {"minimum": {"unit": "day", "value": 7}, "maximum": {"unit": "day", "value": 9}})
