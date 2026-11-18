"""
Paying for an order: the shop side of checkout.

An Order is created in ``pending_payment`` before the redirect; the payment webhook promotes it to
``pending_approval`` once the provider confirms the payment. This keeps the line items authoritative on our side
rather than reconstructing them from the provider.

Talking to the provider is the gateway's job (tshirtbrand.core.payments + the adapter that bootstrap.get_gateway()
picks); this module reads and writes orders and turns them into the neutral requests the gateway takes.
"""

from django.conf import settings
from django.urls import reverse

from tshirtbrand.bootstrap import get_gateway
from tshirtbrand.core.payments.api import PaymentError, checkout_request, success_url_with_session  # noqa: F401

from .orders import Order, OrderItem, OrderStatus


def checkout_is_live():
    """Whether checkout can really take money (a gateway with credentials, not the local stand-in)."""
    return not get_gateway().simulated


def _abs(request, viewname, **kwargs):
    return request.build_absolute_uri(reverse(viewname, kwargs=kwargs or None))


def create_order_from_cart(cart, email=""):
    """Create a pending_payment Order + items from the session cart."""
    order = Order.objects.create(
        email=email or "",
        status=OrderStatus.PENDING_PAYMENT,
        items_total=cart.get_total(),
        grand_total=cart.get_total(),
    )
    for row in cart:
        listing, size = row["listing"], row["size"]
        OrderItem.objects.create(
            order=order,
            listing=listing,
            listing_size=size,
            design_title=listing.design.title,
            product_type=listing.product_type,
            color=listing.color,
            size_label=size.label,
            quantity=row["quantity"],
            unit_price=row["unit_price"],
            unit_supplier_cost=listing.base_cost,
        )
    return order


def create_checkout_session(request, order):
    """Ask the gateway for a hosted checkout for `order` and remember its session id. Raises PaymentError."""
    items = [(i.design_title, i.product_type, i.color, i.size_label, i.quantity, i.unit_price)
             for i in order.items.all()]
    session = get_gateway().create_checkout(checkout_request(
        order.id, items, email=order.email,
        success_url=success_url_with_session(_abs(request, "shop:checkout_success")),
        cancel_url=_abs(request, "shop:cart_detail"),
        collect_tax=settings.STRIPE_TAX_ENABLED,
    ))
    order.stripe_session_id = session.id
    order.save(update_fields=["stripe_session_id"])
    return session


def parse_event(payload, signature):
    """The verified payment event in a webhook, or None for one we don't act on. Raises PaymentError."""
    return get_gateway().parse_event(payload, signature)


def fulfill_from_event(event):
    """
    Idempotently promote the order for a confirmed payment. Called from the webhook.
    Returns (order, created_now).
    """
    try:
        order = Order.objects.get(id=event.order_ref)
    except (Order.DoesNotExist, ValueError):
        return None, False

    if order.status != OrderStatus.PENDING_PAYMENT:
        return order, False  # already handled

    order.stripe_session_id = event.session_id
    order.stripe_payment_intent = event.payment_ref
    order.email = event.email or order.email
    order.name = event.name or ""
    order.shipping_address = event.address or {}
    order.tax_total = event.tax
    order.shipping_total = event.shipping
    order.grand_total = event.total
    order.items_total = event.items_total
    order.status = OrderStatus.PENDING_APPROVAL
    order.save()
    return order, True
