"""
The curator's order desk — the seed of the Milestone 4 console. Staff-only
(reuses the Django admin login). The approval queue, the approval card, and
the refund / reprint / status actions.
"""

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import fulfillment, printful
from .orders import Fulfillment, Order, OrderStatus

QUEUE_ORDER = [
    OrderStatus.PENDING_APPROVAL,
    OrderStatus.APPROVED,
    OrderStatus.SUBMITTED,
    OrderStatus.IN_PRODUCTION,
    OrderStatus.SHIPPED,
    OrderStatus.DELIVERED,
    OrderStatus.REFUNDED,
    OrderStatus.CANCELLED,
]


@staff_member_required
def order_queue(request):
    orders = (
        Order.objects.exclude(status=OrderStatus.PENDING_PAYMENT)
        .prefetch_related("items", "fulfillments")
    )
    buckets = {s: [] for s in QUEUE_ORDER}
    for o in orders:
        buckets.setdefault(o.status, []).append(o)
    groups = [(OrderStatus(s).label, buckets[s]) for s in QUEUE_ORDER if buckets.get(s)]
    awaiting = len(buckets.get(OrderStatus.PENDING_APPROVAL, []))
    problems = Fulfillment.objects.filter(status=Fulfillment.Status.PROBLEM).count()
    return render(request, "shop/manage/queue.html", {
        "groups": groups, "awaiting": awaiting, "problems": problems,
    })


@staff_member_required
def order_manage(request, pk):
    order = get_object_or_404(
        Order.objects.prefetch_related("items__listing__design", "fulfillments__items"), pk=pk
    )
    return render(request, "shop/manage/order.html", {
        "order": order,
        "address_ok": _address_looks_complete(order),
        "is_mock": getattr(printful.get_client(), "is_mock", False),
    })


def _address_looks_complete(order):
    a = order.shipping_address or {}
    required = ["line1", "city", "state", "postal_code"]
    return all(a.get(k) for k in required) and a.get("country", "US") == "US"


@staff_member_required
@require_POST
def order_approve(request, pk):
    order = get_object_or_404(Order, pk=pk)
    try:
        fulfillment.approve_and_submit(order, note=request.POST.get("note", ""))
        messages.success(request, f"{order.reference} approved and submitted to Printful.")
    except (ValueError, printful.PrintfulError) as exc:
        messages.error(request, str(exc))
    return redirect("shop:manage_order", pk=pk)


@staff_member_required
@require_POST
def order_refund(request, pk):
    order = get_object_or_404(Order, pk=pk)
    fulfillment.refund_order(order, reason=request.POST.get("reason", "curator refund"))
    messages.success(request, f"{order.reference} refunded.")
    return redirect("shop:manage_order", pk=pk)


@staff_member_required
@require_POST
def fulfillment_reprint(request, pk):
    ful = get_object_or_404(Fulfillment, pk=pk)
    new = fulfillment.reprint(ful, reason=request.POST.get("reason", "damage / print error"))
    messages.success(request, f"Reprint created (fulfilment #{new.id}).")
    return redirect("shop:manage_order", pk=ful.order_id)


@staff_member_required
@require_POST
def order_simulate(request, pk):
    order = get_object_or_404(Order, pk=pk)
    fulfillment.simulate_advance(order)
    messages.info(request, f"{order.reference} advanced (mock Printful).")
    return redirect("shop:manage_order", pk=pk)
