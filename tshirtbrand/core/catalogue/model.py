"""What the shop sells and how it prices it. Pure rules: no Django, no supplier, no database.

A **product kind** says what is special about a kind of product (a tee, a sticker, a mug...): what it is called,
how its page slug is made, its own price ceiling and pricing rule. Adding a product
line means adding a kind here; no supplier or payment code mentions "shirt"."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal


@dataclass(frozen=True)
class PricingRule:
    """price = landed cost x multiplier, rounded to whole dollars; flagged when the real price falls under the
    guardrail multiple of landed cost."""

    multiplier: Decimal = Decimal("2.5")
    guardrail: Decimal = Decimal("2.0")


STANDARD_PRICING = PricingRule()


@dataclass(frozen=True)
class ProductKind:
    code: str                         # the stored value, e.g. "tee"
    label: str
    slug_suffix: str = ""             # added to a listing's page slug, e.g. "-sticker"
    price_ceiling: Decimal | None = None   # a suggested price above this is flagged on its template
    pricing: PricingRule = STANDARD_PRICING


KINDS = {
    k.code: k
    for k in (
        ProductKind("tee", "T-shirt", price_ceiling=Decimal("40")),
        ProductKind("sticker", "Sticker", slug_suffix="-sticker"),
        ProductKind("sweatshirt", "Sweatshirt"),
        ProductKind("mug", "Mug"),
    )
}


def kind_for(code):
    """The ProductKind for a stored code. An unknown code gets a plain kind rather than an error, so an old row
    never breaks a page."""
    return KINDS.get(code) or ProductKind(code or "", (code or "").title())


def landed_cost(base_cost, shipping_est):
    return base_cost + shipping_est


def suggested_price(landed, rule=STANDARD_PRICING):
    return (landed * rule.multiplier).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def margin_dollars(price, landed):
    return price - landed


def margin_multiple(price, landed):
    """price / landed cost to two places, or None when the cost isn't known (zero)."""
    if not landed:
        return None
    return (price / landed).quantize(Decimal("0.01"))


def below_guardrail(price, landed, rule=STANDARD_PRICING):
    m = margin_multiple(price, landed)
    return m is not None and m < rule.guardrail


def template_warnings(kind, landed, has_sizes):
    """What is wrong with a product template, in words fit to show the curator."""
    warnings = []
    if landed == 0:
        warnings.append("Costs are $0, so listings would be priced at $0.")
    if kind.price_ceiling is not None and suggested_price(landed, kind.pricing) > kind.price_ceiling:
        warnings.append(f"Suggested price is over the ${kind.price_ceiling} {kind.code} ceiling.")
    if not has_sizes:
        warnings.append("No sizes.")
    return warnings
