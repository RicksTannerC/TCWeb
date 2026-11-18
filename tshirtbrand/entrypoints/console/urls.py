"""The console's URLs. Included by shop/urls.py under /manage/ (and at the root of the private console host,
see shop.middleware.HostRoutingMiddleware). The URL names live in the `shop` namespace."""

from django.urls import path

from shop import two_factor

from . import catalogue_setup
from . import content
from . import dashboard
from . import listings
from . import money
from . import orders

console_patterns = [
    path("2fa/", two_factor.verify, name="manage_2fa"),
    path("", dashboard.dashboard, name="manage_dashboard"),

    path("orders/", orders.order_queue, name="manage_queue"),
    path("orders/<int:pk>/", orders.order_manage, name="manage_order"),
    path("orders/<int:pk>/approve/", orders.order_approve, name="manage_order_approve"),
    path("orders/<int:pk>/refund/", orders.order_refund, name="manage_order_refund"),
    path("orders/<int:pk>/simulate/", orders.order_simulate, name="manage_order_simulate"),
    path("fulfillments/<int:pk>/reprint/", orders.fulfillment_reprint, name="manage_fulfillment_reprint"),
    path("fulfillments/<int:pk>/cancel/", orders.fulfillment_cancel, name="manage_fulfillment_cancel"),

    path("listings/", listings.listings, name="manage_listings"),
    path("listings/intake/", listings.listings_intake, name="manage_listings_intake"),
    path("listings/<int:pk>/", listings.listing_edit, name="manage_listing_edit"),
    path("listings/<int:pk>/printful/", listings.listing_send_to_printful, name="manage_listing_printful"),
    path("listings/<int:pk>/match-printful-sizes/", listings.listing_match_printful_sizes, name="manage_listing_match_printful_sizes"),
    path("listings/<int:pk>/prints/add/", listings.listing_print_add, name="manage_listing_print_add"),
    path("listings/<int:pk>/prints/<int:print_pk>/", listings.listing_print_update, name="manage_listing_print_update"),
    path("listings/<int:pk>/delete/", listings.listing_delete, name="manage_listing_delete"),
    path("listings/<int:pk>/replace-artwork/", listings.listing_replace_artwork, name="manage_listing_replace_artwork"),
    path("listings/<int:pk>/prints/<int:print_pk>/replace-artwork/", listings.listing_print_replace_artwork,
         name="manage_listing_print_replace_artwork"),
    path("listings/<int:pk>/prints/<int:print_pk>/delete/", listings.listing_print_delete, name="manage_listing_print_delete"),
    path("listings/<int:pk>/resend-to-printful/", listings.listing_resend_to_printful, name="manage_listing_resend_printful"),
    path("listings/<int:pk>/refresh-preview/", listings.listing_refresh_preview, name="manage_listing_refresh_preview"),
    path("listings/<int:pk>/update-printful/", listings.listing_update_printful, name="manage_listing_update_printful"),
    path("listings/<int:pk>/preview-panel/", listings.listing_preview_panel, name="manage_listing_preview_panel"),
    path("listings/<int:pk>/refresh-printful-sizes/", listings.listing_refresh_printful_sizes, name="manage_listing_refresh_printful_sizes"),
    path("listings/<int:pk>/status/", listings.listing_set_status, name="manage_listing_status"),
    path("listings/<int:pk>/image/", listings.listing_add_image, name="manage_listing_add_image"),
    path("listings/<int:pk>/mockups/", listings.listing_generate_mockups, name="manage_listing_mockups"),
    path("images/<int:pk>/move/", listings.image_move, name="manage_image_move"),
    path("images/<int:pk>/delete/", listings.image_delete, name="manage_image_delete"),
    path("designs/<int:pk>/artwork/", listings.design_artwork, name="manage_design_artwork"),

    # Catalogue setup: product templates + collections, one merged page.
    # The bare /templates/ and /collections/ URLs below still work (they
    # redirect here) so nothing that already links to them breaks.
    path("catalogue/setup/", catalogue_setup.catalogue_setup, name="manage_catalogue_setup"),

    path("collections/", catalogue_setup.collections, name="manage_collections"),
    path("collections/create/", catalogue_setup.collection_create, name="manage_collection_create"),
    path("collections/<int:pk>/", catalogue_setup.collection_edit, name="manage_collection_edit"),
    path("collections/<int:pk>/toggle/", catalogue_setup.collection_toggle, name="manage_collection_toggle"),
    path("collections/<int:pk>/toggle-landing/", catalogue_setup.collection_toggle_landing, name="manage_collection_toggle_landing"),

    # Money: pricing + books, one merged page. /pricing/ and /books/ still
    # work (they redirect here).
    path("money/", money.money, name="manage_money"),

    path("pricing/", money.pricing, name="manage_pricing"),
    path("pricing/update/", money.pricing_update, name="manage_pricing_update"),

    path("templates/", catalogue_setup.product_templates, name="manage_templates"),
    path("templates/new/", catalogue_setup.product_template_edit, name="manage_template_new"),
    path("templates/<int:pk>/", catalogue_setup.product_template_edit, name="manage_template_edit"),
    path("templates/<int:pk>/delete/", catalogue_setup.product_template_delete, name="manage_template_delete"),
    path("templates/printful-search/", catalogue_setup.template_printful_search, name="manage_template_printful_search"),

    path("books/", money.books, name="manage_books"),
    path("books/overhead/add/", money.overhead_add, name="manage_overhead_add"),
    path("books/overhead/<int:pk>/delete/", money.overhead_delete, name="manage_overhead_delete"),

    # Content: messages (inbox) + pages, one merged page. /messages/ and
    # /pages/ still work (they redirect here).
    path("content/", content.content, name="manage_content"),

    path("messages/", content.inbox, name="manage_inbox"),
    path("messages/<int:pk>/toggle/", content.message_toggle, name="manage_message_toggle"),

    path("pages/", content.pages, name="manage_pages"),
    path("pages/new/", content.page_edit, name="manage_page_new"),
    path("pages/<int:pk>/", content.page_edit, name="manage_page_edit"),
]
