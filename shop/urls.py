from django.urls import path

from . import console_views as cv
from . import manage_views as mv
from . import two_factor
from . import views

app_name = "shop"

urlpatterns = [
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
    path("webhooks/printful/", views.printful_webhook, name="printful_webhook"),

    # subscribers + contact
    path("subscribe/", views.subscribe, name="subscribe"),
    path("unsubscribe/<str:token>/", views.unsubscribe, name="unsubscribe"),
    path("contact/", views.contact, name="contact"),

    # content pages
    path("pages/<slug:slug>/", views.page, name="page"),

    # order tracking
    path("order/<str:token>/", views.order_track, name="order_track"),

    # ---- the curator's console (staff) ----
    path("manage/2fa/", two_factor.verify, name="manage_2fa"),
    path("manage/", cv.dashboard, name="manage_dashboard"),

    path("manage/orders/", mv.order_queue, name="manage_queue"),
    path("manage/orders/<int:pk>/", mv.order_manage, name="manage_order"),
    path("manage/orders/<int:pk>/approve/", mv.order_approve, name="manage_order_approve"),
    path("manage/orders/<int:pk>/refund/", mv.order_refund, name="manage_order_refund"),
    path("manage/orders/<int:pk>/simulate/", mv.order_simulate, name="manage_order_simulate"),
    path("manage/fulfillments/<int:pk>/reprint/", mv.fulfillment_reprint, name="manage_fulfillment_reprint"),

    path("manage/listings/", cv.listings, name="manage_listings"),
    path("manage/listings/intake/", cv.listings_intake, name="manage_listings_intake"),
    path("manage/listings/<int:pk>/", cv.listing_edit, name="manage_listing_edit"),
    path("manage/listings/<int:pk>/printful/", cv.listing_send_to_printful, name="manage_listing_printful"),
    path("manage/listings/<int:pk>/status/", cv.listing_set_status, name="manage_listing_status"),
    path("manage/listings/<int:pk>/image/", cv.listing_add_image, name="manage_listing_add_image"),
    path("manage/listings/<int:pk>/mockups/", cv.listing_generate_mockups, name="manage_listing_mockups"),
    path("manage/images/<int:pk>/delete/", cv.image_delete, name="manage_image_delete"),

    path("manage/collections/", cv.collections, name="manage_collections"),
    path("manage/collections/create/", cv.collection_create, name="manage_collection_create"),
    path("manage/collections/<int:pk>/", cv.collection_edit, name="manage_collection_edit"),
    path("manage/collections/<int:pk>/toggle/", cv.collection_toggle, name="manage_collection_toggle"),

    path("manage/pricing/", cv.pricing, name="manage_pricing"),
    path("manage/pricing/update/", cv.pricing_update, name="manage_pricing_update"),

    path("manage/books/", cv.books, name="manage_books"),
    path("manage/books/overhead/add/", cv.overhead_add, name="manage_overhead_add"),
    path("manage/books/overhead/<int:pk>/delete/", cv.overhead_delete, name="manage_overhead_delete"),

    path("manage/messages/", cv.inbox, name="manage_inbox"),
    path("manage/messages/<int:pk>/toggle/", cv.message_toggle, name="manage_message_toggle"),

    path("manage/pages/", cv.pages, name="manage_pages"),
    path("manage/pages/new/", cv.page_edit, name="manage_page_new"),
    path("manage/pages/<int:pk>/", cv.page_edit, name="manage_page_edit"),

    # catalogue
    path("overlay/close/", views.overlay_close, name="overlay_close"),
    path("shirts/<slug:slug>/", views.listing_detail, name="listing_detail"),
]
