"""Groups SDK for LimaCharlie v2."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .organization import Organization


class Groups:
    """User group management for a LimaCharlie organization."""

    def __init__(self, org: Organization) -> None:
        self._org = org

    def list(self) -> dict[str, Any]:
        """List all groups."""
        return self._org.get_groups()

    def get(self, group_id: str) -> dict[str, Any]:
        """Get details for a specific group.

        Args:
            group_id: Group identifier.
        """
        return self._org.get_group(group_id)

    def create(self, name: str) -> dict[str, Any]:
        """Create a new group.

        Args:
            name: Group name.
        """
        return self._org.create_group(name)

    def delete(self, group_id: str) -> dict[str, Any]:
        """Delete a group.

        Args:
            group_id: Group identifier.
        """
        return self._org.delete_group(group_id)

    def add_member(self, group_id: str, email: str) -> dict[str, Any]:
        """Add a member to a group.

        Args:
            group_id: Group identifier.
            email: Email address of the user to add.
        """
        return self._org.add_group_member(group_id, email)

    def remove_member(self, group_id: str, email: str) -> dict[str, Any]:
        """Remove a member from a group.

        Args:
            group_id: Group identifier.
            email: Email address of the user to remove.
        """
        return self._org.remove_group_member(group_id, email)

    def add_owner(self, group_id: str, email: str) -> dict[str, Any]:
        """Add an owner to a group.

        Args:
            group_id: Group identifier.
            email: Email address of the user to make owner.
        """
        return self._org.add_group_owner(group_id, email)

    def remove_owner(self, group_id: str, email: str) -> dict[str, Any]:
        """Remove an owner from a group.

        Args:
            group_id: Group identifier.
            email: Email address of the owner to remove.
        """
        return self._org.remove_group_owner(group_id, email)

    def set_permissions(self, group_id: str, permissions: list[str]) -> dict[str, Any]:
        """Set permissions for a group.

        Args:
            group_id: Group identifier.
            permissions: List of permission strings.
        """
        return self._org.set_group_permissions(group_id, permissions)

    def get_logs(self, group_id: str) -> dict[str, Any]:
        """Get audit logs for a group.

        Args:
            group_id: Group identifier.
        """
        return self._org.get_group_logs(group_id)

    def add_org(self, group_id: str, oid: str) -> dict[str, Any]:
        """Add an organization to a group.

        Args:
            group_id: Group identifier.
            oid: Organization ID to add.
        """
        return self._org.add_group_org(group_id, oid)

    def remove_org(self, group_id: str, oid: str) -> dict[str, Any]:
        """Remove an organization from a group.

        Args:
            group_id: Group identifier.
            oid: Organization ID to remove.
        """
        return self._org.remove_group_org(group_id, oid)
