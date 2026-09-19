"""
Enroll a staff user for two-factor sign-in (authenticator app + backup codes).

    python manage.py otp_setup <username>            # first-time setup
    python manage.py otp_setup <username> --reset    # replace a lost/changed device

Enrollment is deliberately command-line only: someone who has just stolen a
password cannot enroll their own authenticator through the website. The QR code
and backup codes are printed to this terminal. The authenticator key and backup
codes also live in the database, so treat the database like a password store.
"""

import io
from urllib.parse import parse_qs, urlparse

import qrcode
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice

BACKUP_CODE_COUNT = 8


class Command(BaseCommand):
    help = "Enroll a staff user for authenticator-app sign-in and print backup codes."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument(
            "--reset", action="store_true",
            help="Delete existing second-factor devices for this user and enroll a new one.",
        )

    def handle(self, *args, username, reset, **options):
        User = get_user_model()
        try:
            user = User.objects.get(**{User.USERNAME_FIELD: username})
        except User.DoesNotExist:
            raise CommandError(f"No such user: {username}")
        if not user.is_staff:
            raise CommandError(f"{username} is not a staff user.")

        has_device = (
            TOTPDevice.objects.filter(user=user).exists()
            or StaticDevice.objects.filter(user=user).exists()
        )
        if has_device and not reset:
            raise CommandError(
                f"{username} is already enrolled. Use --reset to replace the "
                "authenticator (this invalidates the old device and backup codes)."
            )
        if reset:
            TOTPDevice.objects.filter(user=user).delete()
            StaticDevice.objects.filter(user=user).delete()

        device = TOTPDevice.objects.create(user=user, name="authenticator", confirmed=True)
        backup = StaticDevice.objects.create(user=user, name="backup codes", confirmed=True)
        codes = []
        for _ in range(BACKUP_CODE_COUNT):
            token = StaticToken.random_token()
            StaticToken.objects.create(device=backup, token=token)
            codes.append(token)

        url = device.config_url
        secret = parse_qs(urlparse(url).query).get("secret", [""])[0]

        qr = qrcode.QRCode(border=1)
        qr.add_data(url)
        qr.make(fit=True)
        art = io.StringIO()
        qr.print_ascii(out=art, invert=True)

        w = self.stdout.write
        w(self.style.SUCCESS(f"\nTwo-factor enabled for {username}.\n"))
        w("1. Scan this QR code with an authenticator app (Google Authenticator,")
        w("   Microsoft Authenticator, 1Password, Authy, ...):\n")
        w(art.getvalue())
        w("   Can't scan? Enter this key manually (time-based, 6 digits):")
        w(f"   {secret}\n")
        w("2. Save these one-time backup codes somewhere safe. They are shown only")
        w("   now, and each works once if you lose your phone:\n")
        for code in codes:
            w(f"   {code}")
        w("\nClear this terminal when you're done; anyone who sees the key or codes can sign in.")
