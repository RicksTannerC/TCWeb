"""The ImageTool port on Pillow: measures the visible design and builds the print file for a positioned print.

Printful fits the whole canvas to the print area, so what we place here is where it prints, whatever the
supplier does with a file's `position`. Size and position refer to the *visible* design: the empty
(transparent) margin around it is cropped off first, so "upper right" puts the design itself in the corner."""

import io

from PIL import Image

from tshirtbrand.core.artwork.api import Layout

# the largest canvas we'll build: a sanity limit, real print areas are ~2250 x 2700
MAX_SIDE = 6000
# alpha below this counts as empty (ignores faint fringes and stray near-invisible pixels)
VISIBLE_ALPHA = 8


def visible_box(im):
    """(left, top, right, bottom) of the design's visible pixels, or None to use the whole image
    (no transparency, or nothing visible)."""
    if "A" not in im.getbands():
        return None
    mask = im.getchannel("A").point(lambda a: 255 if a >= VISIBLE_ALPHA else 0)
    return mask.getbbox()


def visible_size_of(im):
    box = visible_box(im)
    return (box[2] - box[0], box[3] - box[1]) if box else im.size


class PillowImageTool:
    def visible_size(self, data):
        try:
            with Image.open(io.BytesIO(data)) as im:
                return visible_size_of(im.convert("RGBA") if im.mode in ("P", "LA", "RGBa") else im)
        except Exception:  # noqa: BLE001 - not a raster image (an SVG, say): the caller tries another way
            return None

    def compose(self, data, layout: Layout):
        if not (layout.area_width <= MAX_SIDE and layout.area_height <= MAX_SIDE):
            raise ValueError("bad print layout")
        with Image.open(io.BytesIO(data)) as src:
            art = src.convert("RGBA")
            crop = visible_box(art)
            if crop:
                art = art.crop(crop)
            art = art.resize((layout.width, layout.height), Image.LANCZOS)
        canvas = Image.new("RGBA", (layout.area_width, layout.area_height), (0, 0, 0, 0))
        canvas.alpha_composite(art, (max(0, min(layout.left, layout.area_width - layout.width)),
                                     max(0, min(layout.top, layout.area_height - layout.height))))
        out = io.BytesIO()
        canvas.save(out, "PNG")
        return out.getvalue()
