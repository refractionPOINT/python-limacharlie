"""Users SDK for LimaCharlie v2."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .organization import Organization


class Users:
    def __init__(self, org: Organization) -> None:
        self._org = org

    def list(self) -> dict[str, Any]:
        return self._org.get_users()

    def invite(self, email: str) -> dict[str, Any]:
        return self._org.add_user(email)

    def remove(self, email: str) -> dict[str, Any]:
        return self._org.remove_user(email)

    def list_permissions(self) -> dict[str, Any]:
        return self._org.get_user_permissions()

    def add_permission(self, email: str, permission: str) -> dict[str, Any]:
        return self._org.add_user_permission(email, permission)

    def remove_permission(self, email: str, permission: str) -> dict[str, Any]:
        return self._org.remove_user_permission(email, permission)

    def set_role(self, email: str, role: str) -> dict[str, Any]:
        return self._org.set_user_role(email, role)
