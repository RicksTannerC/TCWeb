"""What the payments context needs from the outside: a payment gateway."""

from decimal import Decimal
from typing import Protocol

from .model import CheckoutRequest, CheckoutSession, PaymentEvent, RefundResult


class PaymentError(Exception):
    """The provider refused, was unreachable, or sent something that isn't what it claims to be."""


class PaymentGateway(Protocol):
    name: str
    simulated: bool   # True when it can't really take money (no credentials): checkout is a local stand-in

    def create_checkout(self, request: CheckoutRequest) -> CheckoutSession:
        """Start a hosted checkout. Raises PaymentError."""

    def parse_event(self, payload: bytes, signature: str) -> PaymentEvent | None:
        """Verify and read a provider webhook. Raises PaymentError when it can't be trusted (bad signature,
        malformed body); returns None for a genuine event the shop has no use for."""

    def refund(self, payment_ref: str, amount: Decimal | None = None) -> RefundResult:
        """Refund all (amount None) or part of a payment. Raises PaymentError. A simulated gateway sends
        nothing and says so in the result."""
