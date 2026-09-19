"""First-touch traffic capture — referrer + campaign only, one row per session."""

import time
from urllib.parse import quote, urlparse

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import redirect

_SKIP_PREFIXES = ("/manage/", "/admin/", "/webhooks/", "/static/", "/media/",
                  "/checkout/", "/cart/", "/order/", "/unsubscribe/")


class VisitCaptureMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            self._maybe_capture(request, response)
        except Exception:  # noqa: BLE001 — never break a page over analytics
            pass
        return response

    def _maybe_capture(self, request, response):
        if request.method != "GET" or getattr(request, "htmx", False):
            return
        # Only real HTML page views, not assets / redirects / 404s.
        if response.status_code != 200:
            return
        if "text/html" not in response.get("Content-Type", ""):
            return
        path = request.path
        if any(path.startswith(p) for p in _SKIP_PREFIXES):
            return
        if not request.session.session_key:
            request.session.save()
        key = request.session.session_key
        if request.session.get("_visit_logged"):
            return

        from .console import VisitLog

        ref = request.META.get("HTTP_REFERER", "")
        ref_host = urlparse(ref).hostname or ""
        host = request.get_host().split(":")[0]
        if ref_host == host:
            ref_host = ""  # internal navigation

        VisitLog.objects.create(
            session_key=key or "",
            landing_path=path[:300],
            referrer_host=ref_host[:200],
            utm_source=request.GET.get("utm_source", "")[:80],
            utm_medium=request.GET.get("utm_medium", "")[:80],
            utm_campaign=request.GET.get("utm_campaign", "")[:120],
        )
        request.session["_visit_logged"] = True


_2FA_PROTECTED = ("/manage/", "/admin/")
_2FA_EXEMPT = ("/manage/2fa/", "/admin/login/", "/admin/logout/")
SESSION_2FA_KEY = "_2fa_verified_at"


def two_factor_ok(request):
    """True when this session has a fresh, completed second-factor check."""
    if not request.user.is_verified():
        return False
    verified_at = request.session.get(SESSION_2FA_KEY, 0)
    return time.time() - verified_at < settings.STAFF_2FA_MAX_AGE


class StaffTwoFactorMiddleware:
    """Require a second factor for staff on the console and the Django admin.

    Runs after authentication + django-otp. Anonymous visitors fall through to
    the normal login redirect; staff who have signed in with a password but not
    yet passed the second factor are sent to /manage/2fa/.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._blocked(request):
            target = "/manage/2fa/?next=" + quote(request.get_full_path(), safe="/")
            if getattr(request, "htmx", False):
                # A redirect would be swapped into the page fragment; tell htmx to navigate.
                response = HttpResponse(status=401)
                response["HX-Redirect"] = target
                return response
            return redirect(target)
        return self.get_response(request)

    @staticmethod
    def _blocked(request):
        if not settings.STAFF_2FA_REQUIRED:
            return False
        path = request.path
        if not path.startswith(_2FA_PROTECTED) or path.startswith(_2FA_EXEMPT):
            return False
        user = request.user
        if not (user.is_authenticated and user.is_staff):
            return False
        return not two_factor_ok(request)
