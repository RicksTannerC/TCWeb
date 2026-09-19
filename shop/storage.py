"""Private file storage for print-ready originals.

Originals (SVG or full-size PNG) live outside MEDIA_ROOT, in PRIVATE_MEDIA_ROOT,
and have no public URL. They are only ever read through a staff-only view on the
console host (see console_views.design_artwork).
"""

import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage


class PrivateMediaStorage(FileSystemStorage):
    # Resolved on every access so tests (and env changes) can repoint it.
    @property
    def base_location(self):
        return str(settings.PRIVATE_MEDIA_ROOT)

    @property
    def location(self):
        return os.path.abspath(self.base_location)

    def url(self, name):
        raise ValueError("Private files have no public URL; serve them through the console view.")


_storage = PrivateMediaStorage()


def get_private_storage():
    """Callable used by the model field, so the migration stores a stable reference."""
    return _storage
