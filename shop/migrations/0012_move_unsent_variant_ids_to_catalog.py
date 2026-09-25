from django.db import migrations


def move_unsent_ids(apps, schema_editor):
    """For a listing that has never been sent to Printful, any stored variant id
    came from "Match sizes", i.e. it is a catalogue id. Move it to the field that
    now holds catalogue ids. Listings already on Printful keep theirs as-is
    (those are sync variant ids)."""
    ListingSize = apps.get_model("shop", "ListingSize")
    for size in ListingSize.objects.filter(listing__printful_product_id="").exclude(printful_variant_id=""):
        size.printful_catalog_variant_id = size.printful_variant_id
        size.printful_variant_id = ""
        size.save(update_fields=["printful_catalog_variant_id", "printful_variant_id"])


def move_back(apps, schema_editor):
    ListingSize = apps.get_model("shop", "ListingSize")
    for size in ListingSize.objects.filter(listing__printful_product_id="").exclude(printful_catalog_variant_id=""):
        size.printful_variant_id = size.printful_catalog_variant_id
        size.printful_catalog_variant_id = ""
        size.save(update_fields=["printful_catalog_variant_id", "printful_variant_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("shop", "0011_printful_catalog_ids_and_sent_snapshot"),
    ]

    operations = [
        migrations.RunPython(move_unsent_ids, move_back),
    ]
