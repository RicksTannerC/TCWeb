from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse


def _abs(path):
    base = getattr(settings, "SITE_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    return f"{base}{path}"


def send_order_confirmation(order):
    ctx = {
        "order": order,
        "shop_name": settings.SHOP_NAME,
        "postal_address": settings.SHOP_POSTAL_ADDRESS,
        "track_url": _abs(reverse("shop:order_track", args=[order.track_token])),
        "shop_url": _abs(reverse("shop:index")),
        "subscribe_url": _abs(reverse("shop:subscribe")),
    }
    body = render_to_string("shop/email/order_confirmation.txt", ctx)
    send_mail(
        subject=f"{settings.SHOP_NAME} — order {order.reference} confirmed",
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[order.email],
        fail_silently=False,
    )


def send_subscribe_welcome(subscriber):
    ctx = {
        "shop_name": settings.SHOP_NAME,
        "postal_address": settings.SHOP_POSTAL_ADDRESS,
        "shop_url": _abs(reverse("shop:index")),
        "unsubscribe_url": _abs(
            reverse("shop:unsubscribe", args=[subscriber.unsubscribe_token])
        ),
    }
    body = render_to_string("shop/email/subscribe_welcome.txt", ctx)
    send_mail(
        subject=f"{settings.SHOP_NAME} — you're on the list",
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[subscriber.email],
        fail_silently=True,
    )
