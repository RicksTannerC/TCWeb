"""
Order pipeline entry points for the console and the supplier webhook: approve -> submit to the print supplier ->
status/tracking updates -> refunds & reprints. The curator's one-click approval is the gate; nothing reaches a print
partner without it.

The rules and the sequencing live in tshirtbrand.core.ordering (the OrderDesk use cases); bootstrap.get_order_desk()
wires them to the ORM, the current supplier and payment gateway, and the customer email. These functions take and
return the Django order objects the views and templates work with, refreshed after the use case has run.
"""

from __future__ import annotations

from django.utils import timezone

from tshirtbrand.bootstrap import get_order_desk

from .orders import Fulfillment, Order


def approve_and_submit(order: Order, *, note: str = "") -> Order:
    """Curator approved the order: create the fulfilment and send it to the supplier."""
    get_order_desk().approve_and_submit(order.pk, note=note)
    order.refresh_from_db()
    return order


def handle_supplier_payload(payload: dict) -> Order | None:
    """A supplier's raw webhook body: let the supplier's adapter say what it means, then apply it."""
    order_id = get_order_desk().handle_supplier_payload(payload)
    return Order.objects.filter(pk=order_id).first() if order_id else None


def apply_partner_event(event_type: str, data: dict) -> Order | None:
    return handle_supplier_payload({"type": event_type, "data": data})


def apply_event(event) -> Order | None:
    order_id = get_order_desk().apply_event(event)
    return Order.objects.filter(pk=order_id).first() if order_id else None


def cancel_partner_order(ful: Fulfillment) -> None:
    """Cancel one fulfilment's order at the supplier. Raises the supplier port's error if the supplier won't, typically
    because production has already started."""
    get_order_desk().cancel_fulfilment(ful.pk, ful.order_id)
    ful.refresh_from_db()


def cancel_supplier_orders(order: Order) -> tuple[list[str], list[str]]:
    """Cancel every cancellable fulfilment. Returns (cancelled, failures) as display strings."""
    return get_order_desk().cancel_supplier_orders(order.pk)


def refund_order(order: Order, *, reason: str = "") -> tuple[Order, list[str], list[str]]:
    """Refund the payment, then cancel the print order(s) at the supplier. Raises PaymentError, with nothing
    changed, if the payment provider refuses. Returns (order, cancelled, cancel_failures)."""
    cancelled, failures = get_order_desk().refund_order(order.pk, reason=reason)
    order.refresh_from_db()
    return order, cancelled, failures


def reprint(fulfillment: Fulfillment, *, reason: str = "") -> Fulfillment:
    """Create and submit a replacement for `fulfillment`. Raises the supplier port's error, with nothing created, if the
    order lines can't be built; if the supplier itself refuses, the new fulfilment is kept in Problem."""
    new_id = get_order_desk().reprint(fulfillment.pk, fulfillment.order_id, reason=reason)
    fulfillment.refresh_from_db()
    return Fulfillment.objects.get(pk=new_id)


def simulate_advance(order: Order) -> Order:
    """Push every fulfilment one step forward (the simulated supplier only)."""
    get_order_desk().simulate_advance(order.pk, stamp=int(timezone.now().timestamp()) % 100000)
    order.refresh_from_db()
    return order
