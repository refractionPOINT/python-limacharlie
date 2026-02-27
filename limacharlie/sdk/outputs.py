"""Outputs SDK for LimaCharlie v2."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .organization import Organization


class Outputs:
    """Output integration management."""

    def __init__(self, org: Organization) -> None:
        self._org = org

    def list(self) -> dict[str, Any]:
        """List all configured outputs."""
        return self._org.get_outputs()

    def create(self, name: str, module: str, data_type: str, **kwargs: Any) -> dict[str, Any]:
        """Create a new output.

        Args:
            name: Output name.
            module: Output module type (e.g. 's3', 'scp', 'slack').
            data_type: Data type to output (e.g. 'event', 'detect', 'audit').
            **kwargs: Additional module-specific parameters.

        Returns:
            dict: API response.
        """
        return self._org.add_output(name, module, data_type, **kwargs)

    def delete(self, name: str) -> dict[str, Any]:
        """Delete an output.

        Args:
            name: Output name.

        Returns:
            dict: API response.
        """
        return self._org.delete_output(name)
