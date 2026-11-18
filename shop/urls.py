from django.urls import include, path

from tshirtbrand.entrypoints.console.urls import console_patterns
from tshirtbrand.entrypoints.storefront.urls import storefront_patterns
from tshirtbrand.entrypoints.webhooks.urls import webhook_patterns

app_name = "shop"

# Every URL is served from an entry point under tshirtbrand/entrypoints/; this file only composes them.
# The curator's console is served under /manage/ on the normal host and at the root of the private
# CONSOLE_HOST (see shop.middleware.HostRoutingMiddleware).
public_patterns = storefront_patterns + webhook_patterns

urlpatterns = public_patterns + [path("manage/", include(console_patterns))]
