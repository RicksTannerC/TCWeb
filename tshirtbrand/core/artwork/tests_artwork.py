"""The artwork context on its own: layout arithmetic, the print fingerprint and aspect reading. No images,
no Django models: a stub stands in for the image tool."""

from django.test import SimpleTestCase

from . import api
from .api import Layout, PrintSpec, plan_layout, print_signature


class StubTool:
    def __init__(self, size=None):
        self.size = size

    def visible_size(self, data):
        return self.size

    def compose(self, data, layout):
        return b"png"


class PlanLayoutTests(SimpleTestCase):
    def test_full_size_and_centred_needs_no_layout(self):
        self.assertIsNone(plan_layout(100, "center"))

    def test_full_size_but_off_centre_still_gets_a_layout(self):
        self.assertIsNotNone(plan_layout(100, "higher"))

    def test_scale_is_clamped_to_25_100(self):
        self.assertEqual(plan_layout(5, "center").width, 450)    # 25% of 1800
        self.assertEqual(plan_layout(500, "left").width, 1800)

    def test_wide_and_tall_art_keep_their_shape_inside_the_area(self):
        wide = plan_layout(30, "top_left", area=(1800, 2400), aspect=2.0)
        self.assertEqual((wide.width, wide.height), (540, 270))
        tall = plan_layout(30, "center", area=(1800, 2400), aspect=0.2)
        self.assertEqual((tall.width, tall.height), (144, 720))

    def test_every_preset_stays_inside_every_area(self):
        for pos in api.POSITION_OFFSETS:
            for aspect in (0.1, 1.0, 10.0):
                for scale in (25, 50, 99):
                    p = plan_layout(scale, pos, area=(600, 525), aspect=aspect)
                    self.assertGreaterEqual(min(p.left, p.top), 0, (pos, aspect, scale))
                    self.assertLessEqual(p.left + p.width, 600, (pos, aspect, scale))
                    self.assertLessEqual(p.top + p.height, 525, (pos, aspect, scale))

    def test_unknown_position_centres(self):
        p = plan_layout(50, "diagonal")
        self.assertEqual(p.left + p.width / 2, p.area_width / 2)

    def test_nonsense_aspect_is_square(self):
        for bad in (0, -1, None):
            p = plan_layout(30, "center", aspect=bad)
            self.assertEqual(p.width, p.height)

    def test_an_empty_area_falls_back_to_the_default(self):
        self.assertEqual(plan_layout(50, "center", area=None).area_width, api.DEFAULT_PRINT_AREA[0])


class LayoutTests(SimpleTestCase):
    def test_round_trips_through_its_list_form(self):
        lay = Layout(1800, 2400, 1260, 0, 540, 270)
        self.assertEqual(Layout.from_list(lay.as_list()), lay)
        self.assertEqual(Layout.from_list(["1800", "2400", "1", "2", "3", "4"]).height, 4)

    def test_nonsense_is_refused(self):
        for bad in ([0, 10, 0, 0, 5, 5], [10, 10, 0, 0, 0, 5], [10, 10, -1, 0, 5, 5]):
            with self.assertRaises(ValueError):
                Layout.from_list(bad)


class SignatureTests(SimpleTestCase):
    def spec(self, placement="front", scale=100, position="center", art="d1"):
        return PrintSpec(placement, scale, position, art)

    def test_plain_print_has_no_geometry_marker(self):
        self.assertEqual(print_signature([self.spec()]), "front:100:center:d1")

    def test_positioned_print_is_marked_as_built_into_the_file(self):
        self.assertEqual(print_signature([self.spec(scale=30)]), "front:30:center:d1:g3")
        self.assertEqual(print_signature([self.spec(position="higher")]), "front:100:higher:d1:g3")

    def test_order_does_not_matter_and_every_input_changes_it(self):
        a, b = self.spec(), self.spec("back", 40, "left", "d2")
        self.assertEqual(print_signature([a, b]), print_signature([b, a]))
        base = print_signature([a])
        for changed in (self.spec(scale=90), self.spec(position="left"), self.spec(art="d1v2"), self.spec("back")):
            self.assertNotEqual(print_signature([changed]), base)

    def test_art_key_names_the_design_and_its_replaced_version(self):
        self.assertEqual(api.art_key(7), "d7")
        self.assertEqual(api.art_key(7, 3), "d7v3")

    def test_it_fits_the_stored_column(self):
        self.assertLessEqual(len(print_signature([self.spec(art="d" + "9" * 400)])), 255)


class AspectTests(SimpleTestCase):
    def test_a_raster_uses_the_tools_visible_size(self):
        self.assertAlmostEqual(api.aspect_of(b"x", StubTool((201, 101))), 201 / 101)

    def test_a_zero_sized_raster_is_square(self):
        self.assertEqual(api.aspect_of(b"x", StubTool((0, 5))), 1.0)

    def test_svg_viewbox_then_size_attributes(self):
        tool = StubTool(None)
        self.assertEqual(api.aspect_of(b'<svg viewBox="0 0 300 200"></svg>', tool), 1.5)
        self.assertEqual(api.aspect_of(b'<svg width="100" height="400"></svg>', tool), 0.25)

    def test_anything_unreadable_is_square(self):
        tool = StubTool(None)
        for junk in (b"not an image", b"", b'<svg viewBox="0 0 0 0"></svg>'):
            self.assertEqual(api.aspect_of(junk, tool), 1.0)
