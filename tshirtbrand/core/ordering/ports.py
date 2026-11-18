"""What the ordering context needs from the outside, besides a supplier and a payment gateway: somewhere to keep
orders, a way to turn an order item into something the supplier can make, and a way to tell the customer."""

from typing import Protocol

from tshirtbrand.core.fulfilment.api import OrderLine
from tshirtbrand.core.payments.api import PaymentEvent

from .model import FulfilmentChange, FulfilmentView, NewItem, OrderStatus, OrderView


class OrderRepository(Protocol):
    def order(self, order_id: int) -> OrderView:
        """The order as it is right now. Raises LookupError when there is none."""

    def create_order(self, email: str, items: tuple[NewItem, ...], items_total) -> int:
        """A new order awaiting payment, with its items; returns its id."""

    def set_checkout_session(self, order_id: int, session_id: str) -> None:
        """Remember the provider's checkout session, so the return link can find the order."""

    def record_payment(self, order_id: int, event: PaymentEvent) -> None:
        """Store what the customer paid and who they are, and move the order to awaiting approval."""

    def find_fulfilment(self, supplier_order_id: str, order_id: int | None = None,
                        fulfilment_id: int | None = None) -> FulfilmentView | None:
        """The fulfilment the supplier's own order id points at (when it has one), else the one of order
        `order_id` with id `fulfilment_id`, else None."""

    def add_fulfilment(self, order_id: int, supplier: str, item_ids: tuple, problem_note: str = "") -> int:
        """A new pending fulfilment covering `item_ids`; returns its id."""

    def update_fulfilment(self, fulfilment_id: int, change: FulfilmentChange) -> None: ...

    def set_order_status(self, order_id: int, status: OrderStatus, note: str | None = None) -> None:
        """Set the status; a note is appended to the curator's notes, never replacing them."""


class LineSource(Protocol):
    def line_for(self, item_id: int) -> OrderLine:
        """What to ask the supplier to make for one order item. Raises SupplierError, in words fit to show the
        curator, when the item can't be built (e.g. a size the supplier doesn't have)."""


class Notifier(Protocol):
    def order_status_changed(self, order_id: int) -> None:
        """Tell the customer. Must not raise."""
