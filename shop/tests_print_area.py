"""A positioned print is measured against the placement's real print-file size and keeps the
artwork's shape. Stub replies only (the shape is what Printful returned for products 586 and 71)."""

import io
import os
import tempfile
from unittest import mock

from django.core.cache import cache
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings

from tshirtbrand.bootstrap import get_supplier

from . import printful
from tshirtbrand.bootstrap import get_image_tool
from tshirtbrand.core.artwork.api import DEFAULT_PRINT_AREA, Layout, plan_layout

from .models import Design, Listing, ListingPrint, PrintPosition, ProductTemplate
from .supplier_bridge import print_files_for

REAL_REPLY = {
    "product_id": 586,
    "printfiles": [
        {"printfile_id": 1, "width": 1800, "height": 2400, "dpi": 150},
        {"printfile_id": 90, "width": 450, "height": 450, "dpi": 150},
        {"printfile_id": 130, "width": 600, "height": 525, "dpi": 150},
    ],
    "variant_printfiles": [
        {"variant_id": 15114, "placements": {"front": 1, "back": 1, "sleeve_left": 130, "label_outside": 90}},
    ],
}


def png(w, h):
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGBA", (w, h), (10, 100, 50, 255)).save(buf, "PNG")
    return buf.getvalue()


def box_of(entry):
    """The [area_w, area_h, left, top, width, height] a composed print's link carries."""
    from django.core import signing

    url = entry["url"] if isinstance(entry, dict) else entry.url  # a neutral PrintFile or the wire dict
    token = url.rstrip("/").rsplit("/", 1)[1]
    return signing.loads(token, salt="shop.printful-artwork")["box"]


class AreaLookupTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def stub(self, reply=None, error=None):
        c = mock.MagicMock(is_mock=False)
        if error:
            c.print_files.side_effect = error
        else:
            c.print_files.return_value = REAL_REPLY if reply is None else reply
        return c

    def area(self, placement, client, blueprint="586"):
        with mock.patch.object(printful, "get_client", return_value=client):
            found = get_supplier().print_area(blueprint, placement)
        return (found.width, found.height) if found else DEFAULT_PRINT_AREA  # the fallback Listing.layout_for applies

    def test_reads_the_size_of_each_placement(self):
        c = self.stub()
        self.assertEqual(self.area("front", c), (1800, 2400))
        self.assertEqual(self.area("sleeve_left", c), (600, 525))
        self.assertEqual(self.area("label_outside", c), (450, 450))

    def test_one_fetch_per_product(self):
        c = self.stub()
        self.area("front", c)
        self.area("back", c)
        self.assertEqual(c.print_files.call_count, 1)

    def test_falls_back_when_printful_errors_or_replies_oddly(self):
        for c in (self.stub(error=printful.PrintfulError("boom")), self.stub(reply={}),
                  self.stub(reply={"printfiles": "x", "variant_printfiles": 3})):
            cache.clear()
            self.assertEqual(self.area("front", c), DEFAULT_PRINT_AREA)

    def test_unknown_placement_and_no_product_fall_back(self):
        self.assertEqual(self.area("nowhere", self.stub()), DEFAULT_PRINT_AREA)
        self.assertEqual(self.area("front", self.stub(), blueprint=""), DEFAULT_PRINT_AREA)


class PayloadShapeTests(TestCase):
    def test_wide_art_keeps_its_shape(self):
        p = plan_layout(30, PrintPosition.TOP_LEFT, area=(1800, 2400), aspect=2.0)
        self.assertEqual((p.width, p.height), (540, 270))

    def test_tall_art_is_limited_by_the_area_height_share(self):
        p = plan_layout(30, PrintPosition.CENTER, area=(1800, 2400), aspect=0.2)
        self.assertEqual(p.height, 720)
        self.assertEqual(p.width, 144)

    def test_the_box_stays_inside_every_area_for_odd_art(self):
        for aspect in (0.1, 0.5, 1.0, 3.0, 10.0):
            for pos in PrintPosition.values:
                for scale in (25, 50, 100):
                    p = plan_layout(scale, pos, area=(600, 525), aspect=aspect)
                    box = p
                    if box:
                        self.assertGreaterEqual(box.top, 0)
                        self.assertGreaterEqual(box.left, 0)
                        self.assertLessEqual(box.top + box.height, 525, (aspect, pos, scale))
                        self.assertLessEqual(box.left + box.width, 600, (aspect, pos, scale))

    def test_a_corner_preset_lands_in_that_corner_of_the_real_area(self):
        p = plan_layout(30, PrintPosition.TOP_RIGHT, area=(1800, 2400))
        self.assertGreater(p.left + p.width / 2, 900)
        self.assertLess(p.top + p.height / 2, 1200)

    def test_nonsense_aspect_is_treated_as_square(self):
        for bad in (0, -1, None):
            p = plan_layout(30, PrintPosition.CENTER, aspect=bad)
            self.assertEqual(p.width, p.height)


class ArtworkAspectTests(TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.enterContext(override_settings(
            MEDIA_ROOT=os.path.join(tmp.name, "public"), PRIVATE_MEDIA_ROOT=os.path.join(tmp.name, "private")))

    def design(self, name, data):
        d = Design.objects.create(title=name)
        d.artwork.save(name, ContentFile(data), save=True)
        return d

    def test_png(self):
        self.assertAlmostEqual(self.design("w.png", png(400, 100)).artwork_aspect(), 4.0)

    def test_svg_viewbox_and_width_height(self):
        self.assertAlmostEqual(
            self.design("a.svg", b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 200"></svg>').artwork_aspect(), 1.5)
        self.assertAlmostEqual(
            self.design("b.svg", b'<svg xmlns="http://www.w3.org/2000/svg" width="100" height="400"></svg>').artwork_aspect(), 0.25)

    def test_unreadable_or_missing_art_is_square(self):
        self.assertEqual(self.design("c.svg", b"not an image").artwork_aspect(), 1.0)
        self.assertEqual(Design.objects.create(title="none").artwork_aspect(), 1.0)
        self.assertEqual(self.design("d.svg", b'<svg viewBox="0 0 0 0"></svg>').artwork_aspect(), 1.0)


class EndToEndTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.enterContext(override_settings(
            MEDIA_ROOT=os.path.join(tmp.name, "public"), PRIVATE_MEDIA_ROOT=os.path.join(tmp.name, "private")))

    def test_the_sent_front_print_uses_the_real_area_and_the_art_shape(self):
        tpl = ProductTemplate.objects.create(name="Tee", product_type="tee", print_placement="back",
                                             printful_blueprint_id="586")
        main = Design.objects.create(title="Main")
        main.artwork.save("m.png", ContentFile(png(300, 400)), save=True)
        logo = Design.objects.create(title="Logo")
        logo.artwork.save("l.png", ContentFile(png(200, 100)), save=True)
        listing = Listing.objects.create(design=main, template=tpl, product_type="tee")
        ListingPrint.objects.create(listing=listing, placement="front", design=logo, scale_pct=30,
                                    position=PrintPosition.TOP_LEFT)
        client = mock.MagicMock(is_mock=False)
        client.print_files.return_value = REAL_REPLY
        with mock.patch.object(printful, "get_client", return_value=client):
            main_entry, front = print_files_for(listing)
        self.assertIsNone(main_entry.box)
        self.assertIsNone(front.box)  # built into the file, not left to Printful
        area_w, area_h, left, top, width, height = box_of(front)
        self.assertEqual((area_w, area_h), (1800, 2400))
        self.assertEqual((width, height), (540, 270))  # 2:1 logo, 30% of the width
        self.assertLess(left + width / 2, 900)
        self.assertLess(top + height / 2, 1200)


class OldSendNoticedTests(TestCase):
    def test_a_positioned_print_sent_before_the_fix_shows_as_needing_a_resend(self):
        tpl = ProductTemplate.objects.create(name="Tee", product_type="tee", print_placement="back")
        listing = Listing.objects.create(design=Design.objects.create(title="J"), template=tpl, product_type="tee",
                                         printful_product_id="1")
        ListingPrint.objects.create(listing=listing, placement="front", scale_pct=30, position=PrintPosition.TOP_LEFT)
        listing.printful_sent_prints = f"back:100:center:d{listing.design_id}|front:30:top_left:d{listing.design_id}"
        self.assertTrue(any("print areas" in c for c in listing.printful_changes_not_sent))
        listing.printful_sent_prints = listing.print_signature()
        self.assertEqual(listing.printful_changes_not_sent, [])

    def test_a_plain_centered_print_is_not_flagged(self):
        tpl = ProductTemplate.objects.create(name="Tee", product_type="tee", print_placement="back")
        listing = Listing.objects.create(design=Design.objects.create(title="J"), template=tpl, product_type="tee",
                                         printful_product_id="1")
        listing.printful_sent_prints = f"back:100:center:d{listing.design_id}"
        self.assertEqual(listing.printful_changes_not_sent, [])


@override_settings(STAFF_2FA_REQUIRED=False)
class ComposedFileTests(TestCase):
    """The link Printful fetches serves the art already placed on a print-area canvas."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.enterContext(override_settings(
            MEDIA_ROOT=os.path.join(tmp.name, "public"), PRIVATE_MEDIA_ROOT=os.path.join(tmp.name, "private")))
        self.tpl = ProductTemplate.objects.create(name="Tee", product_type="tee", print_placement="back")

    def listing_with_front(self, art, **kw):
        design = Design.objects.create(title="Logo")
        design.artwork.save(art[0], ContentFile(art[1]), save=True)
        main = Design.objects.create(title="Main")
        main.artwork.save("m.png", ContentFile(png(30, 40)), save=True)
        listing = Listing.objects.create(design=main, template=self.tpl, product_type="tee")
        ListingPrint.objects.create(listing=listing, placement="front", design=design, **kw)
        return listing

    def fetch(self, entry):
        from urllib.parse import urlsplit
        return self.client.get(urlsplit(entry.url).path)

    def test_the_link_serves_a_print_area_sized_png_with_the_art_where_chosen(self):
        from PIL import Image

        listing = self.listing_with_front(("l.png", png(100, 100)), scale_pct=30, position=PrintPosition.TOP_RIGHT)
        client = mock.MagicMock(is_mock=False)
        client.print_files.return_value = REAL_REPLY
        with mock.patch.object(printful, "get_client", return_value=client):
            _, front = print_files_for(listing)
        r = self.fetch(front)
        self.assertEqual((r.status_code, r["Content-Type"]), (200, "image/png"))
        img = Image.open(io.BytesIO(b"".join(r.streaming_content) if r.streaming else r.content)).convert("RGBA")
        self.assertEqual(img.size, (1800, 2400))
        solid = img.getchannel("A").getbbox()
        self.assertEqual(solid[2] - solid[0], 540)             # 30% of the width
        self.assertGreater((solid[0] + solid[2]) / 2, 900)      # right of center
        self.assertLess((solid[1] + solid[3]) / 2, 1200)        # above center
        self.assertEqual(img.getpixel((10, 10))[3], 0)          # the rest stays transparent

    def test_an_unpositioned_print_is_the_plain_file(self):
        listing = self.listing_with_front(("l.png", png(100, 100)), scale_pct=100)
        _, front = print_files_for(listing)
        r = self.fetch(front)
        self.assertEqual(r.status_code, 200)
        r.close()  # a streamed file stays open (and locked on Windows) until closed
        self.assertNotIn("box", __import__("django.core.signing", fromlist=["x"]).loads(
            front.url.rstrip("/").rsplit("/", 1)[1], salt="shop.printful-artwork"))

    def test_svg_art_falls_back_to_a_position(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10"/></svg>'
        listing = self.listing_with_front(("l.svg", svg), scale_pct=30, position=PrintPosition.TOP_LEFT)
        client = mock.MagicMock(is_mock=False)
        client.print_files.return_value = REAL_REPLY
        with mock.patch.object(printful, "get_client", return_value=client):
            _, front = print_files_for(listing)
        self.assertIsNotNone(front.box)

    def test_a_tampered_or_stale_link_is_refused(self):
        listing = self.listing_with_front(("l.png", png(100, 100)), scale_pct=30, position=PrintPosition.TOP_LEFT)
        _, front = print_files_for(listing)
        from urllib.parse import urlsplit
        path = urlsplit(front.url).path
        self.assertEqual(self.client.get(path[:-6] + "xxxxx/").status_code, 404)
        design = listing.prints.get().design
        design.artwork.save("new.png", ContentFile(png(50, 50)), save=True)  # replaced since the link was made
        self.assertEqual(self.client.get(path).status_code, 404)


class VisibleDesignTests(TestCase):
    """Size and position refer to the visible design, not the file's empty margin."""

    def padded(self, canvas=(400, 400), inner=(100, 50, 300, 150)):
        from PIL import Image, ImageDraw

        im = Image.new("RGBA", canvas, (0, 0, 0, 0))
        ImageDraw.Draw(im).rectangle(inner, fill=(200, 30, 30, 255))
        buf = io.BytesIO()
        im.save(buf, "PNG")
        return buf.getvalue()

    def test_visible_size_ignores_the_transparent_margin(self):
        from PIL import Image

        from tshirtbrand.adapters.imaging.pillow.tool import visible_box, visible_size_of as visible_size

        im = Image.open(io.BytesIO(self.padded()))
        self.assertEqual(visible_box(im), (100, 50, 301, 151))
        self.assertEqual(visible_size(im), (201, 101))
        self.assertEqual(visible_size(Image.new("RGB", (30, 20))), (30, 20))
        self.assertEqual(visible_size(Image.new("RGBA", (30, 20), (0, 0, 0, 0))), (30, 20))

    def test_a_faint_fringe_is_not_counted(self):
        from PIL import Image

        from tshirtbrand.adapters.imaging.pillow.tool import visible_box

        im = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
        im.putpixel((2, 2), (0, 0, 0, 3))      # near invisible
        im.putpixel((50, 50), (0, 0, 0, 255))
        self.assertEqual(visible_box(im), (50, 50, 51, 51))

    def test_the_composed_print_places_the_visible_design_not_the_canvas(self):
        from PIL import Image

        layout = Layout.from_list([1800, 2400, 1260, 0, 540, 270])   # a 2:1 slot in the upper right
        out = Image.open(io.BytesIO(get_image_tool().compose(self.padded(), layout))).convert("RGBA")
        solid = out.getchannel("A").getbbox()
        self.assertEqual(solid, (1260, 0, 1800, 270))   # the design fills its slot to the edge

    def test_artwork_aspect_is_the_visible_designs(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        with override_settings(MEDIA_ROOT=os.path.join(tmp.name, "p"), PRIVATE_MEDIA_ROOT=os.path.join(tmp.name, "q")):
            d = Design.objects.create(title="Padded")
            d.artwork.save("p.png", ContentFile(self.padded()), save=True)
            self.assertAlmostEqual(d.artwork_aspect(), 201 / 101, places=3)
