"""ARL (Authenticated Resource Locator) SDK for LimaCharlie v2."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .organization import Organization


class ARL:
    """Resolve and fetch data from Authenticated Resource Locators."""

    def __init__(self, org: Organization) -> None:
        self._org = org

    @property
    def client(self) -> Any:
        """The underlying API client."""
        return self._org.client

    def get(self, arl_url: str) -> dict[str, Any]:
        """Resolve an ARL and return the data.

        Args:
            arl_url: The ARL URL to resolve.

        Returns:
            dict or bytes: Resolved data.
        """
        return self.client.request("GET", f"arl/{self._org.oid}",
                                   query_params={"arl": arl_url})
