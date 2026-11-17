"""
Order pipeline services: approve -> submit to the print supplier -> status/tracking
updates -> refunds & reprints. The curator's one-click approval is the gate;
nothing reaches a print partner without it.

Talks to the supplier only through the neutral port (tshirtbrand.core.fulfilment): this module builds
neutral requests from orders and applies neutral results and events to them. What a particular supplier's
API looks like is that supplier's adapter's business.
"""

from __future__ import annotations

from django.utils import timezone

from tshirtbrand.bootstrap import get_supplier
from tshirtbrand.core.fulfilment.api import EventKind, OrderRequest, SupplierError

from . import payments
from .emails import send_order_status_update
from .orders import Fulfillment, Order, OrderStatus
from .supplier_bridge import line_for, recipient_for


# ---- hold rules -----------------------------------------------------
# Every order holds for approval today. This hook is where per-supplier /
# over-$X / new-customer rules land when auto-submit is switched on.

def should_hold(order: Order) -> bool:
    return True


# ---- approve & submit ---------------------------------------------

def approve_and_submit(order: Order, *, note: str = "") -> Order:
    """Curator approved the order — create fulfillment(s) and send to the supplier."""
    if order.status != OrderStatus.PENDING_APPROVAL:
        raise ValueError(f"Order {order.reference} is not awaiting approval.")

    supplier = get_supplier()
    items = list(order.items.all())

    # One fulfilment per supplier. Launch is single-supplier, so one group.
    by_supplier: dict[str, list] = {supplier.name.lower(): items}

    for key, group in by_supplier.items():
        ful = Fulfillment.objects.create(order=order, supplier=key, status=Fulfillment.Status.PENDING)
        ful.items.set(group)

        try:
            submitted = supplier.submit_order(OrderRequest(
                external_id=f"{order.reference}-{ful.id}",
                recipient=recipient_for(order),
                lines=tuple(line_for(it) for it in group),
            ))
        except SupplierError as exc:
            ful.status = Fulfillment.Status.PROBLEM
            ful.problem_note = f"{supplier.name} rejected the order: {exc}"
            ful.save(update_fields=["status", "problem_note", "updated"])
            order.status = OrderStatus.APPROVED  # approved but not cleanly submitted
            order.curator_note = (order.curator_note + f"\nSubmit failed: {exc}").strip()
            order.save(update_fields=["status", "curator_note", "updated"])
            return order

        ful.partner_order_id = submitted.supplier_order_id
        ful.status = Fulfillment.Status.SUBMITTED
        record_supplier_costs(ful, submitted)
        ful.save(update_fields=["partner_order_id", "status", "supplier_cost_actual", "supplier_tax", "updated"])

    order.status = OrderStatus.SUBMITTED
    if note:
        order.curator_note = (order.curator_note + f"\n{note}").strip()
    order.save(update_fields=["status", "curator_note", "updated"])
    return order


def record_supplier_costs(ful: Fulfillment, submitted) -> None:
    """Store what the supplier says it will charge for this order, from the reply to 'submit order' (so
    no extra call). Does nothing when the supplier didn't report a cost."""
    if submitted.cost_total is None:
        return
    ful.supplier_cost_actual = submitted.cost_total
    ful.supplier_tax = submitted.cost_tax


# ---- supplier webhook -> our state -------------------------------

def handle_supplier_payload(payload: dict) -> Order | None:
    """A supplier's raw webhook body: let the supplier's adapter say what it means, then apply it."""
    event = get_supplier().parse_event(payload)
    return apply_event(event) if event else None


def apply_partner_event(event_type: str, data: dict) -> Order | None:
    return handle_supplier_payload({"type": event_type, "data": data})


def apply_event(event) -> Order | None:
    ful = (
        Fulfillment.objects.filter(partner_order_id=event.supplier_order_id).first()
        or Fulfillment.objects.filter(order__reference=event.external_id.split("-")[0]).first()
    )
    if not ful:
        return None
    order = ful.order
    if ful.status == Fulfillment.Status.CANCELLED:
        return order  # we cancelled it ourselves; the supplier's echo isn't a problem

    kind = event.kind
    if kind == EventKind.SHIPPED:
        ful.status = Fulfillment.Status.SHIPPED
        ful.tracking_number = event.tracking_number
        ful.tracking_url = event.tracking_url
        ful.carrier = event.carrier
        ful.save()
    elif kind == EventKind.IN_PRODUCTION:
        ful.status = Fulfillment.Status.IN_PRODUCTION
        ful.save(update_fields=["status", "updated"])
    elif kind in (EventKind.RETURNED, EventKind.FAILED, EventKind.ON_HOLD, EventKind.CANCELED):
        ful.status = Fulfillment.Status.PROBLEM
        ful.problem_note = event.reason
        ful.save()

    _rollup(order)
    return order


def _rollup(order: Order) -> None:
    S = Fulfillment.Status
    statuses = list(order.fulfillments.exclude(status=S.CANCELLED).values_list("status", flat=True))
    if not statuses:
        return

    if any(s == S.PROBLEM for s in statuses):
        # keep the order status; the problem shows on the fulfilment
        new = order.status
    elif all(s == S.DELIVERED for s in statuses):
        new = OrderStatus.DELIVERED
    elif all(s in (S.SHIPPED, S.DELIVERED) for s in statuses):
        new = OrderStatus.SHIPPED
    elif any(s in (S.IN_PRODUCTION, S.SHIPPED, S.DELIVERED) for s in statuses):
        new = OrderStatus.IN_PRODUCTION
    else:
        new = OrderStatus.SUBMITTED

    if new != order.status:
        order.status = new
        order.save(update_fields=["status", "updated"])
        if new in (OrderStatus.IN_PRODUCTION, OrderStatus.SHIPPED, OrderStatus.DELIVERED):
            try:
                send_order_status_update(order)
            except Exception:  # noqa: BLE001
                pass


# ---- refunds & reprints -----------------------------------------

def cancel_partner_order(ful: Fulfillment) -> None:
    """Cancel one fulfilment's order at the supplier (a real call when the supplier is configured).
    Raises SupplierError if the supplier won't — typically because production has already started."""
    supplier = get_supplier()
    supplier.cancel_order(ful.partner_order_id)
    ful.status = Fulfillment.Status.CANCELLED
    ful.problem_note = f"Cancelled at {supplier.name}."
    ful.save(update_fields=["status", "problem_note", "updated"])


def cancel_supplier_orders(order: Order) -> tuple[list[str], list[str]]:
    """Cancel every cancellable fulfilment. Returns (cancelled, failures) as
    display strings; a failure never stops the others."""
    cancelled, failures = [], []
    for ful in order.fulfillments.all():
        if not ful.can_cancel:
            continue
        try:
            cancel_partner_order(ful)
            cancelled.append(ful.partner_order_id)
        except SupplierError as exc:
            failures.append(f"{ful.partner_order_id} ({exc})")
    return cancelled, failures


def refund_order(order: Order, *, reason: str = "") -> tuple[Order, list[str], list[str]]:
    """Refund the payment, then cancel the print order(s) at Printful.

    Refund goes first: if Stripe refuses, nothing else has changed. Returns
    (order, cancelled, cancel_failures) so the caller can tell the curator
    about any Printful order that still has to be cancelled by hand."""
    if order.status == OrderStatus.REFUNDED:
        return order, [], []
    payments.refund(order, reason=reason)
    order.status = OrderStatus.REFUNDED
    order.curator_note = (order.curator_note + f"\nRefunded: {reason}").strip()
    order.save(update_fields=["status", "curator_note", "updated"])
    cancelled, failures = cancel_supplier_orders(order)
    return order, cancelled, failures


def reprint(fulfillment: Fulfillment, *, reason: str = "") -> Fulfillment:
    """Create and submit a replacement for `fulfillment`.

    Raises SupplierError, with nothing created, if the order lines can't be built
    (e.g. a size with no supplier variant). If the supplier itself refuses the order,
    the new fulfilment is kept in the Problem state with its reason."""
    supplier = get_supplier()
    order = fulfillment.order
    items = list(fulfillment.items.all())
    lines = tuple(line_for(it) for it in items)  # may raise: do it before creating anything

    new = Fulfillment.objects.create(
        order=order, supplier=fulfillment.supplier, status=Fulfillment.Status.PENDING,
        problem_note=f"Reprint of fulfilment #{fulfillment.id}: {reason}",
    )
    new.items.set(items)
    try:
        submitted = supplier.submit_order(OrderRequest(
            external_id=f"{order.reference}-{new.id}-reprint", recipient=recipient_for(order), lines=lines))
        new.partner_order_id = submitted.supplier_order_id
        new.status = Fulfillment.Status.SUBMITTED
        record_supplier_costs(new, submitted)
    except SupplierError as exc:
        new.status = Fulfillment.Status.PROBLEM
        new.problem_note += f" — submit failed: {exc}"
    new.save()
    if new.status == Fulfillment.Status.SUBMITTED:
        # A failed attempt that has now been replaced must stop counting as a problem: the
        # status roll-up refuses to advance an order while any fulfilment is in Problem, so a
        # left-behind failure would pin the order (and its shipped/delivered emails) forever.
        if fulfillment.status == Fulfillment.Status.PROBLEM:
            fulfillment.status = Fulfillment.Status.CANCELLED
            fulfillment.problem_note = (fulfillment.problem_note.rstrip()
                                        + f" | Replaced by reprint #{new.id}.")
            fulfillment.save(update_fields=["status", "problem_note", "updated"])
        # Retrying an order whose first submit failed ("approved", not yet at Printful):
        # once a retry goes through, the order is submitted.
        if order.status == OrderStatus.APPROVED:
            order.status = OrderStatus.SUBMITTED
            order.save(update_fields=["status", "updated"])
    return new


# ---- dev simulation --------------------------------------------

_NEXT = {
    Fulfillment.Status.SUBMITTED: Fulfillment.Status.IN_PRODUCTION,
    Fulfillment.Status.IN_PRODUCTION: Fulfillment.Status.SHIPPED,
    Fulfillment.Status.SHIPPED: Fulfillment.Status.DELIVERED,
}


def simulate_advance(order: Order) -> Order:
    """Push every fulfilment one step forward (mock Printful only)."""
    for ful in order.fulfillments.all():
        nxt = _NEXT.get(ful.status)
        if not nxt:
            continue
        ful.status = nxt
        if nxt == Fulfillment.Status.SHIPPED:
            ful.tracking_number = f"MOCK{ful.id}{int(timezone.now().timestamp()) % 100000}"
            ful.tracking_url = f"https://example.invalid/track/{ful.tracking_number}"
            ful.carrier = "MockPost"
        ful.save()
    _rollup(order)
    return order
