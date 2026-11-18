"""Webhook entry point: print supplier news, and the signed artwork links the supplier fetches."""

import json
import mimetypes

from django.http import FileResponse, Http404, HttpResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from shop import fulfillment


@csrf_exempt
@require_POST
def printful_webhook(request, token):
    """Printful's status events (shipped, returned, failed...). Printful doesn't sign them, so
    the secret in the URL is the only gate: anything without it is a plain 404."""
    import hmac

    from shop.printful import webhook_token

    if not hmac.compare_digest(str(token), webhook_token()):
        raise Http404("Not found")
    try:
        event = json.loads(request.body or b"{}")
    except ValueError:
        return HttpResponseBadRequest("invalid payload")
    if isinstance(event, dict):
        fulfillment.handle_supplier_payload(event)
    return HttpResponse(status=200)


def printful_artwork(request, pk, token):
    """Serve a design's private original to Printful's servers via a signed,
    expiring link (see printful_delivery.py). Deliberately not staff-only:
    Printful can't sign in, so the token itself is the only gate."""
    from tshirtbrand.bootstrap import get_image_tool

    from shop.printful_delivery import verify_link

    found = verify_link(pk, token)
    if found is None:
        raise Http404("This link is invalid or has expired.")
    design, layout = found
    try:
        handle = design.artwork.open("rb")
    except FileNotFoundError:
        raise Http404("The artwork file is missing.")
    if layout:
        try:
            with handle:
                png = get_image_tool().compose(handle.read(), layout)
        except (ValueError, OSError):
            raise Http404("The artwork couldn't be placed.")
        response = HttpResponse(png, content_type="image/png")
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"
        response["X-Robots-Tag"] = "noindex"
        return response
    content_type = mimetypes.guess_type(design.artwork.name)[0] or "application/octet-stream"
    response = FileResponse(handle, content_type=content_type)
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    response["X-Robots-Tag"] = "noindex"
    return response
