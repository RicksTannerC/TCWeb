"""
Order pipeline services: approve -> submit to Printful -> status/tracking
updates -> refunds & reprints. The curator's one-click approval is the gate;
nothing reaches a print partner without it.
"""

from __future__ import annotations

from django.utils import timezone

from . import payments, printful
from .emails import send_order_status_update
from .orders import Fulfillment, Order, OrderStatus


# ---- hold rules -----------------------------------------------------
# Every order holds for approval today. This hook is where per-supplier /
# over-$X / new-customer rules land when auto-submit is switched on.

def should_hold(order: Order) -> bool:
    return True


# ---- approve & submit ---------------------------------------------

def approve_and_submit(order: Order, *, note: str = "") -> Order:
    """Curator approved the order — create fulfillment(s) and send to Printful."""
    if order.status != OrderStatus.PENDING_APPROVAL:
        raise ValueError(f"Order {order.reference} is not awaiting approval.")

    client = printful.get_client()
    items = list(order.items.all())

    # One fulfilment per supplier. Launch is Printful-only, so one group.
    by_supplier: dict[str, list] = {}
    for it in items:
        supplier = (it.listing.template.printful_provider_id or "printful") if it.listing else "printful"
        by_supplier.setdefault("printful", []).append(it)

    for supplier, group in by_supplier.items():
        ful = Fulfillment.objects.create(order=order, supplier=supplier, status=Fulfillment.Status.PENDING)
        ful.items.set(group)

        payload = {
            "external_id": f"{order.reference}-{ful.id}",
            "recipient": _recipient(order),
            "items": [_line(it) for it in group],
        }
        try:
            result = client.create_order(payload, confirm=True)
        except printful.PrintfulError as exc:
            ful.status = Fulfillment.Status.PROBLEM
            ful.problem_note = f"Printful rejected the order: {exc}"
            ful.save(update_fields=["status", "problem_note", "updated"])
            order.status = OrderStatus.APPROVED  # approved but not cleanly submitted
            order.curator_note = (order.curator_note + f"\nSubmit failed: {exc}").strip()
            order.save(update_fields=["status", "curator_note", "updated"])
            return order

        ful.partner_order_id = str(result.get("id", ""))
        ful.status = Fulfillment.Status.SUBMITTED
        ful.save(update_fields=["partner_order_id", "status", "updated"])

    order.status = OrderStatus.SUBMITTED
    if note:
        order.curator_note = (order.curator_note + f"\n{note}").strip()
    order.save(update_fields=["status", "curator_note", "updated"])
    return order


def _recipient(order: Order) -> dict:
    a = order.shipping_address or {}
    return {
        "name": order.name,
        "email": order.email,
        "address1": a.get("line1", ""),
        "address2": a.get("line2", ""),
        "city": a.get("city", ""),
        "state_code": a.get("state", ""),
        "country_code": a.get("country", "US"),
        "zip": a.get("postal_code", ""),
    }


def _line(item) -> dict:
    listing = item.listing
    url = listing.design.print_file_url if listing else None
    return {
        "quantity": item.quantity,
        "sync_variant_id": (listing.printful_product_id or None) if listing else None,
        "name": item.design_title,
        "retail_price": str(item.unit_price),
        "files": [{"url": url, **listing.print_file_payload()}] if url else [],
    }


# ---- Printful webhook -> our state -------------------------------

_SHIP_FIELDS = ("tracking_number", "tracking_url", "carrier")


def apply_partner_event(event_type: str, data: dict) -> Order | None:
    ext = (data.get("order") or data).get("external_id", "")
    partner_id = str((data.get("order") or data).get("id", ""))

    ful = (
        Fulfillment.objects.filter(partner_order_id=partner_id).first()
        or Fulfillment.objects.filter(order__reference=ext.split("-")[0]).first()
    )
    if not ful:
        return None
    order = ful.order

    if event_type == "package_shipped":
        shipment = data.get("shipment", {})
        ful.status = Fulfillment.Status.SHIPPED
        ful.tracking_number = shipment.get("tracking_number", "")
        ful.tracking_url = shipment.get("tracking_url", "")
        ful.carrier = shipment.get("carrier", "")
        ful.save()
    elif event_type in ("order_updated",) and (data.get("order") or {}).get("status") == "inprocess":
        ful.status = Fulfillment.Status.IN_PRODUCTION
        ful.save(update_fields=["status", "updated"])
    elif event_type == "package_returned":
        ful.status = Fulfillment.Status.PROBLEM
        ful.problem_note = "Package returned to sender."
        ful.save()
    elif event_type in ("order_failed", "order_put_hold"):
        ful.status = Fulfillment.Status.PROBLEM
        ful.problem_note = data.get("reason", "Printful placed the order on hold.")
        ful.save()
    elif event_type == "order_canceled":
        ful.status = Fulfillment.Status.PROBLEM
        ful.problem_note = "Printful canceled the order."
        ful.save()

    _rollup(order)
    return order


def _rollup(order: Order) -> None:
    S = Fulfillment.Status
    statuses = list(order.fulfillments.values_list("status", flat=True))
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

def refund_order(order: Order, *, reason: str = "") -> Order:
    payments.refund(order, reason=reason)
    order.status = OrderStatus.REFUNDED
    order.curator_note = (order.curator_note + f"\nRefunded: {reason}").strip()
    order.save(update_fields=["status", "curator_note", "updated"])
    return order


def reprint(fulfillment: Fulfillment, *, reason: str = "") -> Fulfillment:
    client = printful.get_client()
    order = fulfillment.order
    new = Fulfillment.objects.create(
        order=order, supplier=fulfillment.supplier, status=Fulfillment.Status.PENDING,
        problem_note=f"Reprint of fulfilment #{fulfillment.id}: {reason}",
    )
    new.items.set(fulfillment.items.all())
    payload = {
        "external_id": f"{order.reference}-{new.id}-reprint",
        "recipient": _recipient(order),
        "items": [_line(it) for it in fulfillment.items.all()],
    }
    try:
        result = client.create_order(payload, confirm=True)
        new.partner_order_id = str(result.get("id", ""))
        new.status = Fulfillment.Status.SUBMITTED
    except printful.PrintfulError as exc:
        new.status = Fulfillment.Status.PROBLEM
        new.problem_note += f" — submit failed: {exc}"
    new.save()
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
