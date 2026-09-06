"""
Seed the launch catalogue: one base collection, two product templates, and
seven shirt designs (each with a tee listing + an in-card sticker listing).

Placeholder data — real artwork is dropped in through the console (Milestone 4).
Idempotent: safe to run repeatedly.
"""

from decimal import Decimal

from django.core.management.base import BaseCommand

from shop.models import (
    Collection,
    Design,
    Listing,
    ListingSize,
    ProductTemplate,
    ProductType,
    Status,
    Tag,
)

TEE_SIZES = [
    {"label": "S", "width_in": 18, "height_in": 28},
    {"label": "M", "width_in": 20, "height_in": 29},
    {"label": "L", "width_in": 22, "height_in": 30},
    {"label": "XL", "width_in": 24, "height_in": 31},
    {"label": "2XL", "width_in": 26, "height_in": 32},
]

DESIGNS = [
    ("Sea of Fog", "Fog Grey", "A figure at the summit, the valley gone to cloud. After Friedrich.",
     ["romantic", "solitude", "mountains"]),
    ("Pillars", "Charcoal", "Columns of gas and dust, light-years tall, lit from within.",
     ["cosmic", "nebula"]),
    ("Carina", "Deep Olive", "The edge of a star-forming cliff, rendered in infrared.",
     ["cosmic", "nebula"]),
    ("The Wanderer", "Bone", "Small against the vast — the Romantic figure, walking on.",
     ["romantic", "solitude"]),
    ("Deep Field", "Black", "Thousands of galaxies in a patch of sky the size of a grain of sand.",
     ["cosmic", "deep-field"]),
    ("Aurora Line", "Slate", "A ribbon of charged light along the night horizon.",
     ["romantic", "sky"]),
    ("Cold Summit", "Iron", "Bare rock, thin air, and the long view down.",
     ["mountains", "solitude"]),
]


class Command(BaseCommand):
    help = "Seeds the launch catalogue (7 shirt designs + sticker versions)."

    def handle(self, *args, **options):
        base, _ = Collection.objects.get_or_create(
            slug="the-t-shirt-shop",
            defaults={"name": "The T-Shirt Shop", "is_base": True, "status": Status.LIVE},
        )

        tee_tpl, _ = ProductTemplate.objects.get_or_create(
            slug="standard-tee",
            defaults={
                "name": "Standard Tee — front print",
                "product_type": ProductType.TEE,
                "base_cost": Decimal("11.00"),
                "shipping_est": Decimal("5.00"),
                "default_sizes": TEE_SIZES,
                "print_placement": "front",
            },
        )
        sticker_tpl, _ = ProductTemplate.objects.get_or_create(
            slug="die-cut-sticker",
            defaults={
                "name": "Die-cut sticker — 3in",
                "product_type": ProductType.STICKER,
                "base_cost": Decimal("1.80"),
                "shipping_est": Decimal("0.50"),
                "default_sizes": [{"label": '3"', "width_in": 3, "height_in": 3}],
            },
        )

        made = 0
        for order, (title, color, story, tags) in enumerate(DESIGNS):
            design, created = Design.objects.get_or_create(
                slug=title.lower().replace(" ", "-"),
                defaults={"title": title, "story": story},
            )
            design.tags.set(Tag.objects.get_or_create(name=t)[0] for t in tags)

            tee = self._listing(design, tee_tpl, color, Decimal("35.00"), base, order)
            self._sizes(tee, TEE_SIZES)

            sticker = self._listing(design, sticker_tpl, "", Decimal("4.00"), base, order)
            self._sizes(sticker, [{"label": '3"', "width_in": 3, "height_in": 3}])

            if created:
                made += 1

        self.stdout.write(self.style.SUCCESS(
            f"Catalogue seeded — {made} new design(s), {Listing.objects.count()} listing(s) total."
        ))

    def _listing(self, design, template, color, price, collection, order):
        listing, _ = Listing.objects.get_or_create(
            design=design,
            product_type=template.product_type,
            defaults={
                "template": template,
                "color": color,
                "status": Status.LIVE,
                "price": price,
                "base_cost": template.base_cost,
                "shipping_est": template.shipping_est,
                "collection": collection,
                "sort_order": order,
            },
        )
        return listing

    def _sizes(self, listing, sizes):
        for i, s in enumerate(sizes):
            ListingSize.objects.get_or_create(
                listing=listing,
                label=s["label"],
                defaults={
                    "width_in": s.get("width_in"),
                    "height_in": s.get("height_in"),
                    "sort_order": i,
                },
            )
