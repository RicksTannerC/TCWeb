from django.contrib import admin, messages

from . import printful
from .models import (
    Collection,
    Design,
    Listing,
    ListingImage,
    ListingSize,
    ProductTemplate,
    Tag,
)
from .console import ContactMessage, OverheadEntry
from .orders import Fulfillment, Order, OrderItem, Subscriber

# The bespoke curator's console is Milestone 4. Until then, the Django admin
# is the working surface for the catalogue.


class ListingSizeInline(admin.TabularInline):
    model = ListingSize
    extra = 0


class ListingImageInline(admin.TabularInline):
    model = ListingImage
    extra = 0


class ListingInline(admin.StackedInline):
    model = Listing
    extra = 0
    fields = ("product_type", "template", "color", "status", "price", "collection")
    show_change_link = True


@admin.register(Design)
class DesignAdmin(admin.ModelAdmin):
    list_display = ("title", "listing_count", "has_artwork", "created")
    search_fields = ("title", "story")
    prepopulated_fields = {"slug": ("title",)}
    filter_horizontal = ("tags",)
    inlines = [ListingInline]

    @admin.display(description="listings")
    def listing_count(self, obj):
        return obj.listings.count()

    @admin.display(boolean=True, description="art")
    def has_artwork(self, obj):
        return bool(obj.artwork)


@admin.register(Listing)
class ListingAdmin(admin.ModelAdmin):
    list_display = (
        "design", "product_type", "color", "status",
        "price", "margin_multiple", "connected", "collection",
    )
    list_filter = ("status", "product_type", "collection")
    search_fields = ("design__title", "color")
    autocomplete_fields = ("design",)
    inlines = [ListingSizeInline, ListingImageInline]
    readonly_fields = ("landed_cost", "suggested_price", "margin_dollars", "margin_multiple")
    actions = ["send_to_printful"]

    @admin.display(boolean=True, description="Printful")
    def connected(self, obj):
        return obj.is_connected

    @admin.action(description="Send selected listings to Printful")
    def send_to_printful(self, request, queryset):
        done, failed = 0, 0
        for listing in queryset:
            try:
                printful.sync_listing(listing)
                done += 1
            except printful.PrintfulError as exc:
                failed += 1
                self.message_user(request, f"{listing}: {exc}", level=messages.ERROR)
        if done:
            self.message_user(request, f"Sent {done} listing(s) to Printful.", level=messages.SUCCESS)


@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    list_display = ("name", "status", "is_base", "listing_count", "go_live_at")
    list_filter = ("status", "is_base")
    prepopulated_fields = {"slug": ("name",)}

    @admin.display(description="listings")
    def listing_count(self, obj):
        return obj.listings.count()


@admin.register(ProductTemplate)
class ProductTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "product_type", "base_cost", "shipping_est")
    list_filter = ("product_type",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}


# ---------------------------------------------------------------- orders


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("design_title", "product_type", "color", "size_label",
                       "quantity", "unit_price", "unit_supplier_cost", "line_total")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class FulfillmentInline(admin.StackedInline):
    model = Fulfillment
    extra = 0
    filter_horizontal = ("items",)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("reference", "email", "status", "grand_total", "margin", "created")
    list_filter = ("status", "created")
    search_fields = ("email", "name", "stripe_session_id", "id")
    readonly_fields = (
        "reference", "stripe_session_id", "stripe_payment_intent", "track_token",
        "items_total", "shipping_total", "tax_total", "grand_total",
        "supplier_cost", "margin", "shipping_address", "created", "updated",
    )
    inlines = [OrderItemInline, FulfillmentInline]

    def has_add_permission(self, request):
        return False


@admin.register(Subscriber)
class SubscriberAdmin(admin.ModelAdmin):
    list_display = ("email", "is_active", "source", "created")
    list_filter = ("is_active", "source")
    search_fields = ("email", "name")
    readonly_fields = ("unsubscribe_token", "created")


@admin.register(OverheadEntry)
class OverheadEntryAdmin(admin.ModelAdmin):
    list_display = ("incurred_on", "label", "category", "amount")
    list_filter = ("category",)
    date_hierarchy = "incurred_on"


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("email", "subject", "order", "handled", "created")
    list_filter = ("handled",)
    search_fields = ("email", "name", "subject", "body")
    autocomplete_fields = ("order",)
