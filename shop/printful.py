"""
Printful API client.

Real HTTP client when ``PRINTFUL_API_KEY`` is set; a deterministic mock
otherwise, so the whole order pipeline (approve -> submit -> status ->
tracking) is exercisable locally without credentials. The mock's shapes
mirror the subset of Printful's v1 API this app touches.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from django.conf import settings

# The raw Printful clients live in the supplier adapter now (docs/ARCHITECTURE.md); they are re-exported here
# so the rest of the shop keeps working while its callers move onto the supplier port one at a time.
from tshirtbrand.adapters.suppliers.printful.client import (  # noqa: F401
    BASE_URL, MockPrintful, PrintfulError, RealPrintful,
)


def configured() -> bool:
    # settings.TESTING is a hard guarantee: the test suite always gets the
    # mock, regardless of what happens to be in the environment. See its
    # definition in config/settings.py for why this exists.
    if settings.TESTING:
        return False
    return bool(settings.PRINTFUL_API_KEY)


def get_client():
    return RealPrintful(settings.PRINTFUL_API_KEY) if configured() else MockPrintful()


CATALOG_CACHE_SECONDS = 60 * 60  # Printful's blank catalog barely changes; avoid refetching it on every search.


def search_catalog(query):
    """Printful's own catalog listing has no server-side search, so this
    fetches the full list (cached) and filters client-side by name/model/brand."""
    from django.core.cache import cache

    query = (query or "").strip().lower()
    if len(query) < 2:
        return []
    client = get_client()
    cache_key = "printful:catalog:mock" if getattr(client, "is_mock", False) else "printful:catalog"
    catalog = cache.get(cache_key)
    if catalog is None:
        catalog = client.list_catalog()
        cache.set(cache_key, catalog, CATALOG_CACHE_SECONDS)
    return [
        p for p in catalog
        if query in str(p.get("title") or "").lower()
        or query in str(p.get("model") or "").lower()
        or query in str(p.get("brand") or "").lower()
    ][:25]


def _cached_variants(blueprint_id):
    """This product's real variants (cached) -- shared by the color dropdown
    and size matching so opening a listing and then matching its sizes only
    costs one real fetch per product per hour, not two."""
    from django.core.cache import cache

    client = get_client()
    cache_key = f"printful:variants:{'mock' if getattr(client, 'is_mock', False) else 'real'}:{blueprint_id}"
    data = cache.get(cache_key)
    if data is None:
        data = client.catalog_variants(blueprint_id)
        cache.set(cache_key, data, CATALOG_CACHE_SECONDS)
    return data


def print_area(blueprint_id, placement):
    """The real print-file size (width, height in px) of a product's placement, from Printful's
    printfiles info (cached). Falls back to the 1800x2400 used by the shirts in use, so a failed
    lookup never blocks a send. A read-only call, made only while building a positioned print."""
    from django.core.cache import cache

    from .models import DEFAULT_PRINT_AREA

    if not blueprint_id:
        return DEFAULT_PRINT_AREA
    client = get_client()
    cache_key = f"printful:printfiles:{'mock' if getattr(client, 'is_mock', False) else 'real'}:{blueprint_id}"
    by_placement = cache.get(cache_key)
    try:
        if by_placement is None:
            data = client.print_files(blueprint_id)
            sizes = {p["printfile_id"]: (int(p["width"]), int(p["height"])) for p in data.get("printfiles") or []}
            by_placement = {}
            for vp in data.get("variant_printfiles") or []:
                for name, file_id in (vp.get("placements") or {}).items():
                    if file_id in sizes:
                        by_placement.setdefault(str(name), sizes[file_id])
            cache.set(cache_key, by_placement, CATALOG_CACHE_SECONDS)
        return by_placement.get(str(placement), DEFAULT_PRINT_AREA)
    except Exception:  # noqa: BLE001 - an unreadable reply or an odd cache must never block a send
        return DEFAULT_PRINT_AREA


def _regions(obj):
    """Region codes named in a Printful availability field, whichever of its
    shapes it arrives in: a list of {"region": ..., "status": ...} or a
    {"US": "United States", ...} mapping."""
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


def us_production(blueprint_id):
    """Whether this Printful product can be made and shipped from the US.

    True / False, or None when Printful's data doesn't say (no product, an
    error, or no availability info) -- callers should only warn on False.
    Uses the variants already fetched for the color dropdown, so it costs no
    extra Printful call. A product made only in the EU/UK will be produced
    there and shipped to a US customer: slower, pricier, and subject to customs.
    """
    if not blueprint_id:
        return None
    try:
        data = _cached_variants(blueprint_id)
    except PrintfulError:
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


_HEX_RE = re.compile(r"#?([0-9a-fA-F]{6})")


def _clean_hex(value):
    """'#RRGGBB' from whatever Printful sent, or '' -- only ever six hex digits, because
    this ends up inside a style attribute."""
    m = _HEX_RE.fullmatch(str(value or "").strip())
    return f"#{m.group(1).lower()}" if m else ""


def _clean_image_url(value):
    """An https image URL as Printful sent it, or '' -- anything else is dropped."""
    v = str(value or "").strip()
    if not (v.startswith("https://") and len(v) < 500 and not re.search(r"[\s\"'<>]", v)):
        return ""
    # Printful sends the bare CDN host ("https://files.cdn.printful.com/") as a product's
    # thumbnail until it has drawn one: that is not an image
    return v if urlsplit(v).path.strip("/") else ""


def _swatch_css(hex1, hex2):
    if hex1 and hex2 and hex2 != hex1:
        return f"linear-gradient(135deg, {hex1} 50%, {hex2} 50%)"
    return hex1


def catalog_color_options(blueprint_id):
    """Each color of a Printful product, for the listing's color picker:
    [{"name", "hex", "hex2", "swatch" (css background), "image" (https photo of
    that color)}], sorted by name. Built from the variants already fetched for
    the color list, so it costs no extra Printful call. hex/image are '' when
    Printful didn't provide them."""
    if not blueprint_id:
        return []
    found = {}
    for v in _cached_variants(blueprint_id).get("variants", []):
        name = str(v.get("color") or "").strip()
        if not name:
            continue
        opt = found.setdefault(name, {"name": name, "hex": "", "hex2": "", "image": ""})
        opt["hex"] = opt["hex"] or _clean_hex(v.get("color_code"))
        opt["hex2"] = opt["hex2"] or _clean_hex(v.get("color_code2"))
        opt["image"] = opt["image"] or _clean_image_url(v.get("image"))
    options = sorted(found.values(), key=lambda o: o["name"].lower())
    for o in options:
        o["swatch"] = _swatch_css(o["hex"], o["hex2"])
    return options


def dashboard_product_url(product_name, product_type="tee"):
    """Best-effort link to this blank's page in the Printful dashboard (where its
    colors are shown on the real shirt), built from the pattern of a real link:
    /dashboard/custom/mens/t-shirts/<title-slug>?color=<Color>. Returns '' for
    anything but a tee or when the name is unknown. Printful doesn't publish this
    URL in its API, so it is a constructed link, not a looked-up one."""
    if product_type != "tee":
        return ""
    slug = re.sub(r"[^a-z0-9]+", "-", str(product_name or "").lower().replace("/", " ")).strip("-")
    if not slug:
        return ""
    return f"https://www.printful.com/dashboard/custom/mens/t-shirts/{slug}"


def catalog_colors(blueprint_id):
    """Real color options for a Printful catalog product, for a dropdown."""
    if not blueprint_id:
        return []
    variants = _cached_variants(blueprint_id).get("variants", [])
    return sorted({v.get("color", "") for v in variants if v.get("color")})


def match_variants(blueprint_id, color, size_labels):
    """For a Printful catalog product, find the variant id for each of
    `size_labels` in `color` (case-insensitive, exact match).

    Returns (matches: {label: variant_id str}, unmatched: [label, ...],
    available_colors: [str, ...]) so the caller can explain a mismatch.
    """
    variants = _cached_variants(blueprint_id).get("variants", [])
    available_colors = sorted({v.get("color", "") for v in variants if v.get("color")})
    color_l = (color or "").strip().lower()
    in_color = [v for v in variants if v.get("color", "").strip().lower() == color_l]

    matches, unmatched = {}, []
    for label in size_labels:
        hit = next((v for v in in_color if v.get("size", "").strip().lower() == label.strip().lower()), None)
        if hit and hit.get("id") is not None:
            matches[label] = str(hit["id"])
        else:
            unmatched.append(label)
    return matches, unmatched, available_colors


WEBHOOK_TYPES = [
    "package_shipped", "package_returned", "order_failed", "order_canceled", "order_put_hold", "order_updated",
]


def webhook_token():
    """The secret that goes in the webhook URL. Printful's v1 webhooks aren't signed, so
    the URL itself has to be unguessable. It is derived from SECRET_KEY (HMAC, so the
    key can't be recovered from it); rotating SECRET_KEY changes it, and the webhook
    then has to be registered again (manage.py printful_webhook --register)."""
    import hashlib
    import hmac

    return hmac.new(settings.SECRET_KEY.encode(), b"printful-webhook-v1", hashlib.sha256).hexdigest()[:40]


def webhook_url():
    from django.urls import reverse

    return settings.SITE_BASE_URL.rstrip("/") + reverse("shop:printful_webhook", args=[webhook_token()])


def missing_catalog_sizes(listing):
    """Sizes with no catalogue variant matched yet (needed to build a product)."""
    return [s.label for s in listing.sizes.all() if not s.printful_catalog_variant_id]


def sync_listing(listing, *, replace=False):
    """
    'Send to Printful': create the sync product from a listing's artwork +
    sizes, store the returned ids, and move the listing out of 'draft' (it is
    still hidden until the curator publishes it).

    replace=True builds a brand-new product (fresh external ids, since Printful
    wants those unique) and points the listing at it. The old product is left
    in the Printful store untouched, for the curator to delete by hand.
    """
    import time

    from .models import Status

    client = get_client()
    # Each artwork link is signed fresh and short-lived on every call, so the
    # entries are built right before the API call rather than stored anywhere.
    files = listing.print_file_entries()
    ext = f"{listing.slug}-r{int(time.time())}" if replace else listing.slug
    payload = {
        "sync_product": {"name": listing.design.title, "external_id": ext},
        "sync_variants": [
            {
                "external_id": f"{ext}::{s.label}",
                "variant_id": int(s.printful_catalog_variant_id) if s.printful_catalog_variant_id else 0,
                "retail_price": str(s.price),
                "files": files,
            }
            for s in listing.sizes.all()
        ],
    }
    result = client.create_sync_product(payload)

    # Printful's real reply nests the product as {"sync_product": {"id": ...},
    # "sync_variants": [...]}; the mock returns the id at the top level.
    product = result.get("sync_product") or result
    listing.printful_product_id = str(product.get("id", ""))

    # A size's variant id belongs to ONE Printful product. On a re-send the old
    # product's ids must not survive (an order would be made from the old shirt),
    # so clear them and fill in the new product's.
    listing.sizes.update(printful_variant_id="")
    reply_variants = result.get("sync_variants") or []
    for sv in reply_variants:
        label = sv.get("external_id", "").split("::")[-1]
        listing.sizes.filter(label=label).update(printful_variant_id=str(sv.get("id", "")))
    if not reply_variants and listing.printful_product_id:
        # Printful's reply to "create product" is only a summary (no per-size ids), so
        # read the product back -- a read-only call on the product just created. If it
        # fails the sizes stay blank (never stale) and Refresh sizes from Printful fixes it.
        try:
            refresh_sync_variants(listing)
        except PrintfulError:
            pass
    if listing.status == Status.DRAFT:
        listing.status = Status.HIDDEN
    listing.printful_sent_blueprint_id = listing.template.printful_blueprint_id
    listing.printful_sent_color = listing.color
    listing.printful_sent_placement = listing.effective_print_placement
    listing.printful_sent_prints = listing.print_signature()
    listing.save(update_fields=["printful_product_id", "status", "updated", "printful_sent_blueprint_id",
                                "printful_sent_color", "printful_sent_placement", "printful_sent_prints"])
    return result


def _sync_variant_size_color(sv, slug=""):
    """(size, color) of a Printful sync variant, from whichever fields it has:
    our own external_id ("slug::M"), explicit size/color, or the name
    ("Title - Khaki / M")."""
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


def extract_previews(result, color=""):
    """Printful's own renders of the art on the blank, from a sync-product reply:
    [{"label", "url"}] (https only, at most 6). Uses the product thumbnail plus the
    `preview` file(s) of the first variant in the listing's colour (sizes of one
    colour look alike). Anything unexpected yields fewer images, never an error."""
    if not isinstance(result, dict):
        return []
    out, seen = [], set()

    def add(label, url):
        url = _clean_image_url(url)
        if url and url not in seen and len(out) < 6:
            seen.add(url)
            out.append({"label": label, "url": url})

    product = result.get("sync_product")
    if isinstance(product, dict):
        add("Product thumbnail", product.get("thumbnail_url"))

    wanted = (color or "").strip().lower()
    chosen = None
    for sv in result.get("sync_variants") or []:
        if not isinstance(sv, dict):
            continue
        _, sv_color = _sync_variant_size_color(sv)
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
    return out


def store_previews(listing, result):
    from django.utils import timezone

    listing.printful_preview = extract_previews(result, listing.color)
    listing.printful_preview_checked = timezone.now()
    listing.save(update_fields=["printful_preview", "printful_preview_checked"])
    return listing.printful_preview


def refresh_preview(listing):
    """Re-read this listing's product from Printful (read-only) and keep its preview images.
    Returns how many were found."""
    if not listing.printful_product_id:
        raise PrintfulError("This listing isn't connected to a Printful product yet.")
    return len(store_previews(listing, get_client().get_sync_product(listing.printful_product_id)))


def refresh_sync_variants(listing):
    """Re-read this listing's product from Printful (read-only) and store each
    size's real *sync variant* id. Returns (matched labels, unmatched labels).

    Where the product holds several colors, only the listing's own color is
    used; a size that still matches more than one variant is left unmatched
    rather than guessed."""
    if not listing.printful_product_id:
        raise PrintfulError("This listing isn't connected to a Printful product yet.")
    result = get_client().get_sync_product(listing.printful_product_id)
    variants = result.get("sync_variants", []) if isinstance(result, dict) else []
    if isinstance(result, dict):
        store_previews(listing, result)

    sizes = list(listing.sizes.all())
    by_label = {}
    for sv in variants:
        size, color = _sync_variant_size_color(sv)
        if not size or not sv.get("id"):
            continue
        if listing.color and color and color.lower() != listing.color.lower():
            continue
        by_label.setdefault(size.lower(), []).append(str(sv["id"]))

    matched, unmatched = [], []
    for s in sizes:
        found = by_label.get(s.label.lower(), [])
        if len(found) == 1:
            s.printful_variant_id = found[0]
            s.save(update_fields=["printful_variant_id"])
            matched.append(s.label)
        else:
            unmatched.append(s.label)
    return matched, unmatched
