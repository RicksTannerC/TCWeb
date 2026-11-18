"""Composition root: the one place that names concrete adapters and hands them to the rest of the app.

Everything else asks for a port here (`get_supplier()`) and never imports an adapter. To change which
implementation is used, change it in this file; nothing else moves. See docs/ARCHITECTURE.md."""


def get_supplier():
    """The print supplier the shop is using right now (real when configured, the canned stand-in otherwise).

    Built per call and cheap: the raw client is created from current settings, and the catalogue cache is
    the project's shared cache."""
    from django.core.cache import cache

    from shop import printful  # the settings-aware factory for the raw client (real vs canned)
    from tshirtbrand.adapters.suppliers.printful.supplier import PrintfulSupplier

    return PrintfulSupplier(printful.get_client(), cache=cache)


def get_image_tool():
    """The image tool the artwork context uses to measure and place print files."""
    from tshirtbrand.adapters.imaging.pillow.tool import PillowImageTool

    return PillowImageTool()


def get_gateway():
    """The payment gateway the shop is using right now.

    Without a Stripe secret key (or while the test suite runs: settings.TESTING is a hard guarantee that no test
    can reach Stripe, whatever the environment holds) the gateway is `simulated`: it never calls Stripe. It can
    still verify a signed webhook, which is a local calculation and needs only the webhook secret."""
    from django.conf import settings

    from tshirtbrand.adapters.payments.stripe.gateway import StripeGateway

    key = "" if settings.TESTING else settings.STRIPE_SECRET_KEY
    return StripeGateway(secret_key=key, webhook_secret=settings.STRIPE_WEBHOOK_SECRET)


def get_order_desk():
    """The order use cases, wired to the ORM, the current supplier and payment gateway, and the customer email."""
    from tshirtbrand.adapters.persistence.django_orm.orders import DjangoOrderRepository, EmailNotifier, OrderItemLines
    from tshirtbrand.core.ordering.api import OrderDesk

    return OrderDesk(DjangoOrderRepository(), get_supplier(), OrderItemLines(), EmailNotifier(), get_gateway())


def get_product_desk():
    """The listing/product use cases, wired to the ORM and the current supplier."""
    from tshirtbrand.adapters.persistence.django_orm.listings import DjangoListingRepository
    from tshirtbrand.core.catalogue.api import ProductDesk

    return ProductDesk(DjangoListingRepository(), get_supplier())
