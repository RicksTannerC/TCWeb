"""Brute-force throttling for staff sign-in (password step and second-factor step).

Failures are stored in the database (FailedLogin) so a lockout survives an app
restart, and are counted two ways: per username (default 5 in 15 minutes) and
per client IP (default 15 in 15 minutes). A lock is time-boxed -- it ends one
window after the most recent failure -- so the owner can never be locked out for
good. Locked attempts are never recorded, so hammering a locked account does not
extend the lock, and a locked attempt is rejected before the password or the
code is looked at.

Where it hooks in:
  * the password step is the Django admin login form (every console page sends
    anonymous staff there); ThrottledAdminAuthenticationForm refuses locked
    attempts before authenticate() runs, and failures are recorded from Django's
    user_login_failed signal;
  * the second-factor step is shop/two_factor.py, which calls the helpers below.

Usernames that don't exist are counted exactly like real ones, and the locked
message never says whether the account exists.
"""

import ipaddress
import logging
import math
from datetime import timedelta

from django.conf import settings
from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.db.models import Max
from django.dispatch import receiver
from django.forms import ValidationError
from django.utils import timezone

from .console import FailedLogin

logger = logging.getLogger(__name__)

USERNAME_MAX = 150
IP_MAX = 45
KEEP_ROWS_FOR = timedelta(days=1)  # old rows are pruned whenever a failure is recorded


def enabled():
    return settings.LOGIN_THROTTLE_ENABLED


def _window():
    return timedelta(seconds=settings.LOGIN_THROTTLE_WINDOW_SECONDS)


def normalize_username(username):
    return str(username or "").strip().lower()[:USERNAME_MAX]


def _is_loopback(addr):
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    return (getattr(ip, "ipv4_mapped", None) or ip).is_loopback


def client_ip(request):
    """The visitor's IP address.

    The site is reachable only through a Cloudflare Tunnel, whose connector
    dials the origin from the loopback address, so REMOTE_ADDR is 127.0.0.1 for
    everyone and the real address is in CF-Connecting-IP. That header is
    trustworthy only because nothing else can reach the origin; so it is read
    only when REMOTE_ADDR is itself loopback. A request that arrives from any
    other address is never allowed to name its own IP through a header.
    """
    remote = request.META.get("REMOTE_ADDR", "")
    if _is_loopback(remote):
        try:
            return str(ipaddress.ip_address(request.META.get("HTTP_CF_CONNECTING_IP", "").strip()))
        except ValueError:
            pass
    return remote


def _seconds_left(failures, limit, now):
    """Seconds until the lock implied by these failures ends; 0 when not locked.

    Locked means `limit` failures fell inside one window ending at the most
    recent failure, and the lock lasts one window past that most recent failure.
    """
    window = _window()
    last = failures.aggregate(last=Max("created_at"))["last"]
    if last is None or last + window <= now:
        return 0
    if failures.filter(created_at__gt=last - window).count() < max(limit, 1):
        return 0
    return math.ceil((last + window - now).total_seconds())


def _user_seconds_left(username, now):
    if not username:
        return 0
    return _seconds_left(
        FailedLogin.objects.filter(username=username), settings.LOGIN_THROTTLE_USER_FAILURES, now
    )


def _ip_seconds_left(ip, now):
    if not ip:
        return 0
    return _seconds_left(
        FailedLogin.objects.filter(ip=ip), settings.LOGIN_THROTTLE_IP_FAILURES, now
    )


def lockout_seconds(username, ip):
    """How many seconds this username / IP pair stays locked (0 = free to try)."""
    if not enabled():
        return 0
    now = timezone.now()
    return max(_user_seconds_left(normalize_username(username), now), _ip_seconds_left(ip, now))


def lock_message(seconds):
    minutes = max(1, math.ceil(seconds / 60))
    return f"Too many sign-in attempts. Try again in {minutes} minute{'s' if minutes != 1 else ''}."


def record_failure(username, ip, kind=FailedLogin.Kind.PASSWORD):
    """Count one failed attempt, and log when it tips a username or IP into a lock."""
    if not enabled():
        return
    now = timezone.now()
    name = normalize_username(username)
    ip = (ip or "")[:IP_MAX]
    if max(_user_seconds_left(name, now), _ip_seconds_left(ip, now)):
        return  # already locked: a locked attempt must not extend the lock
    FailedLogin.objects.create(username=name, ip=ip, kind=kind, created_at=now)
    FailedLogin.objects.filter(created_at__lt=now - max(KEEP_ROWS_FOR, _window())).delete()
    # Neither was locked a moment ago, so any lock now is one this failure engaged.
    # Only the (length-capped) username and IP are logged -- never a password or code.
    left = _user_seconds_left(name, now)
    if left:
        logger.warning(
            "Login throttle: username %r locked for %d more minute(s) (last attempt from %s)",
            name, math.ceil(left / 60), ip or "unknown IP",
        )
    left = _ip_seconds_left(ip, now)
    if left:
        logger.warning(
            "Login throttle: IP %s locked for %d more minute(s) (last username tried %r)",
            ip, math.ceil(left / 60), name,
        )


def clear_failures(username, kinds=None):
    """Forget a username's failures (all kinds, or just `kinds`). Returns rows deleted."""
    rows = FailedLogin.objects.filter(username=normalize_username(username))
    if kinds is not None:
        rows = rows.filter(kind__in=kinds)
    return rows.delete()[0]


class ThrottledAdminAuthenticationForm(AdminAuthenticationForm):
    """The admin sign-in form, refusing locked attempts before any password check."""

    def clean(self):
        username = self.cleaned_data.get("username")
        if username:
            left = lockout_seconds(username, client_ip(self.request) if self.request else "")
            if left:
                raise ValidationError(lock_message(left), code="locked")
        return super().clean()


@receiver(user_login_failed)
def _password_failed(sender, credentials, request=None, **kwargs):
    record_failure(credentials.get("username"), client_ip(request) if request else "")


@receiver(user_logged_in)
def _password_ok(sender, user, **kwargs):
    # Only the password failures: a correct password must not reset the count of
    # wrong second-factor codes, or a thief could alternate between the two.
    if enabled():
        clear_failures(user.get_username(), kinds=[FailedLogin.Kind.PASSWORD])
