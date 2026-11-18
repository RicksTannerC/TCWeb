"""The ordering context's collaborators, on the Django ORM: where orders live, how an order item becomes a supplier
order line, and how the customer is told. This is the one place that reads and writes the `shop` order tables
for the ordering use cases (docs/ARCHITECTURE.md: only persistence may import `shop`)."""

from shop.emails import send_order_status_update
from shop.orders import Fulfillment, Order, OrderItem
from shop.supplier_bridge import line_for, recipient_for
from tshirtbrand.core.ordering.api import FulfilmentStatus, FulfilmentView, OrderStatus, OrderView


def _fulfilment_view(ful):
    return FulfilmentView(
        id=ful.id, order_id=ful.order_id, supplier=ful.supplier, supplier_order_id=ful.partner_order_id,
        status=FulfilmentStatus(ful.status), problem_note=ful.problem_note,
        item_ids=tuple(ful.items.values_list("id", flat=True)),
    )


class DjangoOrderRepository:
    def order(self, order_id):
        try:
            order = Order.objects.get(pk=order_id)
        except Order.DoesNotExist as exc:
            raise LookupError(f"no order {order_id}") from exc
        return OrderView(
            id=order.id, status=OrderStatus(order.status), payment_ref=order.stripe_payment_intent or "",
            recipient=recipient_for(order),
            item_ids=tuple(order.items.values_list("id", flat=True)),
            fulfilments=tuple(_fulfilment_view(f) for f in order.fulfillments.order_by("id")),
        )

    def create_order(self, email, items, items_total):
        order = Order.objects.create(email=email, status=OrderStatus.PENDING_PAYMENT.value,
                                     items_total=items_total, grand_total=items_total)
        for i in items:
            OrderItem.objects.create(
                order=order, listing_id=i.listing_id, listing_size_id=i.size_id, design_title=i.name,
                product_type=i.product_type, color=i.color, size_label=i.size_label, quantity=i.quantity,
                unit_price=i.unit_price, unit_supplier_cost=i.unit_supplier_cost)
        return order.id

    def set_checkout_session(self, order_id, session_id):
        Order.objects.filter(pk=order_id).update(stripe_session_id=session_id)

    def record_payment(self, order_id, event):
        order = Order.objects.get(pk=order_id)
        order.stripe_session_id = event.session_id
        order.stripe_payment_intent = event.payment_ref
        order.email = event.email or order.email
        order.name = event.name or ""
        order.shipping_address = event.address or {}
        order.tax_total = event.tax
        order.shipping_total = event.shipping
        order.grand_total = event.total
        order.items_total = event.items_total
        order.status = OrderStatus.PENDING_APPROVAL.value
        order.save()

    def find_fulfilment(self, supplier_order_id, order_id=None, fulfilment_id=None):
        ful = None
        if supplier_order_id:
            ful = Fulfillment.objects.filter(partner_order_id=supplier_order_id).first()
        if ful is None and order_id is not None and fulfilment_id is not None:
            ful = Fulfillment.objects.filter(pk=fulfilment_id, order_id=order_id).first()
        return _fulfilment_view(ful) if ful else None

    def add_fulfilment(self, order_id, supplier, item_ids, problem_note=""):
        ful = Fulfillment.objects.create(order_id=order_id, supplier=supplier, status=Fulfillment.Status.PENDING,
                                         problem_note=problem_note)
        ful.items.set(item_ids)
        return ful.id

    def update_fulfilment(self, fulfilment_id, change):
        ful = Fulfillment.objects.get(pk=fulfilment_id)
        fields = {
            "status": change.status.value if change.status else None,
            "partner_order_id": change.supplier_order_id,
            "problem_note": change.problem_note,
            "tracking_number": change.tracking_number,
            "tracking_url": change.tracking_url,
            "carrier": change.carrier,
            "supplier_cost_actual": change.supplier_cost,
            "supplier_tax": change.supplier_tax,
        }
        for name, value in fields.items():
            if value is not None:
                setattr(ful, name, value)
        ful.save()

    def set_order_status(self, order_id, status, note=None):
        order = Order.objects.get(pk=order_id)
        order.status = status.value
        if note:
            order.curator_note = (order.curator_note + f"\n{note}").strip()
        order.save(update_fields=["status", "curator_note", "updated"])


class OrderItemLines:
    """Order items -> supplier order lines, from the listing the item was bought from."""

    def line_for(self, item_id):
        return line_for(OrderItem.objects.select_related("listing", "listing_size").get(pk=item_id))


class EmailNotifier:
    def order_status_changed(self, order_id):
        try:
            send_order_status_update(Order.objects.get(pk=order_id))
        except Exception:  # noqa: BLE001 - telling the customer is best effort
            pass
