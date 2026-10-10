"""Console-only records: content pages, overhead entries, customer messages, visits,
failed sign-ins."""

from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class Page(models.Model):
    """A content page, editable in the console without a deploy."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        LIVE = "live", "Live"

    title = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    body = models.TextField(help_text="Markdown.")
    meta_description = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.DRAFT)
    show_in_footer = models.BooleanField(default=True)
    footer_order = models.PositiveIntegerField(default=0)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["footer_order", "title"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("shop:page", args=[self.slug])


class VisitLog(models.Model):
    """First-touch per session — referrer + campaign only, no IP, no fingerprint."""

    session_key = models.CharField(max_length=40, db_index=True)
    landing_path = models.CharField(max_length=300)
    referrer_host = models.CharField(max_length=200, blank=True)
    utm_source = models.CharField(max_length=80, blank=True)
    utm_medium = models.CharField(max_length=80, blank=True)
    utm_campaign = models.CharField(max_length=120, blank=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created"]

    def __str__(self):
        return self.source

    @property
    def source(self):
        if self.utm_source:
            return self.utm_source
        if self.referrer_host:
            return self.referrer_host
        return "direct"


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


class FailedLogin(models.Model):
    """One failed staff sign-in step, kept so lockouts survive a restart.

    Only failures are stored (a success deletes the username's rows). The
    username is lower-cased and truncated; no password or code is ever kept.
    shop/login_throttle.py explains how rows are counted.
    """

    class Kind(models.TextChoices):
        PASSWORD = "password", "Password"
        OTP = "otp", "Second-factor code"

    username = models.CharField(max_length=150)
    ip = models.CharField(max_length=45, blank=True)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.PASSWORD)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["username", "created_at"]),
            models.Index(fields=["ip", "created_at"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.kind} failure for {self.username!r} from {self.ip or '?'}"
