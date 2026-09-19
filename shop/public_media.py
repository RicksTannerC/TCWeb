"""Serve the public media folder (mockups, lifestyle shots, collection art).

Print-ready originals are NOT here; they live in private storage and are only
shown in the console. This folder is meant to be public, but it only ever serves
plain raster images: no SVG, HTML or anything else that could carry script, even
if such a file were uploaded by mistake.
"""

import os

from django.conf import settings
from django.http import Http404
from django.urls import re_path
from django.views.static import serve

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif"}
CACHE_SECONDS = 60 * 60 * 24  # a day; upload names are unique so stale copies aren't a concern


def public_media(request, path):
    if os.path.splitext(path)[1].lower() not in ALLOWED_EXTENSIONS:
        raise Http404("Not found")
    response = serve(request, path, document_root=settings.MEDIA_ROOT)
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = f"public, max-age={CACHE_SECONDS}"
    return response


def media_patterns():
    prefix = settings.MEDIA_URL.strip("/")
    return [re_path(rf"^{prefix}/(?P<path>.+)$", public_media, name="public_media")]
