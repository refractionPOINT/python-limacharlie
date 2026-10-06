"""Hive SDK class for LimaCharlie v2.

Hive is a key-value store for LimaCharlie configuration data.
Supports records with data, metadata, etag-based transactions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, TYPE_CHECKING
from urllib.parse import quote as urlescape

from ..errors import ApiError

if TYPE_CHECKING:
    from ..client import Client
    from .organization import Organization


def is_record_not_found(exc: Exception) -> bool:
    """Check whether an exception is the API's RECORD_NOT_FOUND answer.

    The gateway reports a missing record as HTTP 400 whose body error is
    ``"lc_error_code:RECORD_NOT_FOUND - ..."``, not as a 404, so the code in
    the body is the only reliable signal. Any other failure (permissions,
    network, unknown hive, ...) is not "the record is missing".

    Args:
        exc: The exception raised by a hive read.

    Returns:
        bool: True only for a missing-record answer.
    """
    if not isinstance(exc, ApiError) or not isinstance(exc.response_body, dict):
        return False
    error = exc.response_body.get("error")
    return isinstance(error, str) and error.startswith("lc_error_code:RECORD_NOT_FOUND")


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
    ui_actions: list[dict[str, str]] | None = None
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

        Returns:
            HiveRecord: Populated record instance.
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
            ui_actions=usr.get("ui_actions"),
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
        if self.ui_actions is not None:
            result["usr_mtd"]["ui_actions"] = self.ui_actions
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
        record = HiveRecord.from_raw(record_name, resp)
        # The /mtd endpoint serializes ``data`` as ``{}`` even though only
        # metadata is being returned. Clearing the field here keeps
        # ``set()`` on the round-tripped record routing to /mtd (rather
        # than /data with an empty payload, which trips required-field
        # validators on typed hives like ai_skill or ai_agent).
        record.data = None
        return record

    def merge_current_metadata(self, record: HiveRecord) -> bool:
        """Start a record's metadata from the stored record's metadata.

        ``set()`` replaces the stored metadata wholesale, and a metadata block
        sent without ``enabled`` is stored as disabled. Sending only the
        fields a caller wants to change would therefore silently disable an
        existing record and drop its other metadata. This copies enabled,
        tags, comment, expiry and ui_actions of the stored record onto
        ``record`` (overwriting what it holds for them) so the caller can then
        apply its changes on top. Nothing is changed when the record does not
        exist yet.

        Args:
            record: HiveRecord about to be passed to :meth:`set`.

        Returns:
            bool: True if the record exists and was merged, False if it does not exist.

        Raises:
            ApiError: On any failure reading the metadata other than a missing record.
        """
        try:
            current = self.get_metadata(record.name)
        except ApiError as e:
            if is_record_not_found(e):
                return False
            raise
        record.enabled = current.enabled
        record.tags = current.tags
        record.comment = current.comment
        record.expiry = current.expiry
        record.ui_actions = current.ui_actions
        return True

    def set(self, record: HiveRecord) -> dict[str, Any]:
        """Create or update a record.

        When ``record`` carries no data, only the metadata is written. When it
        carries data and no metadata, the server keeps an existing record's
        metadata (or applies the hive's default to a new one). Any metadata
        present replaces the stored metadata wholesale, and a block without
        ``enabled`` is stored as disabled; see :meth:`merge_current_metadata`.

        Args:
            record: HiveRecord instance with data and optional metadata.

        Returns:
            dict: API response.
        """
        target = "mtd"
        if record.data is not None or record.arl is not None:
            target = "data"

        req: dict[str, Any] = {}
        if record.data is not None:
            req["data"] = json.dumps(record.data)

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
        if record.ui_actions is not None:
            usr_mtd["ui_actions"] = record.ui_actions
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
        if record.ui_actions is not None:
            usr_mtd["ui_actions"] = record.ui_actions
        if usr_mtd:
            req["usr_mtd"] = json.dumps(usr_mtd)

        if record.arl is not None:
            req["arl"] = record.arl

        return self.client.request(
            "POST",
            f"hive/{self._hive_name}/{self._partition_key}/{urlescape(record.name, safe='')}/validate",
            params=req,
        )

    def get_schema(self) -> dict[str, Any]:
        """Get the JSON Schema describing this hive's record type.

        Returns:
            dict: API response with a 'schema' field containing the JSON Schema.
        """
        return self.client.request(
            "GET",
            f"hive/{urlescape(self._hive_name, safe='')}/schema",
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
