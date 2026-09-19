"""Second-factor verification page for staff (authenticator code or backup code)."""

import time

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django_otp import devices_for_user, login as otp_login

from .middleware import SESSION_2FA_KEY, two_factor_ok


def _safe_next(request):
    target = request.POST.get("next") or request.GET.get("next") or ""
    if url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return target
    return "/manage/"


@never_cache
@login_required(login_url="/admin/login/")
def verify(request):
    next_url = _safe_next(request)
    if not request.user.is_staff:
        return redirect("shop:index")
    if two_factor_ok(request):
        return redirect(next_url)

    devices = list(devices_for_user(request.user, confirmed=True))
    error = ""
    if request.method == "POST" and devices:
        # Spaces are stripped and case folded (backup codes are lowercase); the
        # error message is deliberately generic.
        token = "".join(request.POST.get("token", "").split()).lower()
        for device in devices:
            if device.verify_token(token):
                otp_login(request, device)
                request.session[SESSION_2FA_KEY] = time.time()
                return redirect(next_url)
        error = "That code didn't work. Check the code and try again."

    return render(request, "shop/manage/two_factor.html", {
        "next": next_url,
        "error": error,
        "enrolled": bool(devices),
        "username": request.user.get_username(),
    })
