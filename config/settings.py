"""
Django settings for The T-Shirt Shop.

Configuration is environment-driven (see .env.example). Local development
needs no .env at all — the defaults below run a working SQLite site.
"""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, []),
    CSRF_TRUSTED_ORIGINS=(list, []),
)
# Read .env if present (not required in dev).
environ.Env.read_env(BASE_DIR / ".env")

# --- Core ----------------------------------------------------------------

SECRET_KEY = env("SECRET_KEY", default="dev-only-insecure-key-change-me")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = [
    value.strip()
    for value in env.str("ALLOWED_HOSTS", default="localhost,127.0.0.1").split(",")
    if value.strip()
]
CSRF_TRUSTED_ORIGINS = [
    value.strip()
    for value in env.str("CSRF_TRUSTED_ORIGINS", default="").split(",")
    if value.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.sitemaps",
    "django.contrib.staticfiles",
    "django_htmx",
    "django_otp",
    "django_otp.plugins.otp_totp",
    "django_otp.plugins.otp_static",
    "shop",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "shop.middleware.HostRoutingMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_otp.middleware.OTPMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "shop.middleware.StaffTwoFactorMiddleware",
    "shop.middleware.VisitCaptureMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                # {{ cart }} + {{ cart_count }} in every template.
                "shop.context_processors.cart",
                "shop.context_processors.footer_pages",
                "shop.context_processors.site_urls",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# --- Database ----------------------------------------------------------
# Local dev: SQLite by default. Production: set DATABASE_URL to a
# postgres:// URL (Milestone 6).

DATABASES = {
    "default": env.db_url(
        "DATABASE_URL",
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
    )
}

# --- Auth ------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- i18n / tz -------------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = "America/Denver"  # Wyoming
USE_I18N = True
USE_TZ = True

# --- Static & media ------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# shop/static/ is picked up automatically (AppDirectoriesFinder).
STATICFILES_DIRS = []

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
# Print-ready originals. Not served by any public URL; the console reads them
# through a staff-only view. Point this outside any synced folder if you can.
PRIVATE_MEDIA_ROOT = Path(env.str("PRIVATE_MEDIA_ROOT", default=str(BASE_DIR / "private_media")))

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
        if not DEBUG
        else "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

if DEBUG:
    # Don't let the browser cache static assets during development.
    WHITENOISE_AUTOREFRESH = True
    WHITENOISE_MAX_AGE = 0

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Email ---------------------------------------------------------
# EMAIL_URL unset -> console backend (prints to terminal).

_email = env.email_url("EMAIL_URL", default="consolemail://")
EMAIL_BACKEND = _email["EMAIL_BACKEND"]
EMAIL_HOST = _email.get("EMAIL_HOST", "")
EMAIL_PORT = _email.get("EMAIL_PORT", 25)
EMAIL_HOST_USER = _email.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = _email.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = _email.get("EMAIL_USE_TLS", False)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="The T-Shirt Shop <shop@localhost>")

# --- Integrations (wired up later; safe to be blank) ---------------

STRIPE_PUBLISHABLE_KEY = env("STRIPE_PUBLISHABLE_KEY", default="")
STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY", default="")
STRIPE_WEBHOOK_SECRET = env("STRIPE_WEBHOOK_SECRET", default="")
# Stripe Tax: enable once a Wyoming registration is in place (see vision §09).
STRIPE_TAX_ENABLED = env.bool("STRIPE_TAX_ENABLED", default=False)
PRINTFUL_API_KEY = env("PRINTFUL_API_KEY", default="")
# How long a signed print-file link handed to Printful stays valid (seconds).
# Only needs to outlive the moment Printful's servers fetch it after we call
# their API; see shop/printful_delivery.py.
PRINTFUL_ARTWORK_LINK_MAX_AGE = env.int("PRINTFUL_ARTWORK_LINK_MAX_AGE", default=1800)

# Shop identity used in emails / CAN-SPAM footer.
SHOP_NAME = "The T-Shirt Shop"
SHOP_POSTAL_ADDRESS = env(
    "SHOP_POSTAL_ADDRESS", default="The T-Shirt Shop, Wyoming, USA"
)
# Absolute base for links in emails (no request context there).
SITE_BASE_URL = env("SITE_BASE_URL", default="http://127.0.0.1:8000")

# Private console hostname. When set, the console is served at the root of this
# host (e.g. https://manage.example.com/ = dashboard) and nothing else is; other
# public hosts stop serving /manage/ and /admin/. Leave empty for the single-host
# layout (console at /manage/), which is what local development uses.
CONSOLE_HOST = env.str("CONSOLE_HOST", default="").strip().lower()

# --- Two-factor authentication for the console / admin ------------
# Staff must pass an authenticator-app (TOTP) or backup-code check before
# reaching /manage/ or /admin/. Enroll with: manage.py otp_setup <username>
STAFF_2FA_REQUIRED = env.bool("STAFF_2FA_REQUIRED", default=True)
STAFF_2FA_MAX_AGE = env.int("STAFF_2FA_MAX_AGE", default=60 * 60 * 12)  # re-verify after 12h
OTP_TOTP_ISSUER = "The T-Shirt Shop"

# --- Security (production) ----------------------------------------

if not DEBUG:
    # HTTPS is terminated at Cloudflare (Tunnel); the origin only sees plain
    # HTTP plus an X-Forwarded-Proto header. Trusting it is safe because the
    # origin listens on 127.0.0.1 and is reachable only through the tunnel.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    # Off by default so http://127.0.0.1 still works locally (no proxy header
    # there). Cloudflare's "Always Use HTTPS" redirects at the edge; set
    # SECURE_SSL_REDIRECT=True to have Django enforce it as well.
    SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=False)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
