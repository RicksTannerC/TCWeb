"""Show, check or register the Printful webhook that reports shipping/production status.

    python manage.py printful_webhook             print the URL Printful should call
    python manage.py printful_webhook --status    ask Printful what is registered (a read)
    python manage.py printful_webhook --register  register that URL with Printful (a write)

--status and --register make real calls to the Printful account, so run them
deliberately, with the real env file. The URL contains a secret derived from SECRET_KEY:
if SECRET_KEY changes, register again.
"""

from django.core.management.base import BaseCommand, CommandError

from shop import printful


class Command(BaseCommand):
    help = "Show, check or register the Printful status webhook."

    def add_arguments(self, parser):
        parser.add_argument("--status", action="store_true", help="read what Printful has registered")
        parser.add_argument("--register", action="store_true", help="register the URL with Printful (write)")

    def handle(self, *args, **options):
        url = printful.webhook_url()
        self.stdout.write(f"Webhook URL for Printful: {url}")
        if not (options["status"] or options["register"]):
            return
        client = printful.get_client()
        if getattr(client, "is_mock", False):
            self.stdout.write("Printful is in mock mode (no real API key): nothing was contacted.")
            return
        try:
            if options["register"]:
                client.set_webhook(url, printful.WEBHOOK_TYPES)
                self.stdout.write(self.style.SUCCESS(
                    "Registered for: " + ", ".join(printful.WEBHOOK_TYPES)))
            current = client._get("/webhooks")
        except printful.PrintfulError as exc:
            raise CommandError(f"Printful said: {exc}")
        registered = (current or {}).get("url")
        self.stdout.write(f"Printful now has: {registered or 'no webhook registered'}")
        self.stdout.write("Matches this site: " + ("yes" if registered == url else "NO"))
