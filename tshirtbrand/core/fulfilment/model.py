"""Neutral data for talking to a print-on-demand supplier. Nothing here names a particular supplier or its
wire format: an adapter translates these to and from whatever the supplier's API speaks.

Plain frozen dataclasses only (docs/ARCHITECTURE.md rule 6)."""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


# ------------------------------------------------------------------ catalogue lookups

@dataclass(frozen=True)
class CatalogProduct:
    """A blank the supplier can print on (a shirt model, a mug, ...)."""
    id: str
    title: str
    model: str = ""
    brand: str = ""


@dataclass(frozen=True)
class ColorOption:
    name: str
    hex: str = ""      # "#rrggbb" or ""
    hex2: str = ""     # second colour of a two-tone (heather, ...) or ""
    image: str = ""    # https photo of this colour or ""


@dataclass(frozen=True)
class SizeMatch:
    """Which of the wanted size labels the supplier has in a colour, and the id of each."""
    matches: dict            # label -> supplier's variant id (str)
    unmatched: tuple         # labels with no variant in that colour
    available_colors: tuple  # every colour the product comes in


@dataclass(frozen=True)
class PrintArea:
    """The real print-file size, in pixels, of one placement of a product."""
    width: int
    height: int


# ------------------------------------------------------------------ products (what a listing becomes)

@dataclass(frozen=True)
class PrintBox:
    """Where a print sits inside its print area, in pixels. Only used for art that cannot be
    composed into the file itself; a composed print has no box (it already is the whole area)."""
    area_width: int
    area_height: int
    left: int
    top: int
    width: int
    height: int


@dataclass(frozen=True)
class PrintFile:
    placement: str        # "front", "back", "sleeve_left", ...
    url: str              # where the supplier fetches the artwork
    box: PrintBox | None = None


@dataclass(frozen=True)
class VariantSpec:
    external_id: str          # our own id for this size, unique per product
    catalog_variant_id: str   # the supplier's blank (a size in a colour); "" when not matched yet
    retail_price: Decimal
    files: tuple = ()         # PrintFile, ...


@dataclass(frozen=True)
class ProductSpec:
    name: str
    external_id: str          # our own id for the product, unique at the supplier
    variants: tuple = ()      # VariantSpec, ...


@dataclass(frozen=True)
class ProductVariant:
    id: str            # the supplier's id for this size of the product (what orders refer to); "" if unknown
    external_id: str   # our id for it, echoed back
    size: str = ""
    color: str = ""


@dataclass(frozen=True)
class Preview:
    label: str
    url: str


@dataclass(frozen=True)
class ProductRecord:
    """What the supplier knows about a product we sent it."""
    product_id: str
    variants: tuple = ()   # ProductVariant; empty when the supplier only sent a summary
    previews: tuple = ()   # Preview, at most 6, https only


# ------------------------------------------------------------------ orders

@dataclass(frozen=True)
class Recipient:
    name: str
    email: str = ""
    address1: str = ""
    address2: str = ""
    city: str = ""
    region: str = ""        # state / province code
    country: str = "US"
    postal_code: str = ""


@dataclass(frozen=True)
class OrderLine:
    """One thing to make. Exactly one of `product_variant_id` (a size of a product we already sent) or
    `catalog_variant_id` (a blank, with `files` to print on it) is set."""
    quantity: int
    name: str
    unit_price: Decimal
    product_variant_id: str = ""
    catalog_variant_id: str = ""
    files: tuple = ()

    def __post_init__(self):
        if bool(self.product_variant_id) == bool(self.catalog_variant_id):
            raise ValueError("an order line needs exactly one of product_variant_id and catalog_variant_id")


@dataclass(frozen=True)
class OrderRequest:
    external_id: str
    recipient: Recipient
    lines: tuple     # OrderLine, ...


@dataclass(frozen=True)
class SubmittedOrder:
    supplier_order_id: str
    status: str = ""
    cost_total: Decimal | None = None   # what the supplier says it will charge; None if it didn't say
    cost_tax: Decimal = Decimal("0.00")


# ------------------------------------------------------------------ events coming back

class EventKind(str, Enum):
    IN_PRODUCTION = "in_production"
    SHIPPED = "shipped"
    RETURNED = "returned"
    FAILED = "failed"
    ON_HOLD = "on_hold"
    CANCELED = "canceled"


@dataclass(frozen=True)
class SupplierEvent:
    kind: EventKind
    supplier_order_id: str = ""
    external_id: str = ""       # the id we gave the order when submitting it
    tracking_number: str = ""
    tracking_url: str = ""
    carrier: str = ""
    reason: str = ""            # human-readable, worded by the adapter
