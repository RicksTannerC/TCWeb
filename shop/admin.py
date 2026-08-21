from django.contrib import admin
from .models import Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["name", "color", "price", "active", "created"]
    list_filter = ["active", "color"]
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ["name", "description"]
