from django.apps import AppConfig


class ShopConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "shop"

    def ready(self):
        from django.contrib import admin

        # Importing connects the sign-in signal receivers; the admin login (the
        # only password sign-in) then uses the throttled form.
        from . import login_throttle

        admin.site.login_form = login_throttle.ThrottledAdminAuthenticationForm
