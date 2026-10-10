"""
Lift sign-in lockouts from the machine that runs the shop.

    python manage.py clear_login_lockouts                    # everyone, every IP
    python manage.py clear_login_lockouts --username owner   # just that username

Lockouts end by themselves 15 minutes after the last failed attempt; this is for
when you don't want to wait. With --username only that username's failures are
forgotten -- a lock on an IP address is cleared by running without it.
"""

from django.core.management.base import BaseCommand

from shop.console import FailedLogin
from shop.login_throttle import clear_failures


class Command(BaseCommand):
    help = "Clear recorded failed sign-ins so locked-out staff can try again."

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            help="Only clear this username's failures (default: all usernames and IPs).",
        )

    def handle(self, *args, username=None, **options):
        if username:
            removed = clear_failures(username)
            self.stdout.write(f"Cleared {removed} failed sign-in(s) for {username}.")
        else:
            removed = FailedLogin.objects.all().delete()[0]
            self.stdout.write(f"Cleared {removed} failed sign-in(s); every lockout is lifted.")
