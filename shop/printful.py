"""
Printful API client.

Real HTTP client when ``PRINTFUL_API_KEY`` is set; a deterministic mock
otherwise, so the whole order pipeline (approve -> submit -> status ->
tracking) is exercisable locally without credentials. The mock's shapes
mirror the subset of Printful's v1 API this app touches.
"""

from __future__ import annotations

import hashlib

import httpx
from django.conf import settings

BASE_URL = "https://api.printful.com"


def configured() -> bool:
    return bool(settings.PRINTFUL_API_KEY)


def get_client():
    return RealPrintful() if configured() else MockPrintful()


class PrintfulError(Exception):
    pass


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


def match_variants(blueprint_id, color, size_labels):
    """For a Printful catalog product, find the variant id for each of
    `size_labels` in `color` (case-insensitive, exact match).

    Returns (matches: {label: variant_id str}, unmatched: [label, ...],
    available_colors: [str, ...]) so the caller can explain a mismatch.
    """
    client = get_client()
    data = client.catalog_variants(blueprint_id)
    variants = data.get("variants", [])
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


def sync_listing(listing):
    """
    'Send to Printful': create the sync product from a draft listing's
    artwork + sizes, store the returned ids, and move the listing out of
    'draft' (it is still hidden until the curator publishes it).
    """
    from .models import Status

    client = get_client()
    # print_file_url signs a fresh, short-lived link each call, so it is built
    # right before the API call rather than stored anywhere.
    url = listing.design.print_file_url
    files = [{"url": url}] if url else []
    payload = {
        "sync_product": {"name": listing.design.title, "external_id": listing.slug},
        "sync_variants": [
            {
                "external_id": f"{listing.slug}::{s.label}",
                "variant_id": int(s.printful_variant_id) if s.printful_variant_id else 0,
                "retail_price": str(s.price),
                "files": files,
            }
            for s in listing.sizes.all()
        ],
    }
    result = client.create_sync_product(payload)

    listing.printful_product_id = str(result.get("id", ""))
    for sv in result.get("sync_variants", []):
        label = sv.get("external_id", "").split("::")[-1]
        listing.sizes.filter(label=label).update(printful_variant_id=str(sv.get("id", "")))
    if listing.status == Status.DRAFT:
        listing.status = Status.HIDDEN
    listing.save(update_fields=["printful_product_id", "status", "updated"])
    return result


# --------------------------------------------------------------------- real

class RealPrintful:
    def __init__(self):
        self._http = httpx.Client(
            base_url=BASE_URL,
            headers={"Authorization": f"Bearer {settings.PRINTFUL_API_KEY}"},
            timeout=30,
        )

    def _get(self, path, **params):
        r = self._http.get(path, params=params)
        return self._unwrap(r)

    def _post(self, path, json):
        r = self._http.post(path, json=json)
        return self._unwrap(r)

    @staticmethod
    def _unwrap(r):
        try:
            data = r.json()
        except ValueError:
            raise PrintfulError(f"Non-JSON response ({r.status_code})")
        if r.status_code >= 400 or (isinstance(data, dict) and data.get("error")):
            msg = (data.get("error") or {}).get("message") if isinstance(data, dict) else r.text
            raise PrintfulError(msg or f"HTTP {r.status_code}")
        return data.get("result", data)

    # --- catalogue / products ---
    def list_catalog(self):
        return self._get("/products")

    def catalog_variants(self, blueprint_id):
        return self._get(f"/products/{blueprint_id}")

    def create_sync_product(self, payload):
        return self._post("/store/products", payload)

    # --- orders ---
    def create_order(self, payload, confirm=False):
        return self._post(f"/orders?confirm={'1' if confirm else '0'}", payload)

    def get_order(self, printful_id):
        return self._get(f"/orders/{printful_id}")

    def estimate_shipping(self, payload):
        return self._post("/shipping/rates", payload)

    # --- webhooks ---
    def set_webhook(self, url, types):
        return self._post("/webhooks", {"url": url, "types": types})


# --------------------------------------------------------------------- mock

def _fake_id(*parts) -> int:
    h = hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()
    return 40000000 + int(h[:7], 16) % 9000000


class MockPrintful:
    """Canned responses. Nothing leaves the machine."""

    is_mock = True

    _CATALOG = [
        {"id": 456, "title": "Unisex Organic Cotton Creator 2.0 T-Shirt | Stanley/Stella STTU169",
         "model": "STTU169", "brand": "Stanley/Stella"},
        {"id": 71, "title": "Unisex Staple T-Shirt | Bella + Canvas 3001",
         "model": "3001", "brand": "Bella + Canvas"},
        {"id": 145, "title": "Unisex Heavy Cotton Tee | Gildan 5000",
         "model": "5000", "brand": "Gildan"},
    ]

    def list_catalog(self):
        return self._CATALOG

    def catalog_variants(self, blueprint_id):
        product = next((p for p in self._CATALOG if p["id"] == blueprint_id),
                        {"id": blueprint_id, "title": "Mock blank"})
        return {
            "product": product,
            "variants": [
                {"id": _fake_id(blueprint_id, color, size), "size": size, "color": color, "price": "11.00"}
                for color in ["Black", "White", "Khaki"]
                for size in ["S", "M", "L", "XL", "2XL"]
            ],
        }

    def create_sync_product(self, payload):
        name = payload.get("sync_product", {}).get("name", "product")
        pid = _fake_id("sync", name)
        variants = payload.get("sync_variants", [])
        return {
            "id": pid,
            "external_id": payload.get("sync_product", {}).get("external_id", ""),
            "sync_variants": [
                {
                    "id": _fake_id(pid, v.get("external_id", i)),
                    "external_id": v.get("external_id", ""),
                    "variant_id": v.get("variant_id"),
                    "retail_price": v.get("retail_price"),
                }
                for i, v in enumerate(variants)
            ],
            "mockups": [
                {"placement": "front", "mockup_url": f"https://example.invalid/mockup/{pid}.png"}
            ],
        }

    def create_order(self, payload, confirm=False):
        ref = payload.get("external_id", "order")
        return {
            "id": _fake_id("order", ref),
            "external_id": ref,
            "status": "pending" if confirm else "draft",
            "costs": {"subtotal": "0.00", "shipping": "0.00", "total": "0.00"},
        }

    def get_order(self, printful_id):
        return {"id": printful_id, "status": "pending", "shipments": []}

    def estimate_shipping(self, payload):
        return [{"id": "STANDARD", "name": "Standard", "rate": "4.69", "currency": "USD"}]

    def set_webhook(self, url, types):
        return {"url": url, "types": types}
