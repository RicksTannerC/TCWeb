from django.contrib import admin
from django.utils.html import format_html

from .models import (
    Collection,
    Design,
    Listing,
    ListingImage,
    ListingSize,
    ProductTemplate,
    Tag,
)

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

    @admin.display(boolean=True, description="Printful")
    def connected(self, obj):
        return obj.is_connected


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
