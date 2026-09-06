from django.conf import settings
from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

import json

from . import fulfillment, payments
from .cart import Cart
from .emails import send_order_confirmation, send_subscribe_welcome
from .models import Listing, ListingSize, ProductType, Status
from .orders import Order, OrderStatus, Subscriber


# ---------------------------------------------------------------- catalogue

def _live_tees(query=""):
    qs = (
        Listing.objects.filter(status=Status.LIVE, product_type=ProductType.TEE)
        .select_related("design")
        .prefetch_related("images", "design__tags")
    )
    if query:
        qs = qs.filter(
            Q(design__title__icontains=query)
            | Q(design__tags__name__icontains=query)
            | Q(color__icontains=query)
            | Q(product_type__icontains=query)
        ).distinct()
    return qs


def shop_index(request):
    query = request.GET.get("q", "").strip()
    tees = _live_tees(query)
    if request.htmx and request.GET.get("grid"):
        return render(request, "shop/_grid.html", {"tees": tees, "query": query})
    return render(request, "shop/shop.html", {"tees": tees, "query": query, "overlay": None})


def listing_detail(request, slug):
    listing = get_object_or_404(
        Listing.objects.select_related("design", "template", "collection").prefetch_related(
            "images", "sizes", "design__tags"
        ),
        slug=slug,
    )
    ctx = {"listing": listing, "sticker": listing.design.sticker_listing}
    if request.htmx:
        return render(request, "shop/_overlay.html", ctx)
    ctx.update({"tees": _live_tees(), "query": "", "overlay": listing})
    return render(request, "shop/shop.html", ctx)


def overlay_close(request):
    return HttpResponse("")


# ---------------------------------------------------------------- cart

def _cart_response(request, feedback_template=None, feedback_ctx=None):
    """htmx: feedback fragment + out-of-band cart updates. else: redirect to cart."""
    if request.htmx:
        html = ""
        if feedback_template:
            html = render(request, feedback_template, feedback_ctx or {}).content.decode()
        html += render(request, "shop/_cart_oob.html").content.decode()
        return HttpResponse(html)
    return redirect("shop:cart_detail")


@require_POST
def cart_add(request, listing_id):
    listing = get_object_or_404(Listing, id=listing_id, status=Status.LIVE)
    size = get_object_or_404(ListingSize, id=request.POST.get("size"), listing=listing)
    Cart(request).add(listing, size)
    if not request.htmx:
        messages.success(request, f"Added {listing.design.title} ({size.label}) to your cart.")
    return _cart_response(request, "shop/_added.html")


@require_POST
def cart_update(request):
    try:
        quantity = int(request.POST.get("quantity", 1))
    except (TypeError, ValueError):
        quantity = 1
    Cart(request).set_quantity(request.POST.get("listing"), request.POST.get("size"), quantity)
    if request.htmx:
        return render(request, "shop/_cart_body.html", {"oob": True})
    return redirect("shop:cart_detail")


@require_POST
def cart_remove(request):
    Cart(request).remove(request.POST.get("listing"), request.POST.get("size"))
    if request.htmx and request.headers.get("HX-Target") == "cart-body":
        return render(request, "shop/_cart_body.html", {"oob": True})
    return _cart_response(request)


def cart_drawer(request):
    return render(request, "shop/_cart_drawer_body.html")


def cart_detail(request):
    return render(request, "shop/cart_detail.html")


# ---------------------------------------------------------------- checkout

@require_POST
def checkout(request):
    cart = Cart(request)
    if len(cart) == 0:
        messages.info(request, "Your cart is empty.")
        return redirect("shop:cart_detail")

    order = payments.create_order_from_cart(cart)
    request.session["pending_order_id"] = order.id

    if payments.stripe_ready():
        session = payments.create_checkout_session(request, order)
        return redirect(session.url, permanent=False)

    if settings.DEBUG:
        return redirect("shop:checkout_dev")

    messages.error(request, "Checkout is temporarily unavailable. Please try again later.")
    return redirect("shop:cart_detail")


def checkout_success(request):
    ref = request.GET.get("ref", "")
    order = None
    if ref:
        order = Order.objects.filter(stripe_session_id=ref).first()
    if not order:
        oid = request.session.get("pending_order_id")
        order = Order.objects.filter(id=oid).first() if oid else None

    Cart(request).clear()
    request.session.pop("pending_order_id", None)
    return render(request, "shop/checkout_success.html", {"order": order})


# --- dev-only stand-in for the Stripe redirect ---------------------

def checkout_dev(request):
    if not settings.DEBUG:
        return HttpResponseBadRequest()
    order = Order.objects.filter(id=request.session.get("pending_order_id")).first()
    if not order:
        return redirect("shop:cart_detail")
    return render(request, "shop/checkout_dev.html", {"order": order})


@require_POST
def checkout_simulate(request):
    if not settings.DEBUG:
        return HttpResponseBadRequest()
    order = Order.objects.filter(id=request.session.get("pending_order_id")).first()
    if not order or order.status != OrderStatus.PENDING_PAYMENT:
        return redirect("shop:cart_detail")

    order.email = request.POST.get("email", "dev@example.com")
    order.name = request.POST.get("name", "Dev Tester")
    order.status = OrderStatus.PENDING_APPROVAL
    order.save()
    try:
        send_order_confirmation(order)
    except Exception:  # noqa: BLE001 — dev convenience
        pass
    return redirect(reverse("shop:checkout_success") + f"?ref={order.stripe_session_id or ''}")


@csrf_exempt
@require_POST
def stripe_webhook(request):
    try:
        event = payments.construct_event(request.body, request.META.get("HTTP_STRIPE_SIGNATURE", ""))
    except Exception:  # noqa: BLE001 — bad signature / malformed
        return HttpResponseBadRequest("invalid payload")

    if event["type"] == "checkout.session.completed":
        order, created = payments.fulfill_from_session(event["data"]["object"])
        if order and created:
            try:
                send_order_confirmation(order)
            except Exception:  # noqa: BLE001
                pass

    return HttpResponse(status=200)


@csrf_exempt
@require_POST
def printful_webhook(request):
    try:
        event = json.loads(request.body or b"{}")
    except ValueError:
        return HttpResponseBadRequest("invalid payload")
    etype = event.get("type", "")
    data = event.get("data", {})
    if etype:
        fulfillment.apply_partner_event(etype, data)
    return HttpResponse(status=200)


# ---------------------------------------------------------------- subscribers

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


# ---------------------------------------------------------------- order tracking

def order_track(request, token):
    order = get_object_or_404(
        Order.objects.prefetch_related("items", "fulfillments"), track_token=token
    )
    return render(request, "shop/order_track.html", {"order": order})


# ---------------------------------------------------------------- contact

def contact(request):
    from .console import ContactMessage
    from .orders import Order as OrderModel

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
