"""
Stripe hosted Checkout.

An Order is created in ``pending_payment`` before the redirect; the webhook
promotes it to ``pending_approval`` once Stripe confirms the payment. This
keeps the line items authoritative on our side rather than reconstructing
them from Stripe.
"""

from decimal import Decimal

import stripe
from django.conf import settings
from django.urls import reverse

from .orders import Order, OrderItem, OrderStatus


def _configure():
    stripe.api_key = settings.STRIPE_SECRET_KEY


def stripe_ready():
    # settings.TESTING is a hard guarantee, independent of the environment:
    # see shop.printful.configured() for the matching guard and why it exists.
    if settings.TESTING:
        return False
    return bool(settings.STRIPE_SECRET_KEY)


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
    _configure()

    line_items = [
        {
            "quantity": item.quantity,
            "price_data": {
                "currency": "usd",
                "unit_amount": int(item.unit_price * 100),
                "tax_behavior": "exclusive",
                "product_data": {
                    "name": item.design_title,
                    "description": ", ".join(
                        p for p in [item.product_type.title(), item.color, item.size_label] if p
                    ) or "Item",
                },
            },
        }
        for item in order.items.all()
    ]

    params = {
        "mode": "payment",
        "line_items": line_items,
        "client_reference_id": str(order.id),
        "metadata": {"order_id": str(order.id)},
        "customer_email": order.email or None,
        "success_url": _abs(request, "shop:checkout_success") + "?ref={CHECKOUT_SESSION_ID}",
        "cancel_url": _abs(request, "shop:cart_detail"),
        "shipping_address_collection": {"allowed_countries": ["US"]},
        "billing_address_collection": "auto",
        # hybrid shipping: free to the customer, absorbed into pricing
        "shipping_options": [
            {
                "shipping_rate_data": {
                    "type": "fixed_amount",
                    "fixed_amount": {"amount": 0, "currency": "usd"},
                    "display_name": "Standard shipping",
                    "delivery_estimate": {
                        "minimum": {"unit": "business_day", "value": 3},
                        "maximum": {"unit": "business_day", "value": 8},
                    },
                }
            }
        ],
    }
    if settings.STRIPE_TAX_ENABLED:
        params["automatic_tax"] = {"enabled": True}

    session = stripe.checkout.Session.create(**params)
    order.stripe_session_id = session.id
    order.save(update_fields=["stripe_session_id"])
    return session


def fulfill_from_session(session):
    """
    Idempotently promote the order for a completed checkout session.
    Called from the webhook. Returns (order, created_now).
    """
    order_id = (session.get("client_reference_id")
                or session.get("metadata", {}).get("order_id"))
    if not order_id:
        return None, False

    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        return None, False

    if order.status != OrderStatus.PENDING_PAYMENT:
        return order, False  # already handled

    details = session.get("customer_details") or {}
    total = Decimal(session.get("amount_total", 0)) / 100
    tax = Decimal((session.get("total_details") or {}).get("amount_tax", 0)) / 100
    shipping = Decimal((session.get("total_details") or {}).get("amount_shipping", 0)) / 100

    order.stripe_session_id = session["id"]
    order.stripe_payment_intent = session.get("payment_intent", "") or ""
    order.email = details.get("email") or order.email
    order.name = details.get("name") or ""
    order.shipping_address = (session.get("shipping_details") or details).get("address", {}) or {}
    order.tax_total = tax
    order.shipping_total = shipping
    order.grand_total = total
    order.items_total = total - tax - shipping
    order.status = OrderStatus.PENDING_APPROVAL
    order.save()
    return order, True


def construct_event(payload, sig_header):
    return stripe.Webhook.construct_event(
        payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
    )


def refund(order, amount=None, reason=""):
    """Refund an order's payment. No-op (mock) when Stripe isn't configured."""
    if not stripe_ready() or not order.stripe_payment_intent:
        return {"mock": True, "amount": amount or order.grand_total}
    _configure()
    kwargs = {"payment_intent": order.stripe_payment_intent, "reason": "requested_by_customer"}
    if amount is not None:
        kwargs["amount"] = int(amount * 100)
    return stripe.Refund.create(**kwargs)
