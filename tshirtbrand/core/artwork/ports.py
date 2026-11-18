"""What the artwork context needs from the outside: something that can look at and build image files."""

from typing import Protocol

from .model import Layout


class ImageTool(Protocol):
    def visible_size(self, data: bytes):
        """(width, height) of the design's visible pixels, transparent margin excluded, or None when `data`
        isn't a raster image this tool can read."""

    def is_raster(self, data: bytes) -> bool:
        """True if `data` is an intact raster image this tool can read."""

    def compose(self, data: bytes, layout: Layout) -> bytes:
        """PNG bytes: the visible design resized to `layout`'s box on a transparent canvas the size of the
        print area. Raises ValueError for a layout it won't build and OSError for unreadable art."""
