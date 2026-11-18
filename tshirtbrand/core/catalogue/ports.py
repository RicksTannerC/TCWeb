"""What the catalogue context needs from the outside: somewhere to keep listings."""

from typing import Protocol

from .model import ListingView


class ListingRepository(Protocol):
    def listing(self, listing_id: int) -> ListingView:
        """The listing as it is right now. Raises LookupError when there is none."""

    def print_files(self, listing_id: int) -> tuple:
        """The listing's print areas (main first) as neutral PrintFiles, each with its own freshly made
        artwork link: links are short-lived, so this is called right before they are used."""

    def set_product(self, listing_id: int, product_id: str) -> None: ...

    def clear_variant_ids(self, listing_id: int) -> None:
        """Forget every size's variant id (they belong to ONE supplier product)."""

    def set_variant_ids(self, listing_id: int, ids_by_label: dict) -> None: ...

    def store_previews(self, listing_id: int, previews: tuple) -> None:
        """Keep the supplier's own render of the listing (Preview values) and when it was read."""

    def mark_sent(self, listing_id: int, status: str) -> None:
        """Set the status and remember what was sent (shirt, colour, placement, print layout) so a later change
        shows as needing a re-send."""
