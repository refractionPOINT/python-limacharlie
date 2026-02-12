"""False Positive Rules SDK for LimaCharlie v2.

Uses the Hive API (fp hive).
"""

from ..errors import ApiError
from .hive import Hive, HiveRecord


class FPRules:
    """False positive rule management."""

    def __init__(self, org):
        self._org = org

    def list(self):
        hive = Hive(self._org, "fp")
        records = hive.list()
        return {name: rec.to_dict() for name, rec in records.items()}

    def get(self, name):
        hive = Hive(self._org, "fp")
        try:
            record = hive.get(name)
            return record.to_dict()
        except ApiError as e:
            if e.status_code == 404:
                return None
            raise

    def create(self, name, data):
        hive = Hive(self._org, "fp")
        record = HiveRecord(name, data=data)
        return hive.set(record)

    def delete(self, name):
        hive = Hive(self._org, "fp")
        return hive.delete(name)
