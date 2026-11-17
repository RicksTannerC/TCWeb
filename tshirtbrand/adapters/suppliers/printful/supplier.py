"""Printful as a `Supplier`: neutral requests in, Printful's wire format out, and back again.

Everything Printful-shaped lives here (field names, nesting, id types, event names, wording)."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

from tshirtbrand.core.fulfilment.api import (
    CatalogProduct, ColorOption, EventKind, OrderRequest, PrintArea, Preview, ProductRecord, ProductSpec,
    ProductVariant, SizeMatch, SubmittedOrder, SupplierError, SupplierEvent,
)

CACHE_SECONDS = 60 * 60  # Printful's blank catalog barely changes; avoid refetching it on every search

# Printful's webhook event names, for the neutral kinds we subscribe to
WEBHOOK_TYPES = [
    "package_shipped", "package_returned", "order_failed", "order_canceled", "order_put_hold", "order_updated",
]

_HEX_RE = re.compile(r"#?([0-9a-fA-F]{6})")


class _DictCache:
    """Used when no shared cache is supplied (tests, scripts)."""

    def __init__(self):
        self._d = {}

    def get(self, key, default=None):
        return self._d.get(key, default)

    def set(self, key, value, timeout=None):
        self._d[key] = value


class PrintfulSupplier:
    name = "Printful"

    def __init__(self, client, cache=None):
        self._client = client
        self._cache = cache if cache is not None else _DictCache()
        self.simulated = bool(getattr(client, "is_mock", False))
        self._kind = "mock" if self.simulated else "real"

    # ----------------------------------------------------------- catalogue

    def search_catalog(self, query):
        """Printful's own catalog listing has no server-side search, so this fetches the full list
        (cached) and filters by name/model/brand."""
        query = (query or "").strip().lower()
        if len(query) < 2:
            return []
        key = "printful:catalog:mock" if self.simulated else "printful:catalog"
        catalog = self._cache.get(key)
        if catalog is None:
            catalog = self._client.list_catalog()
            self._cache.set(key, catalog, CACHE_SECONDS)
        hits = [
            p for p in catalog
            if query in str(p.get("title") or "").lower()
            or query in str(p.get("model") or "").lower()
            or query in str(p.get("brand") or "").lower()
        ][:25]
        return [CatalogProduct(id=str(p.get("id")), title=str(p.get("title") or ""),
                               model=str(p.get("model") or ""), brand=str(p.get("brand") or "")) for p in hits]

    def _variants(self, catalog_id):
        """This product's real variants (cached), shared by the colour list and size matching."""
        key = f"printful:variants:{self._kind}:{catalog_id}"
        data = self._cache.get(key)
        if data is None:
            data = self._client.catalog_variants(int(catalog_id) if str(catalog_id).isdigit() else catalog_id)
            self._cache.set(key, data, CACHE_SECONDS)
        return data

    def colors(self, catalog_id):
        if not catalog_id:
            return []
        found = {}
        for v in self._variants(catalog_id).get("variants", []):
            name = str(v.get("color") or "").strip()
            if not name:
                continue
            opt = found.setdefault(name, {"hex": "", "hex2": "", "image": ""})
            opt["hex"] = opt["hex"] or _clean_hex(v.get("color_code"))
            opt["hex2"] = opt["hex2"] or _clean_hex(v.get("color_code2"))
            opt["image"] = opt["image"] or _clean_image_url(v.get("image"))
        return [ColorOption(name=n, **found[n]) for n in sorted(found, key=str.lower)]

    def match_sizes(self, catalog_id, color, sizes):
        variants = self._variants(catalog_id).get("variants", [])
        available = tuple(sorted({v.get("color", "") for v in variants if v.get("color")}))
        color_l = (color or "").strip().lower()
        in_color = [v for v in variants if v.get("color", "").strip().lower() == color_l]
        matches, unmatched = {}, []
        for label in sizes:
            hit = next((v for v in in_color if v.get("size", "").strip().lower() == label.strip().lower()), None)
            if hit and hit.get("id") is not None:
                matches[label] = str(hit["id"])
            else:
                unmatched.append(label)
        return SizeMatch(matches=matches, unmatched=tuple(unmatched), available_colors=available)

    def print_area(self, catalog_id, placement):
        """Printful's printfiles info (cached). None when it can't be read or doesn't list the placement."""
        if not catalog_id:
            return None
        key = f"printful:printfiles:{self._kind}:{catalog_id}"
        try:
            by_placement = self._cache.get(key)
            if by_placement is None:
                data = self._client.print_files(int(catalog_id) if str(catalog_id).isdigit() else catalog_id)
                sizes = {p["printfile_id"]: (int(p["width"]), int(p["height"])) for p in data.get("printfiles") or []}
                by_placement = {}
                for vp in data.get("variant_printfiles") or []:
                    for name, file_id in (vp.get("placements") or {}).items():
                        if file_id in sizes:
                            by_placement.setdefault(str(name), sizes[file_id])
                self._cache.set(key, by_placement, CACHE_SECONDS)
            size = by_placement.get(str(placement))
            return PrintArea(*size) if size else None
        except Exception:  # noqa: BLE001 - an unreadable reply or an odd cache must never block a send
            return None

    def made_in_us(self, catalog_id):
        if not catalog_id:
            return None
        try:
            data = self._variants(catalog_id)
        except SupplierError:
            return None
        regions = set()
        product = data.get("product") if isinstance(data, dict) else None
        if isinstance(product, dict):
            regions |= _regions(product.get("availability_regions"))
        for v in (data.get("variants", []) if isinstance(data, dict) else []):
            regions |= _regions(v.get("availability_status"))
            regions |= _regions(v.get("availability_regions"))
        if not regions:
            return None
        return "US" in regions

    # ----------------------------------------------------------- products

    def create_product(self, spec: ProductSpec, color=""):
        payload = {
            "sync_product": {"name": spec.name, "external_id": spec.external_id},
            "sync_variants": [
                {
                    "external_id": v.external_id,
                    "variant_id": int(v.catalog_variant_id) if v.catalog_variant_id else 0,
                    "retail_price": str(v.retail_price),
                    "files": [_file(f) for f in v.files],
                }
                for v in spec.variants
            ],
        }
        return _record(self._client.create_sync_product(payload), color)

    def get_product(self, product_id, color=""):
        return _record(self._client.get_sync_product(product_id), color)

    # ----------------------------------------------------------- orders

    def submit_order(self, order: OrderRequest):
        r = order.recipient
        payload = {
            "external_id": order.external_id,
            "recipient": {
                "name": r.name, "email": r.email, "address1": r.address1, "address2": r.address2,
                "city": r.city, "state_code": r.region, "country_code": r.country, "zip": r.postal_code,
            },
            "items": [_order_line(line) for line in order.lines],
        }
        result = self._client.create_order(payload, confirm=True)
        costs = result.get("costs") if isinstance(result, dict) else None
        total, tax = None, Decimal("0.00")
        if isinstance(costs, dict):
            amount = _money(costs.get("total"))
            if amount is not None and amount > 0:  # an order never really costs nothing: not a recorded cost
                total = amount
                # Printful reports sales tax as `tax` and VAT as `vat`; both are tax we paid
                tax = (_money(costs.get("tax")) or Decimal("0.00")) + (_money(costs.get("vat")) or Decimal("0.00"))
        return SubmittedOrder(supplier_order_id=str(result.get("id", "")), status=str(result.get("status", "")),
                              cost_total=total, cost_tax=tax)

    def cancel_order(self, supplier_order_id):
        self._client.cancel_order(supplier_order_id)

    # ----------------------------------------------------------- events

    def register_events(self, url):
        self._client.set_webhook(url, WEBHOOK_TYPES)
        return list(WEBHOOK_TYPES)

    def parse_event(self, payload):
        try:
            return self._parse_event(payload)
        except Exception:  # noqa: BLE001 - hostile or odd input is simply "not an event"
            return None

    def _parse_event(self, payload):
        if not isinstance(payload, dict):
            return None
        etype = payload.get("type", "")
        data = payload.get("data") or {}
        order = data.get("order") or data
        base = {"supplier_order_id": str(order.get("id", "")), "external_id": str(order.get("external_id", ""))}
        if etype == "package_shipped":
            s = data.get("shipment") or {}
            return SupplierEvent(EventKind.SHIPPED, tracking_number=s.get("tracking_number", ""),
                                 tracking_url=s.get("tracking_url", ""), carrier=s.get("carrier", ""), **base)
        if etype == "order_updated" and (data.get("order") or {}).get("status") == "inprocess":
            return SupplierEvent(EventKind.IN_PRODUCTION, **base)
        if etype == "package_returned":
            return SupplierEvent(EventKind.RETURNED, reason="Package returned to sender.", **base)
        if etype in ("order_failed", "order_put_hold"):
            kind = EventKind.FAILED if etype == "order_failed" else EventKind.ON_HOLD
            return SupplierEvent(kind, reason=data.get("reason", "Printful placed the order on hold."), **base)
        if etype == "order_canceled":
            return SupplierEvent(EventKind.CANCELED, reason="Printful canceled the order.", **base)
        return None


# ---------------------------------------------------------------- wire helpers

def _file(f):
    entry = {"url": f.url, "type": f.placement}
    if f.box:
        b = f.box
        entry["position"] = {"area_width": b.area_width, "area_height": b.area_height, "width": b.width,
                             "height": b.height, "top": b.top, "left": b.left}
    return entry


def _order_line(line):
    out = {"quantity": line.quantity, "name": line.name, "retail_price": str(line.unit_price)}
    if line.product_variant_id:
        out["sync_variant_id"] = int(line.product_variant_id)
    else:
        # not synced yet: order straight off the catalog variant, with the art attached
        out["variant_id"] = int(line.catalog_variant_id)
        out["files"] = [_file(f) for f in line.files]
    return out


def _money(value):
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _clean_hex(value):
    """'#RRGGBB' from whatever Printful sent, or '': only ever six hex digits, because this ends up
    inside a style attribute."""
    m = _HEX_RE.fullmatch(str(value or "").strip())
    return f"#{m.group(1).lower()}" if m else ""


def _clean_image_url(value):
    """An https image URL as Printful sent it, or '': anything else is dropped."""
    v = str(value or "").strip()
    if not (v.startswith("https://") and len(v) < 500 and not re.search(r"[\s\"'<>]", v)):
        return ""
    # Printful sends the bare CDN host ("https://files.cdn.printful.com/") as a product's thumbnail
    # until it has drawn one: that is not an image
    return v if urlsplit(v).path.strip("/") else ""


def _regions(obj):
    """Region codes named in a Printful availability field, in either of its shapes: a list of
    {"region": ..., "status": ...} or a {"US": "United States", ...} mapping."""
    found = set()
    if isinstance(obj, dict):
        found.update(str(k).upper() for k in obj)
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, dict):
                r = item.get("region") or item.get("code")
                status = str(item.get("status", "")).lower()
                if r and status not in ("discontinued", "not_available", "unavailable"):
                    found.add(str(r).upper())
            elif isinstance(item, str):
                found.add(item.upper())
    return found


def _size_color(sv):
    """(size, color) of a Printful sync variant, from whichever fields it has: our own external_id
    ("slug::M"), explicit size/color, or the name ("Title - Khaki / M")."""
    size = color = ""
    ext = str(sv.get("external_id") or "")
    if "::" in ext:
        size = ext.split("::")[-1]
    size = size or str(sv.get("size") or "")
    color = str(sv.get("color") or "")
    if not size:
        parts = [p.strip() for p in str(sv.get("name") or "").split("/")]
        if len(parts) >= 2:
            size = parts[-1]
            color = color or parts[-2].split(" - ")[-1].strip()
    return size.strip(), color.strip()


def _previews(result, color):
    """Printful's own renders of the art on the blank: the product thumbnail plus the `preview` file(s)
    of the first variant in the wanted colour (sizes of one colour look alike). At most 6, https only.
    Anything unexpected yields fewer images, never an error."""
    out, seen = [], set()

    def add(label, url):
        url = _clean_image_url(url)
        if url and url not in seen and len(out) < 6:
            seen.add(url)
            out.append(Preview(label, url))

    product = result.get("sync_product")
    if isinstance(product, dict):
        add("Product thumbnail", product.get("thumbnail_url"))
    wanted = (color or "").strip().lower()
    chosen = None
    for sv in result.get("sync_variants") or []:
        if not isinstance(sv, dict):
            continue
        _, sv_color = _size_color(sv)
        if wanted and sv_color and sv_color.lower() != wanted:
            continue
        previews = [f for f in (sv.get("files") or []) if isinstance(f, dict) and f.get("type") == "preview"]
        if previews:
            chosen = (sv_color, previews)
            break
    if chosen:
        sv_color, previews = chosen
        for n, f in enumerate(previews, 1):
            add(f"{sv_color or 'Preview'}" + (f" ({n})" if len(previews) > 1 else ""),
                f.get("preview_url") or f.get("thumbnail_url"))
    return tuple(out)


def _record(result, color=""):
    """A Printful product reply as a ProductRecord. The real reply nests the product as
    {"sync_product": {"id": ...}, "sync_variants": [...]}; the mock (and Printful's create summary)
    return the id at the top level."""
    if not isinstance(result, dict):
        raise SupplierError("Printful sent an unreadable product reply.")
    product = result.get("sync_product") or result
    variants = []
    for sv in result.get("sync_variants") or []:
        if not isinstance(sv, dict):
            continue
        size, sv_color = _size_color(sv)
        variants.append(ProductVariant(id=str(sv.get("id") or ""), external_id=str(sv.get("external_id") or ""),
                                       size=size, color=sv_color))
    return ProductRecord(product_id=str(product.get("id", "")), variants=tuple(variants),
                         previews=_previews(result, color))
