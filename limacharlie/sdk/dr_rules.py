"""D&R Rules SDK for LimaCharlie v2.

Uses the Hive API (dr-general, dr-managed, dr-service hives).
"""

from ..errors import ApiError
from .hive import Hive, HiveRecord


def _hive_name(namespace):
    return f"dr-{namespace or 'general'}"


class DRRules:
    """D&R rule management for a LimaCharlie organization."""

    def __init__(self, org):
        self._org = org

    def list(self, namespace=None):
        hive = Hive(self._org, _hive_name(namespace))
        records = hive.list()
        return {name: rec.to_dict() for name, rec in records.items()}

    def get(self, name, namespace=None):
        hive = Hive(self._org, _hive_name(namespace))
        try:
            record = hive.get(name)
            return record.to_dict()
        except ApiError as e:
            if e.status_code == 404:
                return None
            raise

    def create(self, name, data, namespace=None):
        hive = Hive(self._org, _hive_name(namespace))
        record = HiveRecord(name, data=data)
        return hive.set(record)

    def update(self, name, data, namespace=None):
        return self.create(name, data, namespace=namespace)

    def delete(self, name, namespace=None):
        hive = Hive(self._org, _hive_name(namespace))
        return hive.delete(name)
