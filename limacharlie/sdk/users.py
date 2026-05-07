"""Users SDK for LimaCharlie v2."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .organization import Organization


class Users:
    """User management for a LimaCharlie organization."""

    def __init__(self, org: Organization) -> None:
        self._org = org

    def list(self) -> dict[str, Any]:
        """List all users in the organization."""
        return self._org.get_users()

    def invite(self, email: str) -> dict[str, Any]:
        """Invite a user to the organization.

        Args:
            email: Email address of the user to invite.

        Returns:
            dict: API response.
        """
        return self._org.add_user(email)

    def remove(self, email: str) -> dict[str, Any]:
        """Remove a user from the organization.

        Args:
            email: Email address of the user to remove.

        Returns:
            dict: API response.
        """
        return self._org.remove_user(email)

    def list_permissions(self) -> dict[str, Any]:
        """List permissions for all users in the organization."""
        return self._org.get_user_permissions()

    def add_permission(self, email: str, permission: str) -> dict[str, Any]:
        """Grant a permission to a user.

        Args:
            email: User email address.
            permission: Permission string to grant.

        Returns:
            dict: API response.
        """
        return self._org.add_user_permission(email, permission)

    def remove_permission(self, email: str, permission: str) -> dict[str, Any]:
        """Revoke a permission from a user.

        Args:
            email: User email address.
            permission: Permission string to revoke.

        Returns:
            dict: API response.
        """
        return self._org.remove_user_permission(email, permission)

    def set_role(self, email: str, role: str) -> dict[str, Any]:
        """Set the role for a user.

        Args:
            email: User email address.
            role: Role name to assign.

        Returns:
            dict: API response.
        """
        return self._org.set_user_role(email, role)
