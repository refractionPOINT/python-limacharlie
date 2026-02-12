"""False Positive Rules SDK for LimaCharlie v2.

Uses the Hive API (fp hive).
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from ..errors import ApiError
from .hive import Hive, HiveRecord

if TYPE_CHECKING:
    from .organization import Organization


class FPRules:
    """False positive rule management."""

    def __init__(self, org: Organization) -> None:
        self._org = org

    def list(self) -> dict[str, Any]:
        hive = Hive(self._org, "fp")
        records = hive.list()
        return {name: rec.to_dict() for name, rec in records.items()}

    def get(self, name: str) -> dict[str, Any] | None:
        hive = Hive(self._org, "fp")
        try:
            record = hive.get(name)
            return record.to_dict()
        except ApiError as e:
            if e.status_code == 404:
                return None
            raise

    def create(self, name: str, data: dict[str, Any]) -> dict[str, Any]:
        hive = Hive(self._org, "fp")
        record = HiveRecord(name, data=data)
        return hive.set(record)

    def delete(self, name: str) -> dict[str, Any]:
        hive = Hive(self._org, "fp")
        return hive.delete(name)
