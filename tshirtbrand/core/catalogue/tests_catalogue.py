"""The catalogue context on its own: product kinds and the pricing rule."""

from decimal import Decimal

from django.test import SimpleTestCase

from . import api


class PricingTests(SimpleTestCase):
    def test_landed_cost_is_base_plus_shipping(self):
        self.assertEqual(api.landed_cost(Decimal("11"), Decimal("5")), Decimal("16"))

    def test_suggested_price_is_two_and_a_half_times_landed_rounded_to_whole_dollars(self):
        self.assertEqual(api.suggested_price(Decimal("16")), Decimal("40"))
        self.assertEqual(api.suggested_price(Decimal("13.40")), Decimal("34"))   # 33.5 rounds up
        self.assertEqual(api.suggested_price(Decimal("0")), Decimal("0"))

    def test_a_kind_can_carry_its_own_rule(self):
        rule = api.PricingRule(multiplier=Decimal("3"), guardrail=Decimal("2.5"))
        self.assertEqual(api.suggested_price(Decimal("10"), rule), Decimal("30"))
        self.assertTrue(api.below_guardrail(Decimal("24"), Decimal("10"), rule))
        self.assertFalse(api.below_guardrail(Decimal("24"), Decimal("10")))   # standard guardrail is 2.0

    def test_margin_figures(self):
        self.assertEqual(api.margin_dollars(Decimal("40"), Decimal("16")), Decimal("24"))
        self.assertEqual(api.margin_multiple(Decimal("40"), Decimal("16")), Decimal("2.50"))

    def test_an_unknown_cost_has_no_margin_and_no_flag(self):
        self.assertIsNone(api.margin_multiple(Decimal("40"), Decimal("0")))
        self.assertFalse(api.below_guardrail(Decimal("40"), Decimal("0")))

    def test_under_two_times_is_flagged_exactly_two_times_is_not(self):
        self.assertTrue(api.below_guardrail(Decimal("31.50"), Decimal("16")))
        self.assertFalse(api.below_guardrail(Decimal("32"), Decimal("16")))


class KindTests(SimpleTestCase):
    def test_the_kinds_the_shop_sells(self):
        self.assertEqual(sorted(api.KINDS), ["mug", "sticker", "sweatshirt", "tee"])

    def test_a_stickers_page_slug_is_marked(self):
        self.assertEqual(api.kind_for("sticker").slug_suffix, "-sticker")
        self.assertEqual(api.kind_for("tee").slug_suffix, "")

    def test_an_unknown_kind_never_breaks_a_page(self):
        kind = api.kind_for("hoodie")
        self.assertEqual((kind.code, kind.slug_suffix, kind.price_ceiling), ("hoodie", "", None))
        self.assertEqual(api.kind_for("").code, "")


class TemplateWarningTests(SimpleTestCase):
    def warn(self, code, landed, sizes=True):
        return api.template_warnings(api.kind_for(code), Decimal(landed), sizes)

    def test_a_healthy_template_has_none(self):
        self.assertEqual(self.warn("tee", "16"), [])

    def test_zero_cost_and_no_sizes(self):
        self.assertEqual(self.warn("tee", "0", sizes=False),
                         ["Costs are $0, so listings would be priced at $0.", "No sizes."])

    def test_a_tee_over_its_ceiling(self):
        self.assertEqual(self.warn("tee", "17"), ["Suggested price is over the $40 tee ceiling."])   # 42.5 -> 43

    def test_only_kinds_with_a_ceiling_are_checked(self):
        self.assertEqual(self.warn("sticker", "100"), [])
