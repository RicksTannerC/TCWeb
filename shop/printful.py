"""
Printful settings and wiring for the shop.

The Printful API itself (raw client, canned mock, and the translation to the neutral supplier port) lives in
tshirtbrand/adapters/suppliers/printful. What stays here is the part that needs Django settings:

* `get_client()` -- the real client when ``PRINTFUL_API_KEY`` is set, the canned mock otherwise, so the whole
  order pipeline is exercisable locally without credentials;
* the webhook URL and its secret token.

Callers that need to *do* something at the supplier go through `tshirtbrand.bootstrap.get_supplier()`.
"""

from __future__ import annotations

from django.conf import settings

# Re-exported so existing imports keep working while callers move onto the supplier port.
from tshirtbrand.adapters.suppliers.printful.client import (  # noqa: F401
    BASE_URL, MockPrintful, PrintfulError, RealPrintful,
)
from tshirtbrand.adapters.suppliers.printful.supplier import WEBHOOK_TYPES  # noqa: F401


def configured() -> bool:
    # settings.TESTING is a hard guarantee: the test suite always gets the
    # mock, regardless of what happens to be in the environment. See its
    # definition in config/settings.py for why this exists.
    if settings.TESTING:
        return False
    return bool(settings.PRINTFUL_API_KEY)


def get_client():
    return RealPrintful(settings.PRINTFUL_API_KEY) if configured() else MockPrintful()


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
