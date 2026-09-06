from django.urls import path

from . import manage_views, views

app_name = "shop"

urlpatterns = [
    path("", views.shop_index, name="index"),

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
    path("webhooks/printful/", views.printful_webhook, name="printful_webhook"),

    # subscribers
    path("subscribe/", views.subscribe, name="subscribe"),
    path("unsubscribe/<str:token>/", views.unsubscribe, name="unsubscribe"),

    # orders
    path("order/<str:token>/", views.order_track, name="order_track"),

    # curator's order desk (staff)
    path("manage/", manage_views.order_queue, name="manage_queue"),
    path("manage/orders/<int:pk>/", manage_views.order_manage, name="manage_order"),
    path("manage/orders/<int:pk>/approve/", manage_views.order_approve, name="manage_order_approve"),
    path("manage/orders/<int:pk>/refund/", manage_views.order_refund, name="manage_order_refund"),
    path("manage/orders/<int:pk>/simulate/", manage_views.order_simulate, name="manage_order_simulate"),
    path("manage/fulfillments/<int:pk>/reprint/", manage_views.fulfillment_reprint, name="manage_fulfillment_reprint"),

    # catalogue
    path("overlay/close/", views.overlay_close, name="overlay_close"),
    path("shirts/<slug:slug>/", views.listing_detail, name="listing_detail"),
]
