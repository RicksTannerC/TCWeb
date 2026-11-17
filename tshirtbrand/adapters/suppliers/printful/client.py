"""Printful's v1 API, spoken raw: dicts in, dicts out. `supplier.PrintfulSupplier` is the layer that turns this
into the neutral supplier port; nothing outside this package should need Printful's shapes.

`RealPrintful` is the HTTP client. `MockPrintful` returns canned replies of the same shapes so the whole
pipeline runs locally without credentials (nothing leaves the machine)."""

from __future__ import annotations

import hashlib

import httpx

from tshirtbrand.core.fulfilment.ports import SupplierError

BASE_URL = "https://api.printful.com"

# Kept under its old name: the raw client and its callers have always called it this.
PrintfulError = SupplierError


class RealPrintful:
    is_mock = False

    def __init__(self, api_key, transport=None):
        self._http = httpx.Client(
            base_url=BASE_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
            transport=transport,
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

    def print_files(self, blueprint_id):
        return self._get(f"/mockup-generator/printfiles/{blueprint_id}")

    def create_sync_product(self, payload):
        return self._post("/store/products", payload)

    def get_sync_product(self, product_id):
        return self._get(f"/store/products/{product_id}")

    # --- orders ---
    def create_order(self, payload, confirm=False):
        return self._post(f"/orders?confirm={'1' if confirm else '0'}", payload)

    def get_order(self, printful_id):
        return self._get(f"/orders/{printful_id}")

    def cancel_order(self, printful_id):
        return self._unwrap(self._http.delete(f"/orders/{printful_id}"))

    def estimate_shipping(self, payload):
        return self._post("/shipping/rates", payload)

    # --- webhooks ---
    def set_webhook(self, url, types):
        return self._post("/webhooks", {"url": url, "types": types})


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
                {"id": _fake_id(blueprint_id, color, size), "size": size, "color": color, "price": "11.00",
                 "color_code": {"Black": "#0b0b0b", "White": "#ffffff", "Khaki": "#b8a77f"}[color]}
                for color in ["Black", "White", "Khaki"]
                for size in ["S", "M", "L", "XL", "2XL"]
            ],
        }

    def print_files(self, blueprint_id):
        return {"printfiles": [{"printfile_id": 1, "width": 1800, "height": 2400}],
                "variant_printfiles": [{"variant_id": 1, "placements": {"front": 1, "back": 1}}]}

    def get_sync_product(self, product_id):
        return {
            "sync_product": {"id": product_id, "name": "Mock product"},
            "sync_variants": [
                {"id": _fake_id("sv", product_id, color, size), "variant_id": _fake_id(color, size),
                 "size": size, "color": color, "name": f"Mock product - {color} / {size}"}
                for color in ["Black", "White", "Khaki"] for size in ["S", "M", "L", "XL", "2XL"]
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

    def cancel_order(self, printful_id):
        return {"id": printful_id, "status": "canceled"}

    def estimate_shipping(self, payload):
        return [{"id": "STANDARD", "name": "Standard", "rate": "4.69", "currency": "USD"}]

    def set_webhook(self, url, types):
        return {"url": url, "types": types}
