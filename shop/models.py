"""
Catalogue model.

A **Design** is the artwork (the parent). One design produces one or more
**Listings** — a sellable card: this design, on this product, in this color.
Size is the only choice made on a listing. Stickers are Listings too; for now
the storefront shows a design's sticker option inside the tee's card rather
than as its own tile.
"""

from decimal import Decimal, ROUND_HALF_UP

from django.db import models
from django.urls import reverse
from django.utils.text import slugify

from .storage import get_private_storage


PRICING_MULTIPLIER = Decimal("2.5")
PRICING_GUARDRAIL = Decimal("2.0")


def unique_slug(model, text, *, pk=None, max_length=140, fallback="item"):
    """A slug for `text` that no other `model` row is using.

    Slugifies `text`, then appends -2, -3, ... until it is free. Falls back to
    `fallback` when the text has nothing sluggable in it (e.g. only symbols).
    """
    base = slugify(text)[: max_length - 8].strip("-") or fallback
    candidate, n = base, 2
    others = model.objects.exclude(pk=pk) if pk else model.objects.all()
    while others.filter(slug=candidate).exists():
        candidate = f"{base}-{n}"
        n += 1
    return candidate


class ProductType(models.TextChoices):
    TEE = "tee", "T-shirt"
    STICKER = "sticker", "Sticker"
    SWEATSHIRT = "sweatshirt", "Sweatshirt"
    MUG = "mug", "Mug"


class Status(models.TextChoices):
    DRAFT = "draft", "Draft — not connected to Printful"
    HIDDEN = "hidden", "Hidden — staged, not public"
    LIVE = "live", "Live"


class Tag(models.Model):
    """A motif or theme — 'cosmic', 'mountains', 'skulls'."""

    name = models.CharField(max_length=40, unique=True)
    slug = models.SlugField(max_length=50, unique=True, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Collection(models.Model):
    """
    A curated grouping. The permanent base collection (`is_base`) always sits
    underneath; a live seasonal collection layers its theme and featured
    designs on top. Theme fields are stubbed here for a later milestone.
    """

    name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=90, unique=True, blank=True)
    summary = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.HIDDEN)
    is_base = models.BooleanField(default=False)
    go_live_at = models.DateTimeField(null=True, blank=True)

    # dormant until the seasonal-worlds milestone
    theme_tokens = models.JSONField(default=dict, blank=True)
    scene_asset = models.ImageField(upload_to="collections/", null=True, blank=True)
    entry_object = models.CharField(max_length=120, blank=True)
    motion_preset = models.CharField(max_length=60, blank=True)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_base", "name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class ProductTemplate(models.Model):
    """
    A reusable product configuration — 'Heavyweight tee, front print',
    '3in die-cut sticker'. Carries the nominal costs the pricing rule uses
    until real Printful figures replace them, and the default size set that
    is copied onto a new listing.
    """

    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=90, unique=True, blank=True)
    product_type = models.CharField(max_length=12, choices=ProductType.choices)

    base_cost = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal("0.00"))
    shipping_est = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal("0.00"))

    # [{"label": "M", "width_in": 20, "height_in": 28}, ...]
    default_sizes = models.JSONField(default=list, blank=True)

    # dormant until the Printful milestone
    printful_blueprint_id = models.CharField(max_length=40, blank=True)
    printful_provider_id = models.CharField(max_length=40, blank=True)
    print_placement = models.CharField(max_length=40, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(ProductTemplate, self.name, pk=self.pk, max_length=90, fallback="template")
        super().save(*args, **kwargs)

    @property
    def landed_cost(self):
        return self.base_cost + self.shipping_est

    @property
    def suggested_price(self):
        """What the pricing rule would charge for a listing made from this template."""
        raw = self.landed_cost * PRICING_MULTIPLIER
        return raw.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


class Design(models.Model):
    """The artwork. Parent of its listings."""

    title = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    story = models.TextField(blank=True, help_text="The short narrative shown on the card.")
    artwork = models.FileField(
        upload_to="designs/", storage=get_private_storage, null=True, blank=True,
        help_text="Print-ready original (SVG or PNG). Private: viewable only in the console.",
    )
    tags = models.ManyToManyField(Tag, blank=True, related_name="designs")

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(Design, self.title, pk=self.pk, max_length=140, fallback="design")
        super().save(*args, **kwargs)

    @property
    def print_file_url(self):
        """A URL a print partner could fetch the original from, or None.

        Originals are private and have no public URL. Delivering them to Printful
        needs a signed, expiring link, which hasn't been built yet.
        """
        return None

    @property
    def sticker_listing(self):
        """The live sticker version of this design, if there is one."""
        return self.listings.filter(product_type=ProductType.STICKER, status=Status.LIVE).first()


class Listing(models.Model):
    """A sellable card: one design, one product, one color."""

    design = models.ForeignKey(Design, on_delete=models.CASCADE, related_name="listings")
    template = models.ForeignKey(ProductTemplate, on_delete=models.PROTECT, related_name="listings")
    product_type = models.CharField(max_length=12, choices=ProductType.choices)

    color = models.CharField(max_length=40, blank=True)
    slug = models.SlugField(max_length=160, unique=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)

    collection = models.ForeignKey(
        Collection, on_delete=models.SET_NULL, null=True, blank=True, related_name="listings",
    )

    price = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal("0.00"))
    base_cost = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal("0.00"))
    shipping_est = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal("0.00"))
    competitor_price = models.DecimalField(
        max_digits=7, decimal_places=2, null=True, blank=True,
        help_text="Hand-entered, for the pricing workspace.",
    )

    # empty = not connected to Printful
    printful_product_id = models.CharField(max_length=40, blank=True)

    sort_order = models.PositiveIntegerField(default=0)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "design__title"]

    def __str__(self):
        return f"{self.design.title} — {self.get_product_type_display()}"

    def save(self, *args, **kwargs):
        if not self.product_type and self.template_id:
            self.product_type = self.template.product_type
        if not self.slug:
            self.slug = self._unique_slug()
        super().save(*args, **kwargs)

    def _unique_slug(self):
        base = slugify(self.design.title)
        if self.product_type == ProductType.STICKER:
            base = f"{base}-sticker"
        candidates = [base]
        if self.color:
            candidates.append(f"{base}-{slugify(self.color)}")
        for candidate in candidates:
            if not Listing.objects.exclude(pk=self.pk).filter(slug=candidate).exists():
                return candidate
        n = 2
        while Listing.objects.exclude(pk=self.pk).filter(slug=f"{base}-{n}").exists():
            n += 1
        return f"{base}-{n}"

    def get_absolute_url(self):
        return reverse("shop:listing_detail", args=[self.slug])

    @property
    def is_connected(self):
        return bool(self.printful_product_id)

    @property
    def landed_cost(self):
        return self.base_cost + self.shipping_est

    @property
    def suggested_price(self):
        raw = self.landed_cost * PRICING_MULTIPLIER
        return raw.quantize(Decimal("1"), rounding=ROUND_HALF_UP)

    @property
    def margin_dollars(self):
        return self.price - self.landed_cost

    @property
    def margin_multiple(self):
        if not self.landed_cost:
            return None
        return (self.price / self.landed_cost).quantize(Decimal("0.01"))

    @property
    def below_guardrail(self):
        m = self.margin_multiple
        return m is not None and m < PRICING_GUARDRAIL

    @property
    def primary_image(self):
        return self.images.first()


class ListingSize(models.Model):
    """One size row on a listing, with its measurements shown inline."""

    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name="sizes")
    label = models.CharField(max_length=16)
    width_in = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    height_in = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    price_override = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    printful_variant_id = models.CharField(max_length=40, blank=True)
    in_stock = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"{self.listing} — {self.label}"

    @property
    def price(self):
        return self.price_override if self.price_override is not None else self.listing.price

    @property
    def measurements(self):
        if self.width_in and self.height_in:
            return f'{self.width_in:g}" wide, {self.height_in:g}" tall'
        return ""


class ListingImage(models.Model):
    class Kind(models.TextChoices):
        MOCKUP = "mockup", "Mockup"
        LIFESTYLE = "lifestyle", "Lifestyle"
        DETAIL = "detail", "Print detail"

    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="listings/")
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.MOCKUP)
    alt_text = models.CharField(max_length=160, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"{self.listing} — image {self.pk}"


# Order-side + console models live in sibling modules; import so migrations see them.
from .orders import (  # noqa: E402,F401
    Fulfillment,
    Order,
    OrderItem,
    OrderStatus,
    Subscriber,
)
from .console import ContactMessage, OverheadEntry, Page, VisitLog  # noqa: E402,F401
