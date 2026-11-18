"""What the shop does with an order once it is paid: approve it and send it to the supplier, follow the supplier's
news, cancel, refund, reprint. Every collaborator is handed in, so none of this knows about a database, a
particular supplier or a particular payment provider."""

from tshirtbrand.core.fulfilment.api import OrderRequest, SupplierError

from .model import (
    NEXT_STEP, NOTIFY_ON, FulfilmentChange, FulfilmentStatus, OrderStatus, change_for_event, external_id, items_total,
    parse_external_id, rollup,
)
from .ports import LineSource, Notifier, OrderRepository

F = FulfilmentStatus
O = OrderStatus  # noqa: E741


def submitted_change(submitted):
    """What to record once the supplier has taken an order: its id for it, and what it says it will charge (from
    the reply to 'submit order', so no extra call); no cost when it didn't report one."""
    return FulfilmentChange(
        status=F.SUBMITTED, supplier_order_id=submitted.supplier_order_id,
        supplier_cost=submitted.cost_total,
        supplier_tax=submitted.cost_tax if submitted.cost_total is not None else None)


class OrderDesk:
    def __init__(self, orders: OrderRepository, supplier, lines: LineSource, notifier: Notifier, gateway):
        self.orders = orders
        self.supplier = supplier
        self.lines = lines
        self.notifier = notifier
        self.gateway = gateway

    # ---- place & pay

    def place_order(self, email, items):
        """Record a cart as an order awaiting payment; returns its id."""
        items = tuple(items)
        return self.orders.create_order(email or "", items, items_total(items))

    def remember_checkout_session(self, order_id, session_id):
        self.orders.set_checkout_session(order_id, session_id)

    def confirm_payment(self, event):
        """Idempotently promote the order a confirmed payment is for (the provider may tell us twice).
        Returns (order_id, newly_confirmed); (None, False) when the event names no order of ours."""
        try:
            order = self.orders.order(int(event.order_ref))
        except (LookupError, ValueError):
            return None, False
        if order.status != OrderStatus.PENDING_PAYMENT:
            return order.id, False  # already handled
        self.orders.record_payment(order.id, event)
        return order.id, True

    # ---- approve & submit

    def approve_and_submit(self, order_id, note=""):
        """The curator approved the order: create the fulfilment and send it to the supplier. A supplier that
        refuses leaves a fulfilment in Problem and the order Approved (not cleanly submitted), with the reason."""
        order = self.orders.order(order_id)
        if order.status != O.PENDING_APPROVAL:
            raise ValueError(f"Order {order.reference} is not awaiting approval.")

        # One fulfilment per supplier. Launch is single-supplier, so one group.
        ful_id = self.orders.add_fulfilment(order_id, self.supplier.name.lower(), order.item_ids)
        try:
            submitted = self.supplier.submit_order(OrderRequest(
                external_id=external_id(order_id, ful_id),
                recipient=order.recipient,
                lines=tuple(self.lines.line_for(i) for i in order.item_ids),
            ))
        except SupplierError as exc:
            self.orders.update_fulfilment(ful_id, FulfilmentChange(
                status=F.PROBLEM, problem_note=f"{self.supplier.name} rejected the order: {exc}"))
            self.orders.set_order_status(order_id, O.APPROVED, note=f"Submit failed: {exc}")
            return

        self.orders.update_fulfilment(ful_id, submitted_change(submitted))
        self.orders.set_order_status(order_id, O.SUBMITTED, note=note or None)

    # ---- supplier news

    def handle_supplier_payload(self, payload):
        """A supplier's raw webhook body: its adapter says what it means, then it is applied."""
        event = self.supplier.parse_event(payload)
        return self.apply_event(event) if event else None

    def apply_event(self, event):
        """Apply one supplier event. Returns the order id it belongs to, or None if it matches nothing of ours."""
        parsed = parse_external_id(event.external_id)
        ful = self.orders.find_fulfilment(
            event.supplier_order_id, order_id=parsed[0] if parsed else None, fulfilment_id=parsed[1] if parsed else None)
        if not ful:
            return None
        if ful.status == F.CANCELLED:
            return ful.order_id  # we cancelled it ourselves; the supplier's echo isn't a problem
        change = change_for_event(event)
        if change:
            self.orders.update_fulfilment(ful.id, change)
        self._rollup(ful.order_id)
        return ful.order_id

    def _rollup(self, order_id):
        order = self.orders.order(order_id)
        new = rollup(order.status, [f.status for f in order.fulfilments])
        if new != order.status:
            self.orders.set_order_status(order_id, new)
            if new in NOTIFY_ON:
                try:
                    self.notifier.order_status_changed(order_id)
                except Exception:  # noqa: BLE001 - a failed email never holds up the order
                    pass

    # ---- cancel, refund, reprint

    def cancel_fulfilment(self, fulfilment_id, order_id):
        """Cancel one fulfilment's order at the supplier. Raises SupplierError if it won't, typically because
        production has already started."""
        ful = next(f for f in self.orders.order(order_id).fulfilments if f.id == fulfilment_id)
        self.supplier.cancel_order(ful.supplier_order_id)
        self.orders.update_fulfilment(fulfilment_id, FulfilmentChange(
            status=F.CANCELLED, problem_note=f"Cancelled at {self.supplier.name}."))

    def cancel_supplier_orders(self, order_id):
        """Cancel every cancellable fulfilment. Returns (cancelled, failures) as display strings; a failure
        never stops the others."""
        cancelled, failures = [], []
        for ful in self.orders.order(order_id).fulfilments:
            if not ful.can_cancel:
                continue
            try:
                self.cancel_fulfilment(ful.id, order_id)
                cancelled.append(ful.supplier_order_id)
            except SupplierError as exc:
                failures.append(f"{ful.supplier_order_id} ({exc})")
        return cancelled, failures

    def refund_order(self, order_id, reason=""):
        """Refund the payment, then cancel the print order(s) at the supplier.

        The refund goes first: if the payment provider refuses (PaymentError), nothing else has changed.
        Returns (cancelled, cancel_failures) so the caller can tell the curator about any supplier order that
        still has to be cancelled by hand."""
        order = self.orders.order(order_id)
        if order.status == O.REFUNDED:
            return [], []
        self.gateway.refund(order.payment_ref)
        self.orders.set_order_status(order_id, O.REFUNDED, note=f"Refunded: {reason}")
        return self.cancel_supplier_orders(order_id)

    def reprint(self, fulfilment_id, order_id, reason=""):
        """Create and submit a replacement for a fulfilment; returns the new fulfilment's id.

        Raises SupplierError, with nothing created, if the order lines can't be built (e.g. a size with no
        supplier variant). If the supplier itself refuses the order, the new fulfilment is kept in the Problem
        state with its reason."""
        order = self.orders.order(order_id)
        old = next(f for f in order.fulfilments if f.id == fulfilment_id)
        lines = tuple(self.lines.line_for(i) for i in old.item_ids)  # may raise: do it before creating anything

        new_id = self.orders.add_fulfilment(
            order_id, old.supplier, old.item_ids, problem_note=f"Reprint of fulfilment #{old.id}: {reason}")
        try:
            submitted = self.supplier.submit_order(OrderRequest(
                external_id=external_id(order_id, new_id, reprint=True), recipient=order.recipient, lines=lines))
        except SupplierError as exc:
            note = next(f for f in self.orders.order(order_id).fulfilments if f.id == new_id).problem_note
            self.orders.update_fulfilment(new_id, FulfilmentChange(
                status=F.PROBLEM, problem_note=f"{note} — submit failed: {exc}"))
            return new_id

        self.orders.update_fulfilment(new_id, submitted_change(submitted))
        # A failed attempt that has now been replaced must stop counting as a problem: the status roll-up
        # refuses to advance an order while any fulfilment is in Problem, so a left-behind failure would pin
        # the order (and its shipped/delivered emails) forever.
        if old.status == F.PROBLEM:
            self.orders.update_fulfilment(old.id, FulfilmentChange(
                status=F.CANCELLED, problem_note=old.problem_note.rstrip() + f" | Replaced by reprint #{new_id}."))
        # Retrying an order whose first submit failed ("approved", not yet at the supplier): once a retry goes
        # through, the order is submitted.
        if order.status == O.APPROVED:
            self.orders.set_order_status(order_id, O.SUBMITTED)
        return new_id

    # ---- stand-in supplier only

    def simulate_advance(self, order_id, stamp):
        """Push every fulfilment one step forward (the simulated supplier only). `stamp` makes the fake
        tracking numbers unique."""
        for ful in self.orders.order(order_id).fulfilments:
            nxt = NEXT_STEP.get(ful.status)
            if not nxt:
                continue
            change = FulfilmentChange(status=nxt)
            if nxt == F.SHIPPED:
                number = f"MOCK{ful.id}{stamp}"
                change = FulfilmentChange(status=nxt, tracking_number=number,
                                          tracking_url=f"https://example.invalid/track/{number}", carrier="MockPost")
            self.orders.update_fulfilment(ful.id, change)
        self._rollup(order_id)
