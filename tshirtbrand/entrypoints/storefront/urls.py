"""The storefront's URLs (the public shop). Included by shop/urls.py; the names live in the `shop` namespace."""

from django.urls import path

from . import cart, catalogue, checkout, customers, pages

storefront_patterns = [
    path("", pages.landing, name="landing"),
    path("shop/", catalogue.shop_index, name="index"),

    # cart
    path("cart/", cart.cart_detail, name="cart_detail"),
    path("cart/drawer/", cart.cart_drawer, name="cart_drawer"),
    path("cart/add/<int:listing_id>/", cart.cart_add, name="cart_add"),
    path("cart/update/", cart.cart_update, name="cart_update"),
    path("cart/remove/", cart.cart_remove, name="cart_remove"),

    # checkout
    path("checkout/", checkout.checkout, name="checkout"),
    path("checkout/success/", checkout.checkout_success, name="checkout_success"),
    path("checkout/dev/", checkout.checkout_dev, name="checkout_dev"),
    path("checkout/dev/pay/", checkout.checkout_simulate, name="checkout_simulate"),

    # subscribers + contact
    path("subscribe/", customers.subscribe, name="subscribe"),
    path("unsubscribe/<str:token>/", customers.unsubscribe, name="unsubscribe"),
    path("contact/", customers.contact, name="contact"),

    # content pages
    path("pages/<slug:slug>/", pages.page, name="page"),

    # order tracking
    path("order/<str:token>/", customers.order_track, name="order_track"),

    # catalogue
    path("overlay/close/", catalogue.overlay_close, name="overlay_close"),
    path("shirts/<slug:slug>/", catalogue.listing_detail, name="listing_detail"),
]
