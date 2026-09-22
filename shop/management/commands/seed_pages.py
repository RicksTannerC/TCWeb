"""
Seed the launch content pages with starting copy.

Idempotent by slug. The Privacy and Terms drafts are plain-language
starting points that reflect the shop's actual stances — have them
reviewed before a real launch.
"""

from django.core.management.base import BaseCommand

from shop.console import Page

PAGES = [
    {
        "slug": "about",
        "title": "About",
        "footer_order": 1,
        "meta_description": "A one-person, curated print-to-order shirt shop.",
        "body": """\
The T-Shirt Brand is a one-person operation. One person picks the art, picks
the garment, sets the price, and packs nothing — because every shirt is
**printed when you order it** by a print partner.

That's why the selection is small and why it rotates. Rather than list every
design in every color, the shop shows a short, changing set — the pieces that
are worth wearing right now. If something you liked is gone, it may come back.

No warehouse, no overstock, no pressure. Just a good shirt when you want one.
""",
    },
    {
        "slug": "shipping-and-returns",
        "title": "Shipping & Returns",
        "footer_order": 2,
        "meta_description": "How orders ship, and our returns policy.",
        "body": """\
## Shipping

Every order is **printed to order**, so give it a few days to be made before
it ships. You'll get an email when it's in production, another when it ships
(with tracking), and one when it's delivered.

Shipping is **free** — it's built into the price. Sales tax is calculated at
checkout where it applies.

If an order includes items made by different print partners, it may arrive in
**more than one package**, each with its own tracking. We'll tell you if that's
the case.

## Returns

Because each shirt is printed for you individually, we don't accept returns or
exchanges for a change of mind or the wrong size chosen at checkout. Please
use the measurements shown on each listing.

**If something is wrong with your order** — a print defect, the wrong item, or
damage in transit — email us within 30 days and we'll send a replacement or a
full refund, no questions asked. A photo helps but isn't required.

[Contact us](/contact/) and include your order reference.
""",
    },
    {
        "slug": "privacy",
        "title": "Privacy",
        "footer_order": 3,
        "meta_description": "What data we collect and why.",
        "body": """\
_Last updated when this page was published. This is a plain-language summary,
not a substitute for legal advice._

The T-Shirt Brand is operated from Wyoming, USA.

## What we collect

- **When you order:** your email and shipping address, and the items you
  bought. Payment card details go straight to **Stripe** — we never see or
  store them.
- **When you join the new-collection list:** just your email address. Every
  email has a one-click unsubscribe link.
- **When you contact us:** whatever you put in the form.
- **Basic visit data:** the site records which website referred you and any
  campaign tag in the link. We do **not** log IP addresses, set advertising
  cookies, or use third-party trackers.

## What we do with it

We use your details to fulfil and support your order, and — if you opted in —
to email you when a new seasonal collection drops. We share your shipping
details with the print partner making your order, and with Stripe to take
payment. We don't sell your data.

## Your choices

Unsubscribe from the list any time. To ask what we hold about you, or to have
it deleted, [contact us](/contact/).
""",
    },
    {
        "slug": "terms",
        "title": "Terms",
        "footer_order": 4,
        "meta_description": "The terms for using this shop.",
        "body": """\
_Plain-language terms. Have these reviewed before relying on them._

## Orders

Placing an order is an offer to buy. We confirm it by email, and we may
decline or cancel an order (with a full refund) if we can't fulfil it — for
example if an item is discontinued by our print partner.

Prices and availability can change at any time. The selection rotates by
design.

## The artwork

The designs sold here are the shop's own work. Buying a shirt doesn't give you
any right to reproduce, resell, or use the artwork itself.

## Defects and liability

Our responsibility for a faulty order is limited to replacing it or refunding
what you paid. Nothing here limits rights you have under applicable consumer
law.

## Governing law

These terms are governed by the laws of the State of Wyoming, USA.
""",
    },
    {
        "slug": "social",
        "title": "Social",
        "footer_order": 5,
        "meta_description": "Follow the shop.",
        "body": """\
New designs and collection drops are posted here first:

- **Instagram** — @thetshirtshop _(placeholder)_
- **Pinterest** — @thetshirtshop _(placeholder)_

Or join the [new-collection email list](/) — one message when a season drops,
nothing else.
""",
    },
]


class Command(BaseCommand):
    help = "Seeds the launch content pages."

    def handle(self, *args, **options):
        made = 0
        for data in PAGES:
            _, created = Page.objects.get_or_create(
                slug=data["slug"],
                defaults={**data, "status": Page.Status.LIVE, "show_in_footer": True},
            )
            made += int(created)
        self.stdout.write(self.style.SUCCESS(f"Seeded {made} page(s); {Page.objects.count()} total."))
