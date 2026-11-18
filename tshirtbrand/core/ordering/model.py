"""Orders and their fulfilments, and the rules that move them along. Pure: plain values and decisions, no
database, no supplier, no payment provider."""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from tshirtbrand.core.fulfilment.api import EventKind, Recipient, SupplierEvent


class OrderStatus(str, Enum):
    PENDING_PAYMENT = "pending_payment"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"            # approved, but the supplier didn't take it cleanly
    SUBMITTED = "submitted"
    IN_PRODUCTION = "in_production"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class FulfilmentStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    IN_PRODUCTION = "in_production"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    PROBLEM = "problem"
    CANCELLED = "cancelled"


# ------------------------------------------------------------------ what the use cases read and write

@dataclass(frozen=True)
class FulfilmentView:
    id: int
    order_id: int
    supplier: str
    supplier_order_id: str
    status: FulfilmentStatus
    problem_note: str
    item_ids: tuple

    @property
    def can_cancel(self):
        """Still sitting at the supplier and not yet shipped."""
        return bool(self.supplier_order_id) and self.status in (
            FulfilmentStatus.SUBMITTED, FulfilmentStatus.IN_PRODUCTION, FulfilmentStatus.PROBLEM)


@dataclass(frozen=True)
class OrderView:
    id: int
    status: OrderStatus
    payment_ref: str
    recipient: Recipient
    item_ids: tuple
    fulfilments: tuple     # FulfilmentView, oldest first

    @property
    def reference(self):
        return reference(self.id)


@dataclass(frozen=True)
class FulfilmentChange:
    """Fields to set on a fulfilment; None means leave it as it is."""

    status: FulfilmentStatus | None = None
    supplier_order_id: str | None = None
    problem_note: str | None = None
    tracking_number: str | None = None
    tracking_url: str | None = None
    carrier: str | None = None
    supplier_cost: Decimal | None = None
    supplier_tax: Decimal | None = None


# ------------------------------------------------------------------ naming

def reference(order_id):
    """What the customer and curator call an order: TTS-00012."""
    return f"TTS-{order_id:05d}"


def external_id(order_id, fulfilment_id, reprint=False):
    """The id we give the supplier for one fulfilment, so its events can be matched back: TTS-00012-5[-reprint]."""
    return f"{reference(order_id)}-{fulfilment_id}" + ("-reprint" if reprint else "")


def parse_external_id(text):
    """(order_id, fulfilment_id) from an id made by `external_id`, or None for anything else."""
    parts = str(text or "").split("-")
    try:
        if len(parts) >= 3 and parts[0] == "TTS":
            return int(parts[1]), int(parts[2])
    except ValueError:
        pass
    return None


# ------------------------------------------------------------------ rules

def should_hold(order):
    """Every order waits for the curator's approval today. This is where per-supplier / over-$X / new-customer
    rules land when auto-submit is switched on."""
    return True


def address_looks_complete(address):
    """Enough of a US address to ship to."""
    a = address or {}
    return all(a.get(k) for k in ("line1", "city", "state", "postal_code")) and a.get("country", "US") == "US"


def rollup(current, fulfilment_statuses):
    """The order status that follows from its fulfilments' (cancelled ones are ignored).

    Any problem leaves the order where it is: the problem shows on the fulfilment, and the order does not
    advance until it is dealt with."""
    statuses = [s for s in fulfilment_statuses if s != FulfilmentStatus.CANCELLED]
    if not statuses:
        return current
    F = FulfilmentStatus
    if any(s == F.PROBLEM for s in statuses):
        return current
    if all(s == F.DELIVERED for s in statuses):
        return OrderStatus.DELIVERED
    if all(s in (F.SHIPPED, F.DELIVERED) for s in statuses):
        return OrderStatus.SHIPPED
    if any(s in (F.IN_PRODUCTION, F.SHIPPED, F.DELIVERED) for s in statuses):
        return OrderStatus.IN_PRODUCTION
    return OrderStatus.SUBMITTED


def change_for_event(event: SupplierEvent):
    """What a supplier event does to a fulfilment, or None when it changes nothing."""
    F = FulfilmentStatus
    if event.kind == EventKind.SHIPPED:
        return FulfilmentChange(status=F.SHIPPED, tracking_number=event.tracking_number,
                                tracking_url=event.tracking_url, carrier=event.carrier)
    if event.kind == EventKind.IN_PRODUCTION:
        return FulfilmentChange(status=F.IN_PRODUCTION)
    if event.kind in (EventKind.RETURNED, EventKind.FAILED, EventKind.ON_HOLD, EventKind.CANCELED):
        return FulfilmentChange(status=F.PROBLEM, problem_note=event.reason)
    return None


NEXT_STEP = {
    FulfilmentStatus.SUBMITTED: FulfilmentStatus.IN_PRODUCTION,
    FulfilmentStatus.IN_PRODUCTION: FulfilmentStatus.SHIPPED,
    FulfilmentStatus.SHIPPED: FulfilmentStatus.DELIVERED,
}

# the order statuses worth telling the customer about
NOTIFY_ON = (OrderStatus.IN_PRODUCTION, OrderStatus.SHIPPED, OrderStatus.DELIVERED)
