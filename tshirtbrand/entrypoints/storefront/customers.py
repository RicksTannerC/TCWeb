"""The storefront: the mailing list, order tracking and the contact form."""

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from shop.emails import send_subscribe_welcome
from shop.orders import Order, Subscriber


@require_POST
def subscribe(request):
    email = request.POST.get("email", "").strip().lower()
    if not email or "@" not in email:
        if request.htmx:
            return HttpResponse('<p class="form-note error">Enter a valid email.</p>')
        messages.error(request, "Enter a valid email.")
        return redirect(request.META.get("HTTP_REFERER", "shop:index"))

    sub, created = Subscriber.objects.get_or_create(
        email=email,
        defaults={"name": request.POST.get("name", ""), "source": request.POST.get("source", "")},
    )
    if not sub.is_active:
        sub.is_active = True
        sub.save(update_fields=["is_active"])
    if created:
        send_subscribe_welcome(sub)

    if request.htmx:
        return HttpResponse('<p class="form-note ok">You\'re on the list. Thanks!</p>')
    messages.success(request, "You're on the list.")
    return redirect(request.META.get("HTTP_REFERER", "shop:index"))


def unsubscribe(request, token):
    sub = Subscriber.objects.filter(unsubscribe_token=token).first()
    if sub and sub.is_active:
        sub.is_active = False
        sub.save(update_fields=["is_active"])
    return render(request, "shop/unsubscribe.html", {"ok": bool(sub)})


def order_track(request, token):
    order = get_object_or_404(
        Order.objects.prefetch_related("items", "fulfillments"), track_token=token
    )
    return render(request, "shop/order_track.html", {"order": order})


def contact(request):
    from shop.console import ContactMessage
    from shop.orders import Order as OrderModel

    if request.method == "POST":
        email = request.POST.get("email", "").strip().lower()
        body = request.POST.get("body", "").strip()
        if not email or "@" not in email or not body:
            messages.error(request, "Email and a message are both needed.")
        else:
            order = None
            ref = request.POST.get("order_ref", "").strip().upper().removeprefix("TTS-")
            if ref.isdigit():
                order = OrderModel.objects.filter(pk=int(ref)).first()
            msg = ContactMessage.objects.create(
                name=request.POST.get("name", "").strip(),
                email=email,
                subject=request.POST.get("subject", "").strip(),
                body=body,
                order=order,
            )
            try:
                from django.conf import settings as dj_settings
                from django.core.mail import send_mail

                send_mail(
                    subject=f"[contact] {msg.subject or 'message'} — {email}",
                    message=f"From: {msg.name} <{email}>\nOrder: {order.reference if order else '—'}\n\n{body}",
                    from_email=dj_settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[dj_settings.DEFAULT_FROM_EMAIL],
                    fail_silently=True,
                )
            except Exception:  # noqa: BLE001
                pass
            messages.success(request, "Thanks — we'll get back to you by email.")
            return redirect("shop:contact")

    return render(request, "shop/contact.html")
