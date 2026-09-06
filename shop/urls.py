from django.urls import path

from . import views

app_name = "shop"

urlpatterns = [
    path("", views.shop_index, name="index"),
    path("cart/", views.cart_detail, name="cart_detail"),
    path("cart/add/<int:listing_id>/", views.cart_add, name="cart_add"),
    path("cart/update/", views.cart_update, name="cart_update"),
    path("cart/remove/", views.cart_remove, name="cart_remove"),
    path("overlay/close/", views.overlay_close, name="overlay_close"),
    path("shirts/<slug:slug>/", views.listing_detail, name="listing_detail"),
]
