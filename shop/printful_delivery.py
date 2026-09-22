"""Signed, expiring links so Printful's servers can fetch a private design
original (see shop.storage) without any account of their own — they can't sign
in, so a normal auth check is no use here.

A link embeds the design's id and its current file name, signed with Django's
own secret key. `verify_token` re-checks both the signature, the expiry
(PRINTFUL_ARTWORK_LINK_MAX_AGE seconds), and that the artwork hasn't been
replaced since the link was made — a link for a since-replaced or deleted file
stops working immediately, not just once it times out.
"""

from django.conf import settings
from django.core import signing
from django.core.signing import BadSignature, SignatureExpired
from django.urls import reverse

_SALT = "shop.printful-artwork"


def build_delivery_url(design):
    """Absolute URL Printful can fetch `design`'s original from, or None if
    it has no artwork. Freshly signed on every call — call this right before
    handing the URL to Printful, not ahead of time."""
    if not design.artwork:
        return None
    token = signing.dumps({"id": design.pk, "name": design.artwork.name}, salt=_SALT)
    path = reverse("shop:printful_artwork", args=[design.pk, token])
    return settings.SITE_BASE_URL.rstrip("/") + path


def verify_token(pk, token):
    """The Design `token` is a live, matching link for, or None."""
    from .models import Design  # local import: models.py imports this module

    try:
        data = signing.loads(token, salt=_SALT, max_age=settings.PRINTFUL_ARTWORK_LINK_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
    if data.get("id") != pk:
        return None
    design = Design.objects.filter(pk=pk).first()
    if design is None or not design.artwork or design.artwork.name != data.get("name"):
        return None
    return design
