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


class PrintPlacement(models.TextChoices):
    """Printful's standard print-area keys for apparel."""
    FRONT = "front", "Front"
    BACK = "back", "Back"
    LEFT_CHEST = "left_chest", "Left chest"
    LEFT_SLEEVE = "left_sleeve", "Left sleeve"
    RIGHT_SLEEVE = "right_sleeve", "Right sleeve"


class PrintPosition(models.TextChoices):
    """A simple, curator-facing proxy for where the art sits within its
    placement area -- not Printful's raw pixel coordinates. See
    Listing.print_position_payload() for how this becomes an actual
    position sent to Printful."""
    CENTER = "center", "Centered"
    HIGHER = "higher", "Higher"
    LOWER = "lower", "Lower"
    LEFT = "left", "Toward the left"
    RIGHT = "right", "Toward the right"
    TOP_LEFT = "top_left", "Upper left"
    TOP_RIGHT = "top_right", "Upper right"


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

    # Shown as its own card on the landing page (centerpiece image = its
    # first live listing's primary image), linking through to the catalogue.
    # Only ever shown while also `status == LIVE`.
    featured_on_landing = models.BooleanField(default=False)
    landing_sort_order = models.PositiveIntegerField(default=0)

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

    @property
    def centerpiece_listing(self):
        """The listing whose image represents this collection on a landing card."""
        return (
            self.listings.filter(status=Status.LIVE)
            .select_related("design")
            .prefetch_related("images")
            .first()
        )

    @classmethod
    def landing_cards(cls):
        """Live, curator-featured collections that have something to show."""
        return [
            c for c in cls.objects.filter(status=Status.LIVE, featured_on_landing=True)
            .order_by("landing_sort_order", "name")
            if c.centerpiece_listing
        ]


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

    # The real Printful catalog product (blueprint) this template maps to,
    # picked via the catalog search in the console. printful_blueprint_name
    # is display-only (never sent to Printful) so a saved template still
    # reads as "Stanley/Stella STTU169" rather than a bare number.
    printful_blueprint_id = models.CharField(max_length=40, blank=True)
    printful_blueprint_name = models.CharField(max_length=160, blank=True)
    printful_provider_id = models.CharField(max_length=40, blank=True)
    print_placement = models.CharField(
        max_length=40, choices=PrintPlacement.choices, default=PrintPlacement.FRONT, blank=True,
    )

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


# Where each position preset nudges a print, as a fraction of its placement
# area (0.5, 0.5 = dead center). Left/right/upper are as you look at the shirt.
POSITION_OFFSETS = {
    PrintPosition.CENTER: (0.5, 0.5),
    PrintPosition.HIGHER: (0.5, 0.3),
    PrintPosition.LOWER: (0.5, 0.7),
    PrintPosition.LEFT: (0.3, 0.5),
    PrintPosition.RIGHT: (0.7, 0.5),
    PrintPosition.TOP_LEFT: (0.3, 0.25),
    PrintPosition.TOP_RIGHT: (0.7, 0.25),
}


# Printful's front and back print area on the shirts in use (Comfort Colors 1717, Bella + Canvas
# 3001), read from its printfiles info: 1800 x 2400 px. Used when the real figure can't be fetched.
DEFAULT_PRINT_AREA = (1800, 2400)


def placement_payload(placement, scale_pct, position, area=DEFAULT_PRINT_AREA, aspect=1.0):
    """One print area in the shape Printful's `files[]` entries expect: `type`,
    plus a `position` object of area/width/height/top/left, all in pixels.

    `area` must be the placement's real print-file size (Printful measures the
    box against it; a wrong area makes it ignore the offset and center the
    print). `aspect` is the artwork's width / height, so the box keeps the
    art's shape instead of squashing it. `scale_pct` is how wide the art runs
    across the area (capped so it also fits the area's height). The default
    (100%, centered) needs no positioning fields at all. The box is kept
    inside the area (a print can't hang off the shirt).
    """
    if scale_pct >= 100 and position == PrintPosition.CENTER:
        return {"type": placement}
    cx, cy = POSITION_OFFSETS.get(position, (0.5, 0.5))
    scale = max(25, min(100, scale_pct)) / 100
    area_w, area_h = (int(area[0]), int(area[1])) if area else DEFAULT_PRINT_AREA
    aspect = aspect if aspect and aspect > 0 else 1.0
    width = scale * area_w
    height = width / aspect
    if height > scale * area_h:
        height = scale * area_h
        width = height * aspect
    width, height = min(area_w, round(width)), min(area_h, round(height))
    top = max(0, min(area_h - height, round(cy * area_h - height / 2)))
    left = max(0, min(area_w - width, round(cx * area_w - width / 2)))
    return {
        "type": placement,
        "position": {"area_width": area_w, "area_height": area_h, "width": width, "height": height,
                     "top": top, "left": left},
    }


class Design(models.Model):
    """The artwork. Parent of its listings."""

    class Origin(models.TextChoices):
        UNKNOWN = "unknown", "Not recorded yet"
        ORIGINAL = "original", "Original work (I made it)"
        COMMISSIONED = "commissioned", "Commissioned (with a written assignment)"
        LICENSED = "licensed", "Licensed (stock, marketplace or font licence)"
        PUBLIC_DOMAIN = "public_domain", "Public-domain source"
        AI = "ai", "AI-assisted or generated"
        OTHER = "other", "Other (explain in the notes)"

    title = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    story = models.TextField(blank=True, help_text="The short narrative shown on the card.")
    artwork = models.FileField(
        upload_to="designs/", storage=get_private_storage, null=True, blank=True,
        help_text="Print-ready original (SVG or PNG). Private: viewable only in the console.",
    )
    tags = models.ManyToManyField(Tag, blank=True, related_name="designs")

    # A private record of rights: where the artwork came from and whether anyone
    # has searched for conflicts. Never shown publicly. The Terms promise that the
    # designs are ours or used with permission; this is the evidence behind it.
    origin = models.CharField(max_length=16, choices=Origin.choices, default=Origin.UNKNOWN)
    ip_checked_on = models.DateField(
        null=True, blank=True, help_text="When trademark/copyright conflicts were last searched for.")
    ip_notes = models.TextField(
        blank=True, help_text="Source files, licence terms, receipts, what was searched and what turned up.")
    # Bumped each time the artwork file is replaced in place, so a listing sent to Printful
    # with the old file shows as needing a re-send (see Listing.print_signature).
    artwork_version = models.PositiveIntegerField(default=0)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title

    @property
    def rights_recorded(self):
        """Origin stated *and* a conflict search dated. The bar for calling it documented."""
        return self.origin != self.Origin.UNKNOWN and self.ip_checked_on is not None

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(Design, self.title, pk=self.pk, max_length=140, fallback="design")
        super().save(*args, **kwargs)

    @property
    def can_compose(self):
        """A raster file we can place on a print-area canvas ourselves (not an SVG)."""
        return bool(self.artwork) and self.artwork.name.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))

    def artwork_aspect(self):
        """The artwork's width / height, so a placed print keeps its shape. 1.0 when it
        can't be read (no file, an odd format)."""
        if not self.artwork:
            return 1.0
        try:
            with self.artwork.open("rb") as fh:
                head = fh.read()
        except OSError:
            return 1.0
        import io
        import re

        try:
            from PIL import Image

            with Image.open(io.BytesIO(head)) as im:
                w, h = im.size
            return w / h if w and h else 1.0
        except Exception:  # noqa: BLE001 - not a raster image; try SVG
            pass
        text = head[:4096].decode("utf-8", "ignore")
        box = re.search(r'viewBox\s*=\s*["\']\s*[-\d.]+[ ,]+[-\d.]+[ ,]+([\d.]+)[ ,]+([\d.]+)', text)
        if box:
            w, h = float(box.group(1)), float(box.group(2))
        else:
            wm, hm = (re.search(rf'<svg[^>]*\s{k}\s*=\s*["\']([\d.]+)', text) for k in ("width", "height"))
            if not (wm and hm):
                return 1.0
            w, h = float(wm.group(1)), float(hm.group(1))
        return w / h if w > 0 and h > 0 else 1.0

    @property
    def print_file_url(self):
        """A signed, expiring URL Printful can fetch this design's private
        original from, or None if it has no artwork. See printful_delivery.py."""
        from .printful_delivery import build_delivery_url

        return build_delivery_url(self)

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
    # What the Printful product was built from when it was last sent, so the
    # console can say when the listing has since changed and Printful hasn't.
    printful_sent_blueprint_id = models.CharField(max_length=40, blank=True)
    printful_sent_color = models.CharField(max_length=40, blank=True)
    printful_sent_placement = models.CharField(max_length=40, blank=True)
    # A fingerprint of every print area (placement, size, position, artwork) at
    # the time it was sent -- see print_signature().
    printful_sent_prints = models.CharField(max_length=255, blank=True)
    # Printful's own render of the art on the blank, as last read from the product:
    # [{"label": ..., "url": "https://..."}]. For checking placement/size/colour before listing.
    printful_preview = models.JSONField(default=list, blank=True)
    printful_preview_checked = models.DateTimeField(null=True, blank=True)

    # Simple, curator-editable positioning within the template's placement
    # area (front/back/etc. — see ProductTemplate.print_placement). Not
    # Printful's raw pixel coordinates; see print_position_payload().
    # Blank = use the template's placement. Lets one template (e.g. a tee) carry
    # some designs on the front and others on the back.
    print_placement = models.CharField(
        max_length=40, choices=PrintPlacement.choices, blank=True, default="",
        help_text="Where the print goes. Blank uses the template's placement.",
    )
    print_scale_pct = models.PositiveSmallIntegerField(
        default=100, help_text="How large the print runs within its placement area (25-100%).",
    )
    print_position = models.CharField(
        max_length=10, choices=PrintPosition.choices, default=PrintPosition.CENTER,
    )

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

    _POSITION_OFFSETS = POSITION_OFFSETS

    @property
    def printful_changes_not_sent(self):
        """What differs between this listing and the product on Printful,
        e.g. ["color (Khaki -> Black)"]. Empty when in step, or when unknown."""
        if not self.is_connected:
            return []
        out = []
        cur_bp = self.template.printful_blueprint_id
        if self.printful_sent_blueprint_id and cur_bp != self.printful_sent_blueprint_id:
            out.append(f"shirt (product {self.printful_sent_blueprint_id} \u2192 {cur_bp or 'none'})")
        if self.printful_sent_color and self.color != self.printful_sent_color:
            out.append(f"color ({self.printful_sent_color} \u2192 {self.color or 'none'})")
        if self.printful_sent_prints:
            if self.print_signature() != self.printful_sent_prints:
                out.append("print areas (placement, size, position or artwork)")
        elif self.printful_sent_placement and self.effective_print_placement != self.printful_sent_placement:
            out.append(f"placement ({self.printful_sent_placement} \u2192 {self.effective_print_placement})")
        return out

    @property
    def preview_images(self):
        """The stored Printful preview, without entries that aren't really images (an old read can
        hold the bare CDN host Printful sends as a thumbnail before it has drawn one)."""
        from urllib.parse import urlsplit

        return [p for p in self.printful_preview or []
                if isinstance(p, dict) and urlsplit(str(p.get("url", ""))).path.strip("/")]

    @property
    def printful_sent_state_unknown(self):
        """Sent before the console started recording what was sent."""
        return self.is_connected and not (self.printful_sent_blueprint_id or self.printful_sent_color)

    @property
    def effective_print_placement(self):
        return self.print_placement or self.template.print_placement or PrintPlacement.FRONT

    def print_file_payload(self):
        """The MAIN print's placement, scale and position (see placement_payload)."""
        return self.payload_for(self.design, self.effective_print_placement, self.print_scale_pct, self.print_position)

    def payload_for(self, design, placement, scale_pct, position):
        """placement_payload with this shirt's real print-area size and the artwork's shape.
        Only a positioned print needs them, so the common centered full-size case makes no lookup."""
        if scale_pct >= 100 and position == PrintPosition.CENTER:
            return placement_payload(placement, scale_pct, position)
        from . import printful

        return placement_payload(
            placement, scale_pct, position,
            area=printful.print_area(self.template.printful_blueprint_id, placement),
            aspect=design.artwork_aspect())

    @property
    def extra_prints(self):
        """Additional print areas that don't clash with the main one's placement."""
        main = self.effective_print_placement
        return [p for p in self.prints.all() if p.placement != main]

    @property
    def print_conflicts(self):
        """Additional prints sharing the main print's placement (e.g. the template's
        default placement was changed to match). They are not sent."""
        main = self.effective_print_placement
        return [p for p in self.prints.all() if p.placement == main]

    def print_signature(self):
        """A stable fingerprint of every print area, to notice when the layout
        changed after the product was sent to Printful."""
        # "g2" marks a positioned print as built with the real print-area size (before that, the
        # position was measured against a fake square and Printful centered it), so a listing
        # sent the old way shows as needing a re-send.
        # "g3" marks a positioned print as built into the print file itself (g2 sent a position
        # Printful ignored), and ":v<n>" a replaced artwork file.
        def geometry(scale, position):
            return "" if scale >= 100 and position == PrintPosition.CENTER else ":g3"

        def art(design):
            return f"d{design.pk}" + (f"v{design.artwork_version}" if design.artwork_version else "")

        parts = [f"{self.effective_print_placement}:{self.print_scale_pct}:{self.print_position}:{art(self.design)}"
                 + geometry(self.print_scale_pct, self.print_position)]
        parts += [f"{p.placement}:{p.scale_pct}:{p.position}:{art(p.design or self.design)}"
                  + geometry(p.scale_pct, p.position) for p in self.extra_prints]
        return "|".join(sorted(parts))[:255]

    def print_file_entries(self):
        """Every print area as a Printful `files[]` entry (main first), each with
        its own freshly signed artwork link. An area whose design has no artwork
        is skipped; so is an extra that clashes with the main placement."""
        entries = []
        for design, payload in [(self.design, self.print_file_payload())] + [
                (p.design or self.design, p.file_payload()) for p in self.extra_prints]:
            entry = self._entry(design, payload)
            if entry:
                entries.append(entry)
        return entries

    @staticmethod
    def _entry(design, payload):
        """One `files[]` entry. A positioned print is built into the file itself: we send a
        full-print-area image with the art already placed, because Printful ignores the
        `position` of a store product's file and centers it. SVG art can't be composed here, so
        it still goes with a `position` (best effort)."""
        from .printful_delivery import build_delivery_url

        position = payload.get("position")
        composed = bool(position) and design.can_compose
        url = build_delivery_url(design, layout=position) if composed else design.print_file_url
        if not url:
            return None
        entry = {"url": url, "type": payload["type"]}
        if position and not composed:
            entry["position"] = position
        return entry

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


class ListingPrint(models.Model):
    """An additional print area on a listing: e.g. a small front design on a
    shirt whose main print (on the Listing itself) is a large back print."""

    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name="prints")
    placement = models.CharField(max_length=40, choices=PrintPlacement.choices)
    design = models.ForeignKey(
        Design, on_delete=models.PROTECT, null=True, blank=True, related_name="used_as_extra_print",
        help_text="Blank = the same artwork as the listing's main print.",
    )
    scale_pct = models.PositiveSmallIntegerField(
        default=100, help_text="How large the print runs within its placement area (25-100%).",
    )
    position = models.CharField(max_length=12, choices=PrintPosition.choices, default=PrintPosition.CENTER)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["listing", "placement"], name="one_extra_print_per_placement"),
        ]

    def __str__(self):
        return f"{self.listing} \u2014 {self.get_placement_display()}"

    def file_payload(self):
        return self.listing.payload_for(self.design or self.listing.design, self.placement, self.scale_pct, self.position)


class ListingSize(models.Model):
    """One size row on a listing, with its measurements shown inline."""

    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name="sizes")
    label = models.CharField(max_length=16)
    width_in = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    height_in = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    price_override = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    # The id Printful gave this size once the listing was sent (a *sync*
    # variant id). Orders to a sent listing use this one.
    printful_variant_id = models.CharField(max_length=40, blank=True)
    # The id of this size in Printful's catalogue (what "Match sizes" finds).
    # Used to build the product when sending, and for listings not yet sent.
    printful_catalog_variant_id = models.CharField(max_length=40, blank=True)
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
from .console import ContactMessage, FailedLogin, OverheadEntry, Page, VisitLog  # noqa: E402,F401
