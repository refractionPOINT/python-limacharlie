"""Hive SDK class for LimaCharlie v2.

Hive is a key-value store for LimaCharlie configuration data.
Supports records with data, metadata, etag-based transactions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, TYPE_CHECKING
from urllib.parse import quote as urlescape

if TYPE_CHECKING:
    from ..client import Client
    from .organization import Organization


@dataclass
class HiveRecord:
    """Represents a record in a Hive."""

    name: str
    data: dict[str, Any] | None = None
    arl: str | None = None
    expiry: int | None = None
    enabled: bool | None = None
    tags: list[str] | None = None
    comment: str | None = None
    etag: str | None = None
    created_at: int | None = None
    created_by: str | None = None
    guid: str | None = None
    last_author: str | None = None
    last_modified: int | None = None
    last_error: str | None = None
    last_error_ts: int | None = None

    @classmethod
    def from_raw(cls, name: str, raw: dict[str, Any]) -> HiveRecord:
        """Create from API response format.

        Args:
            name: Record name/key.
            raw: Raw API response dict (has 'data', 'usr_mtd', 'sys_mtd').
        """
        data = raw.get("data")
        if data is not None and not isinstance(data, dict):
            data = json.loads(data)
        usr = raw.get("usr_mtd", {})
        sys_mtd = raw.get("sys_mtd", {})
        return cls(
            name=name,
            data=data,
            expiry=usr.get("expiry"),
            enabled=usr.get("enabled"),
            tags=usr.get("tags"),
            comment=usr.get("comment"),
            etag=sys_mtd.get("etag"),
            created_at=sys_mtd.get("created_at"),
            created_by=sys_mtd.get("created_by"),
            guid=sys_mtd.get("guid"),
            last_author=sys_mtd.get("last_author"),
            last_modified=sys_mtd.get("last_mod"),
            last_error=sys_mtd.get("last_error"),
            last_error_ts=sys_mtd.get("last_error_ts"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dict matching the API format."""
        result: dict[str, Any] = {"data": self.data, "usr_mtd": {}, "sys_mtd": {}}
        if self.expiry is not None:
            result["usr_mtd"]["expiry"] = self.expiry
        if self.enabled is not None:
            result["usr_mtd"]["enabled"] = self.enabled
        if self.tags is not None:
            result["usr_mtd"]["tags"] = self.tags
        if self.comment is not None:
            result["usr_mtd"]["comment"] = self.comment
        if self.etag:
            result["sys_mtd"]["etag"] = self.etag
        return result


class Hive:
    """Client for a specific Hive type in a LimaCharlie organization.

    Usage:
        hive = Hive(org, "dr-general")
        records = hive.list()
        record = hive.get("my-rule")
    """

    def __init__(self, org: Organization, hive_name: str, partition_key: str | None = None) -> None:
        """Initialize a Hive client.

        Args:
            org: Organization instance.
            hive_name: Hive type name (e.g., 'dr-general', 'secret', 'lookup').
            partition_key: Optional partition key (defaults to org OID).
        """
        self._org = org
        self._hive_name = hive_name
        self._partition_key = partition_key or org.oid

    @property
    def client(self) -> Client:
        """The underlying API client."""
        return self._org.client

    def list(self) -> dict[str, HiveRecord]:
        """List all records in this hive.

        Returns:
            dict: Mapping of record name -> HiveRecord.
        """
        resp = self.client.request("GET", f"hive/{self._hive_name}/{self._partition_key}")
        return {
            name: HiveRecord.from_raw(name, record)
            for name, record in resp.items()
        }

    def get(self, record_name: str) -> HiveRecord:
        """Get a record by name.

        Args:
            record_name: Record key.

        Returns:
            HiveRecord: The record.
        """
        resp = self.client.request(
            "GET",
            f"hive/{self._hive_name}/{self._partition_key}/{urlescape(record_name, safe='')}/data",
        )
        return HiveRecord.from_raw(record_name, resp)

    def get_metadata(self, record_name: str) -> HiveRecord:
        """Get only the metadata for a record.

        Args:
            record_name: Record key.

        Returns:
            HiveRecord: Record with metadata only.
        """
        resp = self.client.request(
            "GET",
            f"hive/{self._hive_name}/{self._partition_key}/{urlescape(record_name, safe='')}/mtd",
        )
        return HiveRecord.from_raw(record_name, resp)

    def set(self, record: HiveRecord) -> dict[str, Any]:
        """Create or update a record.

        Args:
            record: HiveRecord instance with data and optional metadata.

        Returns:
            dict: API response.
        """
        target = "mtd"
        if record.data is not None or record.arl is not None:
            target = "data"

        req = {"data": json.dumps(record.data)}

        if record.etag is not None:
            req["etag"] = record.etag

        usr_mtd = {}
        if record.expiry is not None:
            usr_mtd["expiry"] = record.expiry
        if record.enabled is not None:
            usr_mtd["enabled"] = record.enabled
        if record.tags is not None:
            usr_mtd["tags"] = record.tags
        if record.comment is not None:
            usr_mtd["comment"] = record.comment
        if usr_mtd:
            req["usr_mtd"] = json.dumps(usr_mtd)

        if record.arl is not None:
            req["arl"] = record.arl

        return self.client.request(
            "POST",
            f"hive/{self._hive_name}/{self._partition_key}/{urlescape(record.name, safe='')}/{target}",
            params=req,
        )

    def delete(self, record_name: str) -> dict[str, Any]:
        """Delete a record.

        Args:
            record_name: Record key.

        Returns:
            dict: API response.
        """
        return self.client.request(
            "DELETE",
            f"hive/{self._hive_name}/{self._partition_key}/{urlescape(record_name, safe='')}",
        )

    def validate(self, record: HiveRecord) -> dict[str, Any]:
        """Validate a record without saving it.

        Args:
            record: HiveRecord instance.

        Returns:
            dict: Validation result.
        """
        req = {"data": json.dumps(record.data)}

        if record.etag is not None:
            req["etag"] = record.etag

        usr_mtd = {}
        if record.expiry is not None:
            usr_mtd["expiry"] = record.expiry
        if record.enabled is not None:
            usr_mtd["enabled"] = record.enabled
        if record.tags is not None:
            usr_mtd["tags"] = record.tags
        if record.comment is not None:
            usr_mtd["comment"] = record.comment
        if usr_mtd:
            req["usr_mtd"] = json.dumps(usr_mtd)

        if record.arl is not None:
            req["arl"] = record.arl

        return self.client.request(
            "POST",
            f"hive/{self._hive_name}/{self._partition_key}/{urlescape(record.name, safe='')}/validate",
            params=req,
        )

    def rename(self, record_name: str, new_name: str) -> dict[str, Any]:
        """Rename a record.

        Args:
            record_name: Current record key.
            new_name: New record key.

        Returns:
            dict: API response.
        """
        return self.client.request(
            "POST",
            f"hive/{self._hive_name}/{self._partition_key}/{urlescape(record_name, safe='')}/rename",
            query_params={"new_name": new_name},
        )

    def update_tx(self, record_name: str, callback: Callable[[HiveRecord], None], max_retries: int = 5) -> dict[str, Any]:
        """Transactional update with automatic etag retry.

        Fetches the record, calls callback(record), then saves with etag.
        Retries on etag mismatch.

        Args:
            record_name: Record key.
            callback: Function taking a HiveRecord and modifying it in-place.
            max_retries: Max retry attempts.

        Returns:
            dict: API response from final save.
        """
        from ..errors import ApiError

        for _ in range(max_retries):
            record = self.get(record_name)
            callback(record)
            try:
                return self.set(record)
            except ApiError as e:
                if e.status_code == 409 or "ETAG_MISMATCH" in str(e):
                    continue  # etag mismatch, retry
                raise
        raise ApiError("Transaction failed after max retries (etag conflict).", status_code=409)
