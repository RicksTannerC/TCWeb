"""Where a print sits on its print area, and how to tell when a layout has changed.

Pure arithmetic and strings: no images, no Django, no supplier. Sizes are pixels of the supplier's print file."""

import re
from dataclasses import dataclass

CENTER = "center"

# Where each position preset puts the CENTRE of a print, as a fraction of the print area (0.5, 0.5 = dead
# centre). Left/right/upper are as you look at the shirt. Keys are the stored position values.
POSITION_OFFSETS = {
    "center": (0.5, 0.5),
    "higher": (0.5, 0.3),
    "lower": (0.5, 0.7),
    "left": (0.3, 0.5),
    "right": (0.7, 0.5),
    "top_left": (0.3, 0.25),
    "top_right": (0.7, 0.25),
}

# 1800 x 2400 px is the front/back print area of the shirts in use. Used when the real figure can't be fetched.
DEFAULT_PRINT_AREA = (1800, 2400)

MIN_SCALE_PCT = 25
MAX_SCALE_PCT = 100


@dataclass(frozen=True)
class Layout:
    """A print placed on a canvas the size of its print area: the box the visible design fills."""

    area_width: int
    area_height: int
    left: int
    top: int
    width: int
    height: int

    def __post_init__(self):
        if min(self.area_width, self.area_height, self.width, self.height) <= 0 or min(self.left, self.top) < 0:
            raise ValueError("bad print layout")

    def as_list(self):
        """[area_width, area_height, left, top, width, height]: the compact form carried in a signed link."""
        return [self.area_width, self.area_height, self.left, self.top, self.width, self.height]

    @classmethod
    def from_list(cls, values):
        area_w, area_h, left, top, width, height = (int(v) for v in values)
        return cls(area_w, area_h, left, top, width, height)


def plan_layout(scale_pct, position, area=DEFAULT_PRINT_AREA, aspect=1.0):
    """The box a print occupies, or None when it needs no positioning (full size and centred).

    `area` is the placement's real print-file size (a wrong one makes the supplier ignore the offset and
    centre the print). `aspect` is the visible artwork's width / height, so the box keeps the art's shape.
    `scale_pct` is how wide the art runs across the area (capped so it also fits the area's height) and is
    clamped to 25..100. The box is kept inside the area: a print can't hang off the shirt."""
    if scale_pct >= MAX_SCALE_PCT and position == CENTER:
        return None
    cx, cy = POSITION_OFFSETS.get(position, (0.5, 0.5))
    scale = max(MIN_SCALE_PCT, min(MAX_SCALE_PCT, scale_pct)) / 100
    area_w, area_h = (int(area[0]), int(area[1])) if area else DEFAULT_PRINT_AREA
    aspect = aspect if aspect and aspect > 0 else 1.0
    width = scale * area_w
    height = width / aspect
    if height > scale * area_h:
        height = scale * area_h
        width = height * aspect
    width, height = min(area_w, round(width)), min(area_h, round(height))
    top = max(0, min(area_h - height, round(cy * area_h - height / 2)))
    left = max(0, min(area_w - width, round(cx * area_w - width / 2)))
    return Layout(area_w, area_h, left, top, width, height)


@dataclass(frozen=True)
class PrintSpec:
    """One print area as the curator set it. `art` is an opaque key that changes when the artwork does."""

    placement: str
    scale_pct: int
    position: str
    art: str


def art_key(design_id, version=0):
    """Names one artwork file: its design, plus ":v<n>" once the file has been replaced in place."""
    return f"d{design_id}" + (f"v{version}" if version else "")


def print_signature(specs):
    """A stable fingerprint of every print area, to notice when the layout changed after the product was sent.

    "g3" marks a positioned print as built into the print file itself (older sends gave the supplier a
    position it ignored), so a listing sent the old way shows as needing a re-send."""
    def geometry(spec):
        return "" if spec.scale_pct >= MAX_SCALE_PCT and spec.position == CENTER else ":g3"

    parts = [f"{s.placement}:{s.scale_pct}:{s.position}:{s.art}{geometry(s)}" for s in specs]
    return "|".join(sorted(parts))[:255]


_SVG_VIEWBOX = re.compile(r'viewBox\s*=\s*["\']\s*[-\d.]+[ ,]+[-\d.]+[ ,]+([\d.]+)[ ,]+([\d.]+)')


def svg_aspect(head):
    """Width / height of an SVG from its viewBox, else its width and height attributes; None if unreadable."""
    text = head[:4096].decode("utf-8", "ignore")
    box = _SVG_VIEWBOX.search(text)
    if box:
        w, h = float(box.group(1)), float(box.group(2))
    else:
        wm, hm = (re.search(rf'<svg[^>]*\s{k}\s*=\s*["\']([\d.]+)', text) for k in ("width", "height"))
        if not (wm and hm):
            return None
        w, h = float(wm.group(1)), float(hm.group(1))
    return w / h if w > 0 and h > 0 else None
