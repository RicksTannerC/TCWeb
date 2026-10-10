"""First-touch traffic capture — referrer + campaign only, one row per session."""

import time
from urllib.parse import quote, urlparse

from django.conf import settings
from django.http import HttpResponse, HttpResponseNotFound
from django.shortcuts import redirect
from django.urls import Resolver404, resolve, reverse

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
        if getattr(request, "urlconf", None):
            return  # the private console host is not shop traffic
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


CONSOLE_URLCONF = "config.urls_console"
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]", "testserver"}


class HostRoutingMiddleware:
    """Give the private console host (settings.CONSOLE_HOST) its own URL layout.

    On that host the console lives at the root ("/" is the dashboard) and
    nothing else is served. Once a console host is configured, other public
    hostnames stop serving /manage/ and /admin/ altogether; localhost still
    does, so local development is unchanged. With CONSOLE_HOST unset this
    middleware does nothing.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        www = self._www_redirect(request)
        if www is not None:
            return www
        console_host = settings.CONSOLE_HOST
        if console_host:
            host = request.get_host().split(":")[0].lower()
            if host == console_host:
                request.urlconf = CONSOLE_URLCONF
                early = self._console_host(request)
                if early is not None:
                    return early
            elif host not in _LOCAL_HOSTS and request.path.startswith(("/manage/", "/admin/")):
                return HttpResponseNotFound("Not found")
        return self.get_response(request)

    @staticmethod
    def _www_redirect(request):
        """www.example.com -> example.com, permanently, keeping the path and query.

        Runs before anything calls get_host() (which would reject a www host that
        isn't in ALLOWED_HOSTS). It only ever redirects to a host the site is
        configured to serve -- an exact ALLOWED_HOSTS entry -- so the Host header
        can't be used to bounce visitors to somewhere else. The private console
        host is never redirected, and a www host with no matching apex is left to
        fail as it did before.
        """
        raw = request.META.get("HTTP_HOST", "").split(":")[0].strip().lower().rstrip(".")
        if not raw.startswith("www."):
            return None
        apex = raw[4:]
        if not apex or apex == (settings.CONSOLE_HOST or ""):
            return None
        if apex not in {h.strip().lower() for h in settings.ALLOWED_HOSTS}:
            return None
        scheme = "https" if request.is_secure() else "http"
        response = HttpResponse(status=301 if request.method in ("GET", "HEAD") else 308)
        response["Location"] = f"{scheme}://{apex}{request.get_full_path()}"
        return response

    @staticmethod
    def _console_host(request):
        path = request.path
        if path == "/manage" or path.startswith("/manage/"):
            # Old-style bookmark: /manage/orders/ -> /orders/
            target = path[len("/manage"):] or "/"
            query = request.META.get("QUERY_STRING")
            return redirect(target + ("?" + query if query else ""))
        try:
            match = resolve(request.path_info, urlconf=CONSOLE_URLCONF)
        except Resolver404:
            return None  # falls through to a normal 404
        served = (
            (match.url_name or "").startswith("manage_")
            or match.namespaces == ["admin"]
            or match.route == "robots.txt"
            or path.startswith("/" + settings.MEDIA_URL.lstrip("/"))
        )
        return None if served else HttpResponseNotFound("Not found")


_2FA_PROTECTED = ("/manage/", "/admin/")
_2FA_EXEMPT = ("/manage/2fa/", "/admin/login/", "/admin/logout/")
_2FA_EXEMPT_CONSOLE_HOST = ("/2fa/", "/admin/login/", "/admin/logout/", "/robots.txt")
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
    yet passed the second factor are sent to the 2FA page.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._blocked(request):
            # The handler hasn't applied request.urlconf yet, so pass it explicitly.
            base = reverse("shop:manage_2fa", urlconf=getattr(request, "urlconf", None))
            target = base + "?next=" + quote(request.get_full_path(), safe="/")
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
        if getattr(request, "urlconf", None) == CONSOLE_URLCONF:
            # Every page on the private host is console; only login + 2FA are open.
            if path.startswith(_2FA_EXEMPT_CONSOLE_HOST):
                return False
        else:
            if not path.startswith(_2FA_PROTECTED) or path.startswith(_2FA_EXEMPT):
                return False
        user = request.user
        if not (user.is_authenticated and user.is_staff):
            return False
        return not two_factor_ok(request)
