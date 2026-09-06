"""Console-only records: overhead entries and customer messages."""

from decimal import Decimal

from django.db import models


class OverheadEntry(models.Model):
    class Category(models.TextChoices):
        HOSTING = "hosting", "Hosting & infrastructure"
        SOFTWARE = "software", "Software & services"
        MARKETING = "marketing", "Marketing & ads"
        SUPPLIES = "supplies", "Supplies & samples"
        FEES = "fees", "Fees & charges"
        OTHER = "other", "Other"

    incurred_on = models.DateField()
    label = models.CharField(max_length=120)
    amount = models.DecimalField(max_digits=9, decimal_places=2)
    category = models.CharField(max_length=16, choices=Category.choices, default=Category.OTHER)
    note = models.TextField(blank=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-incurred_on", "-id"]

    def __str__(self):
        return f"{self.incurred_on} {self.label} ${self.amount}"


class ContactMessage(models.Model):
    name = models.CharField(max_length=120, blank=True)
    email = models.EmailField()
    subject = models.CharField(max_length=160, blank=True)
    body = models.TextField()
    order = models.ForeignKey(
        "shop.Order", on_delete=models.SET_NULL, null=True, blank=True, related_name="messages"
    )
    handled = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["handled", "-created"]

    def __str__(self):
        return f"{self.email}: {self.subject or self.body[:40]}"
