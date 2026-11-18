"""The console's URL table: every name still resolves, every view lives in one of the console's modules."""

from django.test import SimpleTestCase
from django.urls import reverse

from .urls import console_patterns

EXPECTED_NAMES = {
    "manage_2fa", "manage_dashboard", "manage_queue", "manage_order", "manage_order_approve", "manage_order_refund",
    "manage_order_simulate", "manage_fulfillment_reprint", "manage_fulfillment_cancel", "manage_listings",
    "manage_listings_intake", "manage_listing_edit", "manage_listing_printful", "manage_listing_match_printful_sizes",
    "manage_listing_print_add", "manage_listing_print_update", "manage_listing_delete", "manage_listing_replace_artwork",
    "manage_listing_print_replace_artwork", "manage_listing_print_delete", "manage_listing_resend_printful",
    "manage_listing_refresh_preview", "manage_listing_refresh_printful_sizes", "manage_listing_status",
    "manage_listing_update_printful", "manage_listing_preview_panel",
    "manage_listing_add_image", "manage_listing_mockups", "manage_image_move", "manage_image_delete",
    "manage_design_artwork", "manage_catalogue_setup", "manage_collections", "manage_collection_create",
    "manage_collection_edit", "manage_collection_toggle", "manage_collection_toggle_landing", "manage_money",
    "manage_pricing", "manage_pricing_update", "manage_templates", "manage_template_new", "manage_template_edit",
    "manage_template_delete", "manage_template_printful_search", "manage_books", "manage_overhead_add",
    "manage_overhead_delete", "manage_content", "manage_inbox", "manage_message_toggle", "manage_pages",
    "manage_page_new", "manage_page_edit",
}


class ConsoleUrlTests(SimpleTestCase):
    def test_no_console_url_was_lost_or_renamed(self):
        self.assertEqual({p.name for p in console_patterns}, EXPECTED_NAMES)

    def test_every_name_still_reverses_under_the_shop_namespace(self):
        for p in console_patterns:
            kwargs = {k: 1 for k in p.pattern.regex.groupindex}
            kwargs = {k: ("tok" if k == "token" else v) for k, v in kwargs.items()}
            self.assertTrue(reverse(f"shop:{p.name}", kwargs=kwargs).startswith("/manage/"), p.name)

    def test_every_view_lives_in_a_console_module_or_the_platform_two_factor_check(self):
        for p in console_patterns:
            module = p.callback.__module__
            self.assertTrue(module.startswith("tshirtbrand.entrypoints.console.") or module == "shop.two_factor",
                            f"{p.name} is served from {module}")
