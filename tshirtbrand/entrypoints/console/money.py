"""The curator's console: the pricing workspace and the books."""

from decimal import Decimal

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Sum
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from shop.console import OverheadEntry
from shop.models import Listing, ProductType, Status
from shop.orders import Order, OrderStatus
from tshirtbrand.core.catalogue import api as catalogue


# ------------------------------------------------------------------ pricing

def _pricing_rows():
    return (
        Listing.objects.select_related("design")
        .exclude(status=Status.DRAFT)
        .order_by("product_type", "design__title")
    )


@staff_member_required
def pricing(request):
    """Old standalone URL: pricing now lives on the merged Money page."""
    return redirect(reverse("shop:manage_money") + "#pricing")


@staff_member_required
@require_POST
def pricing_update(request):
    for key, value in request.POST.items():
        if not key.startswith("price_"):
            continue
        try:
            listing = Listing.objects.get(pk=key.split("_", 1)[1])
        except (Listing.DoesNotExist, ValueError):
            continue
        v = value.strip()
        if v:
            listing.price = Decimal(v)
            listing.save(update_fields=["price", "updated"])
        comp = request.POST.get(f"comp_{listing.pk}", "").strip()
        listing.competitor_price = Decimal(comp) if comp else None
        listing.save(update_fields=["competitor_price"])
    messages.success(request, "Prices updated.")
    return redirect(reverse("shop:manage_money") + "#pricing")




# ------------------------------------------------------------------ books

def _books_context():
    completed = Order.objects.exclude(
        status__in=[OrderStatus.PENDING_PAYMENT, OrderStatus.REFUNDED]
    )
    refunded = Order.objects.filter(status=OrderStatus.REFUNDED)

    revenue = completed.aggregate(s=Sum("items_total"))["s"] or Decimal("0")
    tax_collected = completed.aggregate(s=Sum("tax_total"))["s"] or Decimal("0")
    refunds = refunded.aggregate(s=Sum("grand_total"))["s"] or Decimal("0")
    supplier_cost = sum((o.supplier_cost for o in completed), Decimal("0"))
    supplier_tax = sum((o.supplier_tax for o in completed), Decimal("0"))
    estimated_orders = sum(1 for o in completed if o.supplier_cost_is_estimate)

    overhead_qs = OverheadEntry.objects.all()
    overhead_total = overhead_qs.aggregate(s=Sum("amount"))["s"] or Decimal("0")
    by_cat = overhead_qs.values("category").annotate(s=Sum("amount")).order_by("-s")

    net = revenue - supplier_cost - overhead_total - refunds

    return {
        "revenue": revenue,
        "supplier_cost": supplier_cost,
        "overhead_total": overhead_total,
        "overhead_by_cat": by_cat,
        "refunds": refunds,
        "tax_collected": tax_collected,
        "supplier_tax": supplier_tax,
        "estimated_orders": estimated_orders,
        "net": net,
        "entries": overhead_qs[:50],
        "categories": OverheadEntry.Category.choices,
    }


@staff_member_required
def books(request):
    """Old standalone URL: books now live on the merged Money page."""
    return redirect(reverse("shop:manage_money") + "#books")


@staff_member_required
def money(request):
    """Pricing + Books, one page: both are the financial side of the console."""
    return render(request, "shop/manage/money.html", {
        "rows": _pricing_rows(),
        "ceiling": catalogue.kind_for(ProductType.TEE).price_ceiling,
        "multiplier": catalogue.STANDARD_PRICING.multiplier,
        "guardrail": catalogue.STANDARD_PRICING.guardrail,
        **_books_context(),
    })


@staff_member_required
@require_POST
def overhead_add(request):
    try:
        OverheadEntry.objects.create(
            incurred_on=request.POST.get("incurred_on") or timezone.now().date(),
            label=request.POST.get("label", "").strip() or "Expense",
            amount=Decimal(request.POST.get("amount", "0") or "0"),
            category=request.POST.get("category", OverheadEntry.Category.OTHER),
            note=request.POST.get("note", ""),
        )
        messages.success(request, "Expense logged.")
    except Exception:  # noqa: BLE001
        messages.error(request, "Couldn't log that — check the amount and date.")
    return redirect(reverse("shop:manage_money") + "#books")


@staff_member_required
@require_POST
def overhead_delete(request, pk):
    OverheadEntry.objects.filter(pk=pk).delete()
    return redirect(reverse("shop:manage_money") + "#books")
