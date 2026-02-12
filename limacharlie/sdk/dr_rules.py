"""D&R Rules SDK for LimaCharlie v2.

Uses the Hive API (dr-general, dr-managed, dr-service hives).
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from ..errors import ApiError
from .hive import Hive, HiveRecord

if TYPE_CHECKING:
    from .organization import Organization


def _hive_name(namespace: str | None) -> str:
    return f"dr-{namespace or 'general'}"


class DRRules:
    """D&R rule management for a LimaCharlie organization."""

    def __init__(self, org: Organization) -> None:
        self._org = org

    def list(self, namespace: str | None = None) -> dict[str, Any]:
        hive = Hive(self._org, _hive_name(namespace))
        records = hive.list()
        return {name: rec.to_dict() for name, rec in records.items()}

    def get(self, name: str, namespace: str | None = None) -> dict[str, Any] | None:
        hive = Hive(self._org, _hive_name(namespace))
        try:
            record = hive.get(name)
            return record.to_dict()
        except ApiError as e:
            if e.status_code == 404:
                return None
            raise

    def create(self, name: str, data: dict[str, Any], namespace: str | None = None) -> dict[str, Any]:
        hive = Hive(self._org, _hive_name(namespace))
        record = HiveRecord(name, data=data)
        return hive.set(record)

    def update(self, name: str, data: dict[str, Any], namespace: str | None = None) -> dict[str, Any]:
        return self.create(name, data, namespace=namespace)

    def delete(self, name: str, namespace: str | None = None) -> dict[str, Any]:
        hive = Hive(self._org, _hive_name(namespace))
        return hive.delete(name)
