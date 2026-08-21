from decimal import Decimal
from .models import Product

CART_SESSION_KEY = "cart"


class Cart:
    """
    Thin wrapper around request.session that knows how to add/remove
    products and compute totals. Same role as a `cart.py` you'd find
    in most Django e-commerce tutorials — no cart app is heavy enough
    to need its own model yet, since nothing here needs to survive
    past the session (no accounts, no persistent orders in this pilot).
    """

    def __init__(self, request):
        self.session = request.session
        cart = self.session.get(CART_SESSION_KEY)
        if cart is None:
            cart = self.session[CART_SESSION_KEY] = {}
        self.cart = cart

    def add(self, product, quantity=1):
        product_id = str(product.id)
        if product_id not in self.cart:
            self.cart[product_id] = {"quantity": 0}
        self.cart[product_id]["quantity"] += quantity
        self.save()

    def remove(self, product):
        product_id = str(product.id)
        if product_id in self.cart:
            del self.cart[product_id]
            self.save()

    def save(self):
        # Session middleware only re-saves the session if it sees
        # `session.modified = True`. Mutating a dict in place (as
        # add()/remove() do above) doesn't trigger that automatically,
        # so we set it explicitly — this is the equivalent of Node's
        # express-session auto-detecting the mutation for you.
        self.session.modified = True

    def __iter__(self):
        product_ids = self.cart.keys()
        products = Product.objects.filter(id__in=product_ids)
        products_map = {str(p.id): p for p in products}

        for product_id, item in self.cart.items():
            product = products_map.get(product_id)
            if not product:
                continue
            quantity = item["quantity"]
            yield {
                "product": product,
                "quantity": quantity,
                "subtotal": product.price * quantity,
            }

    def __len__(self):
        return sum(item["quantity"] for item in self.cart.values())

    def get_total(self):
        return sum((item["subtotal"] for item in self), Decimal("0.00"))

    def clear(self):
        self.session[CART_SESSION_KEY] = {}
        self.save()
