"""Ingestion Keys SDK for LimaCharlie v2."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .organization import Organization


class IngestionKeys:
    """Ingestion key management for a LimaCharlie organization."""

    def __init__(self, org: Organization) -> None:
        self._org = org

    def list(self) -> Any:
        """List all ingestion keys."""
        return self._org.get_ingestion_keys()

    def create(self, name: str) -> dict[str, Any]:
        """Create a new ingestion key.

        Args:
            name: Key name.

        Returns:
            dict: API response.
        """
        return self._org.create_ingestion_key(name)

    def delete(self, name: str) -> dict[str, Any]:
        """Delete an ingestion key.

        Args:
            name: Key name.

        Returns:
            dict: API response.
        """
        return self._org.delete_ingestion_key(name)
