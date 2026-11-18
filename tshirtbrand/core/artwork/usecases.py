"""What the business can do with artwork: measure its shape and place it."""

from .model import svg_aspect
from .ports import ImageTool


def aspect_of(data: bytes, tool: ImageTool) -> float:
    """The visible design's width / height (transparent margin excluded), so a placed print keeps its shape.
    1.0 when it can't be read (no file, an odd format)."""
    size = tool.visible_size(data)
    if size:
        w, h = size
        return w / h if w and h else 1.0
    return svg_aspect(data) or 1.0
