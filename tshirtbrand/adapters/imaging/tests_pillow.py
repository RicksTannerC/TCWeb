"""The Pillow image tool against real (generated) images."""

import io

from django.test import SimpleTestCase
from PIL import Image, ImageDraw

from tshirtbrand.core.artwork.api import Layout

from .pillow.tool import PillowImageTool


def png_bytes(size=(400, 400), inner=(100, 50, 300, 150), mode="RGBA"):
    im = Image.new(mode, size, (0, 0, 0, 0) if mode == "RGBA" else (255, 255, 255))
    if inner:
        ImageDraw.Draw(im).rectangle(inner, fill=(200, 30, 30, 255) if mode == "RGBA" else (200, 30, 30))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


class PillowImageToolTests(SimpleTestCase):
    tool = PillowImageTool()

    def test_visible_size_ignores_the_transparent_margin(self):
        self.assertEqual(self.tool.visible_size(png_bytes()), (201, 101))

    def test_an_opaque_or_empty_image_is_measured_whole(self):
        self.assertEqual(self.tool.visible_size(png_bytes((30, 20), None, "RGB")), (30, 20))
        self.assertEqual(self.tool.visible_size(png_bytes((30, 20), None)), (30, 20))

    def test_palette_images_are_measured_too(self):
        buf = io.BytesIO()
        Image.new("P", (40, 30)).save(buf, "PNG")
        self.assertEqual(self.tool.visible_size(buf.getvalue()), (40, 30))

    def test_not_a_raster_is_none(self):
        self.assertIsNone(self.tool.visible_size(b'<svg viewBox="0 0 1 1"></svg>'))
        self.assertIsNone(self.tool.visible_size(b""))

    def test_is_raster_tells_an_intact_image_from_anything_else(self):
        self.assertTrue(self.tool.is_raster(png_bytes()))
        self.assertFalse(self.tool.is_raster(png_bytes()[:40]))   # truncated
        self.assertFalse(self.tool.is_raster(b'<svg xmlns="http://www.w3.org/2000/svg"/>'))
        self.assertFalse(self.tool.is_raster(b""))

    def test_compose_fills_the_slot_with_the_visible_design(self):
        out = self.tool.compose(png_bytes(), Layout(1800, 2400, 1260, 0, 540, 270))
        img = Image.open(io.BytesIO(out)).convert("RGBA")
        self.assertEqual(img.size, (1800, 2400))
        self.assertEqual(img.getchannel("A").getbbox(), (1260, 0, 1800, 270))
        self.assertEqual(img.getpixel((10, 10))[3], 0)

    def test_an_oversized_canvas_is_refused(self):
        with self.assertRaises(ValueError):
            self.tool.compose(png_bytes(), Layout(9000, 2400, 0, 0, 10, 10))

    def test_unreadable_art_is_an_oserror(self):
        with self.assertRaises(OSError):
            self.tool.compose(b"nope", Layout(100, 100, 0, 0, 10, 10))
