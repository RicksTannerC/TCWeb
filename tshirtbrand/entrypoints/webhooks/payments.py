"""Webhook entry point: payment confirmations."""

from django.http import HttpResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from shop import payments
from shop.emails import send_order_confirmation
from tshirtbrand.core.payments.api import PaymentError


@csrf_exempt
@require_POST
def stripe_webhook(request):
    try:
        event = payments.parse_event(request.body, request.META.get("HTTP_STRIPE_SIGNATURE", ""))
    except PaymentError:  # bad signature / malformed
        return HttpResponseBadRequest("invalid payload")

    if event is not None:
        order, created = payments.fulfill_from_event(event)
        if order and created:
            try:
                send_order_confirmation(order)
            except Exception:  # noqa: BLE001
                pass

    return HttpResponse(status=200)
