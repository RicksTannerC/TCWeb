"""Stripe hosted Checkout behind the PaymentGateway port.

Everything Stripe-shaped lives here: the line-item and shipping-rate structures, the `checkout.session.completed`
event, signature verification and the refund call. With no secret key the gateway is `simulated`: it never calls
Stripe (the shop then uses its local stand-in checkout), but it can still verify a signed webhook, which is a
local calculation."""

from decimal import Decimal

import stripe

from tshirtbrand.core.payments.api import (
    SESSION_ID_TOKEN, CheckoutRequest, CheckoutSession, PaymentError, PaymentEvent, PaymentEventKind, RefundResult,
)

COMPLETED = "checkout.session.completed"


def _cents(amount):
    return int(Decimal(amount) * 100)


def _money(cents):
    return Decimal(cents or 0) / 100


class StripeGateway:
    name = "Stripe"

    def __init__(self, secret_key="", webhook_secret=""):
        self._key = secret_key or ""
        self._webhook_secret = webhook_secret or ""
        self.simulated = not self._key

    # ---- checkout

    def create_checkout(self, request: CheckoutRequest):
        if self.simulated:
            raise PaymentError("Stripe isn't configured.")
        params = {
            "api_key": self._key,
            "mode": "payment",
            "line_items": [
                {
                    "quantity": line.quantity,
                    "price_data": {
                        "currency": request.currency,
                        "unit_amount": _cents(line.unit_price),
                        "tax_behavior": "exclusive",
                        "product_data": {"name": line.name, "description": line.description},
                    },
                }
                for line in request.lines
            ],
            "client_reference_id": request.order_ref,
            "metadata": {"order_id": request.order_ref},
            "customer_email": request.email or None,
            "success_url": request.success_url.replace(SESSION_ID_TOKEN, "{CHECKOUT_SESSION_ID}"),
            "cancel_url": request.cancel_url,
            "shipping_address_collection": {"allowed_countries": list(request.countries)},
            "billing_address_collection": "auto",
            "shipping_options": [
                {
                    "shipping_rate_data": {
                        "type": "fixed_amount",
                        "fixed_amount": {"amount": _cents(request.shipping.amount), "currency": request.currency},
                        "display_name": request.shipping.label,
                        "delivery_estimate": {
                            "minimum": {"unit": "day", "value": request.shipping.min_days},
                            "maximum": {"unit": "day", "value": request.shipping.max_days},
                        },
                    }
                }
            ],
        }
        if request.collect_tax:
            params["automatic_tax"] = {"enabled": True}
        try:
            session = stripe.checkout.Session.create(**params)
        except stripe.StripeError as exc:
            raise PaymentError(str(exc)) from exc
        return CheckoutSession(id=str(session.id), url=str(session.url))

    # ---- events

    def parse_event(self, payload, signature):
        try:
            event = stripe.Webhook.construct_event(payload, signature, self._webhook_secret)
        except Exception as exc:  # noqa: BLE001 - bad signature, malformed body, no secret set: all untrustworthy
            raise PaymentError("webhook could not be verified") from exc
        if event["type"] != COMPLETED:
            return None
        session = event["data"]["object"]
        # a verified event hands us a StripeObject, which (unlike a dict) has no .get()
        if hasattr(session, "to_dict"):
            session = session.to_dict()
        order_ref = session.get("client_reference_id") or (session.get("metadata") or {}).get("order_id")
        if not order_ref:
            return None
        details = session.get("customer_details") or {}
        totals = session.get("total_details") or {}
        return PaymentEvent(
            kind=PaymentEventKind.PAID,
            order_ref=str(order_ref),
            session_id=str(session.get("id") or ""),
            payment_ref=str(session.get("payment_intent") or ""),
            email=details.get("email") or "",
            name=details.get("name") or "",
            address=(session.get("shipping_details") or details).get("address") or {},
            total=_money(session.get("amount_total")),
            tax=_money(totals.get("amount_tax")),
            shipping=_money(totals.get("amount_shipping")),
        )

    # ---- refunds

    def refund(self, payment_ref, amount=None):
        if self.simulated or not payment_ref:
            return RefundResult(amount=amount, simulated=True)
        params = {"api_key": self._key, "payment_intent": payment_ref, "reason": "requested_by_customer"}
        if amount is not None:
            params["amount"] = _cents(amount)
        try:
            stripe.Refund.create(**params)
        except stripe.StripeError as exc:
            raise PaymentError(str(exc)) from exc
        return RefundResult(amount=amount)
