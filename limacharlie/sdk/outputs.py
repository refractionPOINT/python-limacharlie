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
        return self._org.get_outputs()

    def create(self, name: str, module: str, data_type: str, **kwargs: Any) -> dict[str, Any]:
        return self._org.add_output(name, module, data_type, **kwargs)

    def delete(self, name: str) -> dict[str, Any]:
        return self._org.delete_output(name)
