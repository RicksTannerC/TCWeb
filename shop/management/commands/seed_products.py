from django.core.management.base import BaseCommand
from shop.models import Product

SEED_PRODUCTS = [
    {
        "name": "Ridgeline Tee",
        "slug": "ridgeline-tee",
        "price": "28.00",
        "color": "Charcoal",
        "description": "Heavyweight cotton tee, crest screen-printed on the chest.",
    },
    {
        "name": "Ascent Tee",
        "slug": "ascent-tee",
        "price": "28.00",
        "color": "Stone",
        "description": "Undyed cotton, raw hem, garment-washed for softness.",
    },
    {
        "name": "Summit Tee",
        "slug": "summit-tee",
        "price": "32.00",
        "color": "Olive",
        "description": "Piece-dyed, embroidered micro mark on the sleeve.",
    },
]


class Command(BaseCommand):
    help = "Seeds the database with placeholder TCR products."

    def handle(self, *args, **options):
        created_count = 0
        for data in SEED_PRODUCTS:
            _, created = Product.objects.get_or_create(
                slug=data["slug"], defaults=data
            )
            if created:
                created_count += 1
        self.stdout.write(
            self.style.SUCCESS(f"Seeded {created_count} product(s).")
        )
