"""Checkout is a placeholder until Stripe is configured: no order, no charge."""

from decimal import Decimal

from django.test import Client, TestCase, override_settings

from .models import Design, Listing, ListingSize, ProductTemplate, ProductType, Status
from .orders import Order


def _live_tee():
    tpl = ProductTemplate.objects.create(
        name="Tee", product_type=ProductType.TEE, base_cost=Decimal("11"), shipping_est=Decimal("5"))
    design = Design.objects.create(title="Pillars")
    listing = Listing.objects.create(design=design, template=tpl, product_type="tee",
                                      status=Status.LIVE, price=Decimal("40"))
    size = ListingSize.objects.create(listing=listing, label="M")
    return listing, size


@override_settings(STRIPE_SECRET_KEY="", STRIPE_PUBLISHABLE_KEY="")
class CheckoutPlaceholderTests(TestCase):
    def cart_with_item(self):
        c = Client()
        listing, size = _live_tee()
        c.post(f"/cart/add/{listing.id}/", {"size": size.id})
        return c

    @override_settings(DEBUG=False)
    def test_checkout_refuses_without_stripe_in_production(self):
        c = self.cart_with_item()
        r = c.post("/checkout/")
        self.assertRedirects(r, "/cart/", fetch_redirect_response=False)
        self.assertEqual(Order.objects.count(), 0)

    @override_settings(DEBUG=False)
    def test_no_orphan_order_is_created(self):
        c = self.cart_with_item()
        for _ in range(3):
            c.post("/checkout/")
        self.assertEqual(Order.objects.count(), 0)

    @override_settings(DEBUG=False)
    def test_cart_still_holds_the_item_afterwards(self):
        c = self.cart_with_item()
        c.post("/checkout/")
        self.assertContains(c.get("/cart/"), "Pillars")

    def test_empty_cart_still_shows_its_own_message_first(self):
        r = Client().post("/checkout/")
        self.assertRedirects(r, "/cart/", fetch_redirect_response=False)
        self.assertEqual(Order.objects.count(), 0)

    @override_settings(DEBUG=True)
    def test_debug_dev_checkout_still_works_for_local_testing(self):
        c = self.cart_with_item()
        r = c.post("/checkout/")
        self.assertRedirects(r, "/checkout/dev/", fetch_redirect_response=False)
        self.assertEqual(Order.objects.count(), 1)

    @override_settings(DEBUG=False)
    def test_cart_page_shows_a_disabled_checkout_with_a_notice(self):
        c = self.cart_with_item()
        html = c.get("/cart/").content.decode()
        self.assertIn("disabled", html)
        self.assertIn("isn't open yet", html)
        self.assertNotIn('action="/checkout/"', html)

    @override_settings(DEBUG=True)
    def test_cart_page_shows_a_real_checkout_button_in_dev(self):
        c = self.cart_with_item()
        self.assertIn('action="/checkout/"', c.get("/cart/").content.decode())

    # TESTING=False: simulate production for this one assertion, overriding the
    # hard test-suite guard (settings.TESTING) that otherwise always keeps
    # stripe_ready() False — see shop.payments.stripe_ready().
    @override_settings(STRIPE_SECRET_KEY="sk_test_x", STRIPE_PUBLISHABLE_KEY="pk_test_x", DEBUG=False, TESTING=False)
    def test_cart_page_shows_real_checkout_once_stripe_keys_are_set(self):
        c = self.cart_with_item()
        self.assertIn('action="/checkout/"', c.get("/cart/").content.decode())
