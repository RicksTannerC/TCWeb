"""The webhook URLs: what the payment provider and the print supplier call, and the signed artwork links the
supplier fetches. Included by shop/urls.py; the names live in the `shop` namespace."""

from django.urls import path

from . import payments, suppliers

webhook_patterns = [
    path("webhooks/stripe/", payments.stripe_webhook, name="stripe_webhook"),
    path("webhooks/printful/<str:token>/", suppliers.printful_webhook, name="printful_webhook"),

    # Signed, expiring link so Printful's servers can fetch a private design
    # original; see shop/printful_delivery.py.
    path("printful/artwork/<int:pk>/<str:token>/", suppliers.printful_artwork, name="printful_artwork"),
]
