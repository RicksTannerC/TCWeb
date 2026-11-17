"""What the business needs from a print supplier. Any supplier (Printful today, another tomorrow) is
plugged in by writing an adapter that satisfies `Supplier` and passes the contract tests in
`tshirtbrand/adapters/suppliers/tests_supplier_contract.py`."""

from typing import Protocol

from .model import (
    CatalogProduct, ColorOption, OrderRequest, PrintArea, ProductRecord, ProductSpec, SizeMatch,
    SubmittedOrder, SupplierEvent,
)


class SupplierError(Exception):
    """The supplier refused, or could not be reached. The message is fit to show the curator."""


class Supplier(Protocol):
    name: str          # display name, e.g. "Printful"
    simulated: bool    # True when nothing leaves this machine (a stand-in, not the real supplier)

    # --- catalogue (read-only) ---
    def search_catalog(self, query: str) -> list[CatalogProduct]: ...
    def colors(self, catalog_id: str) -> list[ColorOption]: ...
    def match_sizes(self, catalog_id: str, color: str, sizes: list[str]) -> SizeMatch: ...
    def print_area(self, catalog_id: str, placement: str) -> PrintArea | None:
        """The placement's print-file size, or None when the supplier doesn't say."""
    def made_in_us(self, catalog_id: str) -> bool | None:
        """Whether it can be produced and shipped from the US; None when the supplier doesn't say."""

    def dashboard_url(self, product_name: str, product_type: str = "tee") -> str:
        """A best-effort link to this blank in the supplier's own dashboard, or "" when there is none."""

    # --- products ---
    def create_product(self, spec: ProductSpec, color: str = "") -> ProductRecord: ...
    def get_product(self, product_id: str, color: str = "") -> ProductRecord: ...

    # --- orders ---
    def submit_order(self, order: OrderRequest) -> SubmittedOrder: ...
    def cancel_order(self, supplier_order_id: str) -> None: ...

    # --- events ---
    def register_events(self, url: str) -> list[str]:
        """Tell the supplier to call `url`; returns the names of the events subscribed to."""
    def parse_event(self, payload: dict) -> SupplierEvent | None:
        """A supplier's webhook body as a neutral event, or None for anything we don't act on.
        Never raises on odd input."""
