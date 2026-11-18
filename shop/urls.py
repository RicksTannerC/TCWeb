from django.urls import include, path

from tshirtbrand.entrypoints.console.urls import console_patterns

from . import views

app_name = "shop"

public_patterns = [
    path("", views.landing, name="landing"),
    path("shop/", views.shop_index, name="index"),

    # cart
    path("cart/", views.cart_detail, name="cart_detail"),
    path("cart/drawer/", views.cart_drawer, name="cart_drawer"),
    path("cart/add/<int:listing_id>/", views.cart_add, name="cart_add"),
    path("cart/update/", views.cart_update, name="cart_update"),
    path("cart/remove/", views.cart_remove, name="cart_remove"),

    # checkout
    path("checkout/", views.checkout, name="checkout"),
    path("checkout/success/", views.checkout_success, name="checkout_success"),
    path("checkout/dev/", views.checkout_dev, name="checkout_dev"),
    path("checkout/dev/pay/", views.checkout_simulate, name="checkout_simulate"),
    path("webhooks/stripe/", views.stripe_webhook, name="stripe_webhook"),
    path("webhooks/printful/<str:token>/", views.printful_webhook, name="printful_webhook"),

    # Signed, expiring link so Printful's servers can fetch a private design
    # original; see shop/printful_delivery.py.
    path("printful/artwork/<int:pk>/<str:token>/", views.printful_artwork, name="printful_artwork"),

    # subscribers + contact
    path("subscribe/", views.subscribe, name="subscribe"),
    path("unsubscribe/<str:token>/", views.unsubscribe, name="unsubscribe"),
    path("contact/", views.contact, name="contact"),

    # content pages
    path("pages/<slug:slug>/", views.page, name="page"),

    # order tracking
    path("order/<str:token>/", views.order_track, name="order_track"),

    # catalogue
    path("overlay/close/", views.overlay_close, name="overlay_close"),
    path("shirts/<slug:slug>/", views.listing_detail, name="listing_detail"),
]

urlpatterns = public_patterns + [path("manage/", include(console_patterns))]
