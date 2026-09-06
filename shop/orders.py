"""
Order models.

An **Order** is created (idempotently) when Stripe reports a completed
checkout. It lands in ``pending_approval`` — every order waits for the
curator's one-click go-ahead before it is sent to a print partner
(Milestone 3). One order can split into several **Fulfillments**, one per
print partner / shipment.
"""

from decimal import Decimal

from django.db import models
from django.utils.crypto import get_random_string


class OrderStatus(models.TextChoices):
    PENDING_PAYMENT = "pending_payment", "Awaiting payment"
    PENDING_APPROVAL = "pending_approval", "Awaiting approval"
    APPROVED = "approved", "Approved"
    SUBMITTED = "submitted", "Submitted to partner"
    IN_PRODUCTION = "in_production", "In production"
    SHIPPED = "shipped", "Shipped"
    DELIVERED = "delivered", "Delivered"
    CANCELLED = "cancelled", "Cancelled"
    REFUNDED = "refunded", "Refunded"


def _token():
    return get_random_string(40)


class Order(models.Model):
    # Stripe
    stripe_session_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    stripe_payment_intent = models.CharField(max_length=255, blank=True)

    # customer (guest — no account in Phase 1)
    email = models.EmailField()
    name = models.CharField(max_length=160, blank=True)
    shipping_address = models.JSONField(default=dict, blank=True)

    # money (captured from Stripe, in dollars)
    items_total = models.DecimalField(max_digits=9, decimal_places=2, default=Decimal("0.00"))
    shipping_total = models.DecimalField(max_digits=9, decimal_places=2, default=Decimal("0.00"))
    tax_total = models.DecimalField(max_digits=9, decimal_places=2, default=Decimal("0.00"))
    grand_total = models.DecimalField(max_digits=9, decimal_places=2, default=Decimal("0.00"))

    status = models.CharField(
        max_length=20, choices=OrderStatus.choices, default=OrderStatus.PENDING_APPROVAL
    )

    # magic-link order tracking (no login)
    track_token = models.CharField(max_length=40, unique=True, default=_token, editable=False)

    curator_note = models.TextField(blank=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created"]

    def __str__(self):
        return f"Order #{self.pk} — {self.email}"

    @property
    def reference(self):
        return f"TTS-{self.pk:05d}"

    @property
    def supplier_cost(self):
        return sum((i.supplier_cost_total for i in self.items.all()), Decimal("0.00"))

    @property
    def margin(self):
        return self.items_total - self.supplier_cost


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")

    # snapshot the listing at purchase time (listings can change / rotate out)
    listing = models.ForeignKey("shop.Listing", on_delete=models.SET_NULL, null=True, blank=True)
    listing_size = models.ForeignKey("shop.ListingSize", on_delete=models.SET_NULL, null=True, blank=True)

    design_title = models.CharField(max_length=160)
    product_type = models.CharField(max_length=12)
    color = models.CharField(max_length=40, blank=True)
    size_label = models.CharField(max_length=16, blank=True)

    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=9, decimal_places=2)
    unit_supplier_cost = models.DecimalField(max_digits=9, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.quantity} x {self.design_title} ({self.size_label})"

    @property
    def line_total(self):
        return self.unit_price * self.quantity

    @property
    def supplier_cost_total(self):
        return self.unit_supplier_cost * self.quantity


class Fulfillment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUBMITTED = "submitted", "Submitted"
        IN_PRODUCTION = "in_production", "In production"
        SHIPPED = "shipped", "Shipped"
        DELIVERED = "delivered", "Delivered"
        PROBLEM = "problem", "Problem — needs attention"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="fulfillments")
    supplier = models.CharField(max_length=40, default="printful")
    partner_order_id = models.CharField(max_length=80, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    tracking_number = models.CharField(max_length=120, blank=True)
    tracking_url = models.URLField(blank=True)
    carrier = models.CharField(max_length=60, blank=True)

    problem_note = models.TextField(blank=True)
    items = models.ManyToManyField(OrderItem, blank=True, related_name="fulfillments")

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.order.reference} — {self.supplier} ({self.get_status_display()})"


class Subscriber(models.Model):
    """The season-drop notification list. Self-hosted, deliberately simple."""

    email = models.EmailField(unique=True)
    name = models.CharField(max_length=120, blank=True)
    source = models.CharField(max_length=40, blank=True)  # 'confirmation', 'footer', ...
    is_active = models.BooleanField(default=True)
    unsubscribe_token = models.CharField(max_length=40, unique=True, default=_token, editable=False)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created"]

    def __str__(self):
        return self.email
