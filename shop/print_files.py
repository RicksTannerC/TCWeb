"""Build the print file for a positioned print: the artwork placed at a chosen spot on a
transparent canvas the size of the print area. Printful fits the whole canvas to the area, so
what we place is where it prints, whatever Printful does with a file's `position`.

Size and position refer to the *visible* design: the empty (transparent) margin around it is
cropped off first, so "upper right" puts the design itself in the corner."""

import io

from PIL import Image

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


def visible_size(im):
    box = visible_box(im)
    return (box[2] - box[0], box[3] - box[1]) if box else im.size


def compose(art_file, box):
    """PNG bytes. `art_file` is an open file of the artwork; `box` is
    [area_width, area_height, left, top, width, height] in pixels."""
    area_w, area_h, left, top, width, height = (int(v) for v in box)
    if not (0 < area_w <= MAX_SIDE and 0 < area_h <= MAX_SIDE and width > 0 and height > 0):
        raise ValueError("bad print layout")
    with Image.open(art_file) as src:
        art = src.convert("RGBA")
        crop = visible_box(art)
        if crop:
            art = art.crop(crop)
        art = art.resize((width, height), Image.LANCZOS)
    canvas = Image.new("RGBA", (area_w, area_h), (0, 0, 0, 0))
    canvas.alpha_composite(art, (max(0, min(left, area_w - width)), max(0, min(top, area_h - height))))
    out = io.BytesIO()
    canvas.save(out, "PNG")
    return out.getvalue()
