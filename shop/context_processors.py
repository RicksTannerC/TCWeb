from .cart import Cart


def cart(request):
    c = Cart(request)
    return {"cart": c, "cart_count": len(c)}
