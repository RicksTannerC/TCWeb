"""The curator's console: the dashboard."""

from datetime import timedelta
from decimal import Decimal

from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, Sum
from django.shortcuts import render
from django.utils import timezone

from shop.console import ContactMessage, VisitLog
from shop.models import Listing, Status
from shop.orders import Order, OrderItem, OrderStatus, Subscriber


# ------------------------------------------------------------------ dashboard

@staff_member_required
def dashboard(request):
    now = timezone.now()
    d7, d30 = now - timedelta(days=7), now - timedelta(days=30)

    paid = Order.objects.exclude(status=OrderStatus.PENDING_PAYMENT)
    completed = paid.exclude(status=OrderStatus.REFUNDED)

    def revenue(since):
        return completed.filter(created__gte=since).aggregate(s=Sum("grand_total"))["s"] or Decimal("0")

    from shop.orders import OrderItem
    top_designs = (
        OrderItem.objects.filter(order__in=completed)
        .values("design_title")
        .annotate(units=Sum("quantity"))
        .order_by("-units")[:6]
    )

    abandoned = Order.objects.filter(status=OrderStatus.PENDING_PAYMENT, created__gte=d30).count()
    checked_out = paid.filter(created__gte=d30).count()
    abandon_rate = (
        round(abandoned / (abandoned + checked_out) * 100) if (abandoned + checked_out) else 0
    )

    recent = list(completed.filter(created__gte=d30).prefetch_related("items"))
    avg_margin = (sum((o.margin for o in recent), Decimal("0")) / len(recent)) if recent else Decimal("0")

    sources = (
        VisitLog.objects.filter(created__gte=d30)
        .values("referrer_host", "utm_source")
        .annotate(n=Count("id"))
        .order_by("-n")[:6]
    )
    top_sources = []
    for s in sources:
        label = s["utm_source"] or s["referrer_host"] or "direct"
        top_sources.append({"label": label, "n": s["n"]})

    ctx = {
        "rev_7": revenue(d7),
        "rev_30": revenue(d30),
        "orders_7": completed.filter(created__gte=d7).count(),
        "orders_30": len(recent),
        "awaiting": paid.filter(status=OrderStatus.PENDING_APPROVAL).count(),
        "avg_margin": avg_margin.quantize(Decimal("0.01")),
        "top_designs": top_designs,
        "top_sources": top_sources,
        "visits_30": VisitLog.objects.filter(created__gte=d30).count(),
        "abandon_rate": abandon_rate,
        "subscribers": Subscriber.objects.filter(is_active=True).count(),
        "live_listings": Listing.objects.filter(status=Status.LIVE).count(),
        "draft_listings": Listing.objects.filter(status=Status.DRAFT).count(),
        "unread_messages": ContactMessage.objects.filter(handled=False).count(),
    }
    return render(request, "shop/manage/dashboard.html", ctx)
