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
    on_storefront: bool = False       # gets its own cards and pages in the shop grid and the sitemap


KINDS = {
    k.code: k
    for k in (
        ProductKind("tee", "T-shirt", price_ceiling=Decimal("40"), on_storefront=True),
        ProductKind("sticker", "Sticker", slug_suffix="-sticker"),
        ProductKind("sweatshirt", "Sweatshirt"),
        ProductKind("mug", "Mug"),
    )
}


def storefront_kinds():
    """The stored codes of the product kinds the shop grid and the sitemap show."""
    return [k.code for k in KINDS.values() if k.on_storefront]


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


# ------------------------------------------------------------------ a listing, as the use cases see it

@dataclass(frozen=True)
class SizeView:
    label: str
    price: Decimal
    catalog_variant_id: str = ""   # the supplier's blank for this size in this colour (set by matching sizes)
    variant_id: str = ""           # the supplier's id for this size of OUR product (set once it is sent)


@dataclass(frozen=True)
class ListingView:
    id: int
    slug: str
    title: str
    color: str
    product_id: str                # the supplier's product, "" until sent
    status: str                    # "draft", "hidden" or "live"
    sizes: tuple                   # SizeView, ...

    @property
    def is_connected(self):
        return bool(self.product_id)


def missing_catalog_sizes(listing):
    """Sizes with no catalogue variant matched yet (needed to build a product)."""
    return [s.label for s in listing.sizes if not s.catalog_variant_id]


def product_external_id(slug, replace=False, stamp=0):
    """Our id for the product at the supplier, unique there. A replacement needs a fresh one (`stamp` makes it so)."""
    return f"{slug}-r{stamp}" if replace else slug


def variant_external_id(product_external, label):
    return f"{product_external}::{label}"


def label_of_variant(variant_external):
    return variant_external.split("::")[-1]


def match_product_variants(variants, color, labels):
    """For each size label, the supplier's id for it among `variants` (the product as the supplier holds it).

    Where the product holds several colours only the listing's own is used; a size that still matches more than
    one variant is left unmatched rather than guessed. Returns ({label: id}, [unmatched labels])."""
    by_label = {}
    for v in variants:
        if not v.size or not v.id:
            continue
        if color and v.color and v.color.lower() != color.lower():
            continue
        by_label.setdefault(v.size.lower(), []).append(v.id)
    matched, unmatched = {}, []
    for label in labels:
        found = by_label.get(label.lower(), [])
        if len(found) == 1:
            matched[label] = found[0]
        else:
            unmatched.append(label)
    return matched, unmatched
