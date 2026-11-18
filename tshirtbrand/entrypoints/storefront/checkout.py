"""The storefront: checkout, the return page, and the local stand-in for the payment page."""

import logging

from django.conf import settings
from django.contrib import messages
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from shop import payments
from shop.cart import Cart
from shop.emails import send_order_confirmation
from shop.orders import Order, OrderStatus
from tshirtbrand.core.payments.api import PaymentError

logger = logging.getLogger(__name__)


def checkout_open():
    """Whether a visitor can actually place an order right now: real Stripe
    keys, or the DEBUG-only simulated checkout that stands in for them."""
    return payments.checkout_is_live() or settings.DEBUG


@require_POST
def checkout(request):
    cart = Cart(request)
    if len(cart) == 0:
        messages.info(request, "Your cart is empty.")
        return redirect("shop:cart_detail")

    if not checkout_open():
        # No Order is created here: payment isn't wired up yet, so there is
        # nothing for a pending_payment order to lead to. Nothing is charged
        # and nothing is queued for fulfillment.
        messages.info(
            request,
            "Checkout isn't open yet — we're still setting up payments. "
            "Check back soon.",
        )
        return redirect("shop:cart_detail")

    order = payments.create_order_from_cart(cart)
    request.session["pending_order_id"] = order.id

    if payments.checkout_is_live():
        try:
            session = payments.create_checkout_session(request, order)
        except PaymentError:
            # Configured but broken (bad/mismatched keys, a provider outage, ...):
            # never leave the customer on a raw error page, and never leave
            # an order stranded with nothing that will ever move it forward.
            logger.exception("Checkout session creation failed for order %s", order.pk)
            order.delete()
            request.session.pop("pending_order_id", None)
            messages.error(
                request,
                "Checkout hit a snag on our end and your card was not charged. "
                "Please try again in a moment, or use the contact form if it keeps happening.",
            )
            return redirect("shop:cart_detail")
        return redirect(session.url, permanent=False)

    return redirect("shop:checkout_dev")


def checkout_success(request):
    ref = request.GET.get("ref", "")
    order = None
    if ref:
        order = Order.objects.filter(stripe_session_id=ref).first()
    if not order:
        oid = request.session.get("pending_order_id")
        order = Order.objects.filter(id=oid).first() if oid else None

    Cart(request).clear()
    request.session.pop("pending_order_id", None)
    return render(request, "shop/checkout_success.html", {"order": order})


def checkout_dev(request):
    if not settings.DEBUG:
        return HttpResponseBadRequest()
    order = Order.objects.filter(id=request.session.get("pending_order_id")).first()
    if not order:
        return redirect("shop:cart_detail")
    return render(request, "shop/checkout_dev.html", {"order": order})


@require_POST
def checkout_simulate(request):
    if not settings.DEBUG:
        return HttpResponseBadRequest()
    order = Order.objects.filter(id=request.session.get("pending_order_id")).first()
    if not order or order.status != OrderStatus.PENDING_PAYMENT:
        return redirect("shop:cart_detail")

    order.email = request.POST.get("email", "dev@example.com")
    order.name = request.POST.get("name", "Dev Tester")
    order.status = OrderStatus.PENDING_APPROVAL
    order.save()
    try:
        send_order_confirmation(order)
    except Exception:  # noqa: BLE001 — dev convenience
        pass
    return redirect(reverse("shop:checkout_success") + f"?ref={order.stripe_session_id or ''}")
