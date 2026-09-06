"""First-touch traffic capture — referrer + campaign only, one row per session."""

from urllib.parse import urlparse

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
