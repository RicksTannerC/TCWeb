"""
Session cart.

Keyed by ``"<listing_id>:<size_id>"`` so a tee in M and the same tee in L are
separate lines. A thin wrapper over ``request.session`` — no model yet, since
nothing needs to outlive the session before accounts (Phase 2).
"""

from decimal import Decimal

from .models import Listing, ListingSize

CART_SESSION_KEY = "cart"


class Cart:
    def __init__(self, request):
        self.session = request.session
        cart = self.session.get(CART_SESSION_KEY)
        if cart is None:
            cart = self.session[CART_SESSION_KEY] = {}
        self.cart = cart

    @staticmethod
    def _key(listing_id, size_id):
        return f"{listing_id}:{size_id}"

    def add(self, listing, size, quantity=1):
        key = self._key(listing.id, size.id)
        line = self.cart.setdefault(key, {"quantity": 0})
        line["quantity"] += quantity
        self.save()

    def set_quantity(self, listing_id, size_id, quantity):
        key = self._key(listing_id, size_id)
        if quantity <= 0:
            self.cart.pop(key, None)
        elif key in self.cart:
            self.cart[key]["quantity"] = quantity
        self.save()

    def remove(self, listing_id, size_id):
        self.cart.pop(self._key(listing_id, size_id), None)
        self.save()

    def clear(self):
        self.session[CART_SESSION_KEY] = {}
        self.save()

    def save(self):
        # In-place dict mutation doesn't flip session.modified on its own.
        self.session.modified = True

    def __iter__(self):
        keys = [k.split(":") for k in self.cart]
        listing_ids = {int(k[0]) for k in keys}
        size_ids = {int(k[1]) for k in keys}

        listings = {l.id: l for l in Listing.objects.filter(id__in=listing_ids).select_related("design")}
        sizes = {s.id: s for s in ListingSize.objects.filter(id__in=size_ids)}

        for key, item in self.cart.items():
            lid, sid = (int(x) for x in key.split(":"))
            listing, size = listings.get(lid), sizes.get(sid)
            if not listing or not size:
                continue
            qty = item["quantity"]
            yield {
                "key": key,
                "listing": listing,
                "size": size,
                "quantity": qty,
                "unit_price": size.price,
                "subtotal": size.price * qty,
            }

    def __len__(self):
        return sum(item["quantity"] for item in self.cart.values())

    def get_total(self):
        return sum((row["subtotal"] for row in self), Decimal("0.00"))
