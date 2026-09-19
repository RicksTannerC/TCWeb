import markdown as _md
from django import template
from django.conf import settings
from django.utils.safestring import mark_safe

register = template.Library()

_MD = _md.Markdown(extensions=["extra", "sane_lists", "nl2br", "smarty"])


@register.filter
def markdownify(text):
    """Render curator-authored Markdown. Page bodies are staff-only content."""
    if not text:
        return ""
    _MD.reset()
    return mark_safe(_MD.convert(text))


@register.filter
def on_public_site(path):
    """Turn a site path into an absolute URL on the public shop."""
    return settings.SITE_BASE_URL.rstrip("/") + (path or "")
