"""The public URL table: nothing the outside world has bookmarked, linked or registered moved."""

from django.test import SimpleTestCase
from django.urls import reverse

from tshirtbrand.entrypoints.storefront.urls import storefront_patterns
from tshirtbrand.entrypoints.webhooks.urls import webhook_patterns

PUBLIC_PATHS = {
    "landing": "/", "index": "/shop/", "cart_detail": "/cart/", "cart_drawer": "/cart/drawer/",
    "cart_update": "/cart/update/", "cart_remove": "/cart/remove/", "checkout": "/checkout/",
    "checkout_success": "/checkout/success/", "checkout_dev": "/checkout/dev/", "checkout_simulate": "/checkout/dev/pay/",
    "subscribe": "/subscribe/", "contact": "/contact/", "overlay_close": "/overlay/close/",
}


class StorefrontUrlTests(SimpleTestCase):
    def test_the_public_paths_are_where_they_were(self):
        for name, path in PUBLIC_PATHS.items():
            self.assertEqual(reverse(f"shop:{name}"), path, name)

    def test_paths_with_arguments_are_where_they_were(self):
        self.assertEqual(reverse("shop:cart_add", args=[3]), "/cart/add/3/")
        self.assertEqual(reverse("shop:listing_detail", args=["pillars"]), "/shirts/pillars/")
        self.assertEqual(reverse("shop:page", args=["terms"]), "/pages/terms/")
        self.assertEqual(reverse("shop:order_track", args=["tok"]), "/order/tok/")
        self.assertEqual(reverse("shop:unsubscribe", args=["tok"]), "/unsubscribe/tok/")

    def test_what_the_providers_call_has_not_moved(self):
        # these are registered in the Stripe dashboard and at the print supplier: changing them breaks live orders
        self.assertEqual(reverse("shop:stripe_webhook"), "/webhooks/stripe/")
        self.assertEqual(reverse("shop:printful_webhook", args=["tok"]), "/webhooks/printful/tok/")
        self.assertEqual(reverse("shop:printful_artwork", args=[5, "tok"]), "/printful/artwork/5/tok/")

    def test_every_view_is_served_from_an_entry_point_module(self):
        for p in (*storefront_patterns, *webhook_patterns):
            self.assertTrue(p.callback.__module__.startswith("tshirtbrand.entrypoints."), f"{p.name}: {p.callback.__module__}")
