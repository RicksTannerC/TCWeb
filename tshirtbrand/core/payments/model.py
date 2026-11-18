"""What the shop asks a payment provider for, and what it hears back. Plain values only: no provider's
field names, no Django, no network."""

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum


@dataclass(frozen=True)
class CheckoutLine:
    name: str
    description: str
    quantity: int
    unit_price: Decimal


@dataclass(frozen=True)
class ShippingOption:
    label: str
    amount: Decimal
    min_days: int
    max_days: int


# Shipping is free to the customer and absorbed into pricing. Keep the days in step with the Shipping &
# Returns page ("about 10-14 days"): about a week to hand to the carrier plus the carrier's window.
STANDARD_SHIPPING = ShippingOption("Standard shipping", Decimal("0"), 10, 14)

# the checkout page's return link carries this token where the provider should put its session id
SESSION_ID_TOKEN = "{session_id}"


@dataclass(frozen=True)
class CheckoutRequest:
    order_ref: str
    lines: tuple
    email: str
    success_url: str          # may contain SESSION_ID_TOKEN
    cancel_url: str
    shipping: ShippingOption = STANDARD_SHIPPING
    countries: tuple = ("US",)
    currency: str = "usd"
    collect_tax: bool = False


@dataclass(frozen=True)
class CheckoutSession:
    id: str
    url: str


class PaymentEventKind(str, Enum):
    PAID = "paid"


@dataclass(frozen=True)
class PaymentEvent:
    """A confirmed payment, as heard from the provider."""

    kind: PaymentEventKind
    order_ref: str            # the order_ref we sent with the checkout request
    session_id: str
    payment_ref: str          # what a refund needs
    email: str = ""
    name: str = ""
    address: dict = field(default_factory=dict)   # line1, line2, city, state, postal_code, country
    total: Decimal = Decimal("0")
    tax: Decimal = Decimal("0")
    shipping: Decimal = Decimal("0")

    @property
    def items_total(self):
        return self.total - self.tax - self.shipping


@dataclass(frozen=True)
class RefundResult:
    amount: Decimal | None    # None = the whole payment
    simulated: bool = False   # True when nothing was sent to a real provider
