"""Installation Keys SDK for LimaCharlie v2."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .organization import Organization


class InstallationKeys:
    def __init__(self, org: Organization) -> None:
        self._org = org

    def list(self) -> dict[str, Any]:
        return self._org.get_installation_keys()

    def get(self, iid: str) -> dict[str, Any]:
        return self._org.get_installation_key(iid)

    def create(self, description: str, tags: list[str] | str | None = None, use_public_ca: bool = False) -> dict[str, Any]:
        return self._org.create_installation_key(description, tags=tags, use_public_ca=use_public_ca)

    def delete(self, iid: str) -> dict[str, Any]:
        return self._org.delete_installation_key(iid)
