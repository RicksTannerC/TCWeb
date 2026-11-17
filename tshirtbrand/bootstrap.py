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
