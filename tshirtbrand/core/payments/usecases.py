"""What the business does about payments: the rules, with the gateway and the orders passed in."""

from .model import CheckoutLine, CheckoutRequest, SESSION_ID_TOKEN


def checkout_request(order_ref, items, *, email, success_url, cancel_url, collect_tax=False):
    """The checkout to ask the gateway for. `items` are (name, product_type, color, size, quantity, unit_price)
    rows; the line description is built here so every gateway shows the same words."""
    lines = tuple(
        CheckoutLine(
            name=name,
            description=", ".join(p for p in (product_type.title(), color, size) if p) or "Item",
            quantity=quantity,
            unit_price=unit_price,
        )
        for name, product_type, color, size, quantity, unit_price in items
    )
    return CheckoutRequest(
        order_ref=str(order_ref), lines=lines, email=email or "", success_url=success_url, cancel_url=cancel_url,
        collect_tax=collect_tax,
    )


def success_url_with_session(base_url):
    """The return link, ending in the token the gateway swaps for its own session id."""
    return f"{base_url}?ref={SESSION_ID_TOKEN}"
