"""Hive SDK class for LimaCharlie v2.

Hive is a key-value store for LimaCharlie configuration data.
Supports records with data, metadata, etag-based transactions.
"""

import json
from urllib.parse import quote as urlescape


class HiveRecord:
    """Represents a record in a Hive."""

    def __init__(self, name, data=None, raw=None):
        """Initialize a HiveRecord.

        Args:
            name: Record name/key.
            data: Record data dict.
            raw: Raw API response dict (has 'data', 'usr_mtd', 'sys_mtd').
        """
        self.name = name
        self.arl = None

        if raw is not None:
            self.data = raw.get("data")
            if self.data is not None and not isinstance(self.data, dict):
                self.data = json.loads(self.data)
            usr = raw.get("usr_mtd", {})
            self.expiry = usr.get("expiry")
            self.enabled = usr.get("enabled")
            self.tags = usr.get("tags")
            self.comment = usr.get("comment")
            sys_mtd = raw.get("sys_mtd", {})
            self.etag = sys_mtd.get("etag")
            self.created_at = sys_mtd.get("created_at")
            self.created_by = sys_mtd.get("created_by")
            self.guid = sys_mtd.get("guid")
            self.last_author = sys_mtd.get("last_author")
            self.last_modified = sys_mtd.get("last_mod")
            self.last_error = sys_mtd.get("last_error")
            self.last_error_ts = sys_mtd.get("last_error_ts")
        else:
            self.data = data
            self.expiry = None
            self.enabled = None
            self.tags = None
            self.comment = None
            self.etag = None
            self.created_at = None
            self.created_by = None
            self.guid = None
            self.last_author = None
            self.last_modified = None
            self.last_error = None
            self.last_error_ts = None

    def to_dict(self):
        """Serialize to a dict matching the API format."""
        result = {"data": self.data, "usr_mtd": {}, "sys_mtd": {}}
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

    def __init__(self, org, hive_name, partition_key=None):
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
    def client(self):
        return self._org.client

    def list(self):
        """List all records in this hive.

        Returns:
            dict: Mapping of record name -> HiveRecord.
        """
        resp = self.client.request("GET", f"hive/{self._hive_name}/{self._partition_key}")
        return {
            name: HiveRecord(name, raw=record)
            for name, record in resp.items()
        }

    def get(self, record_name):
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
        return HiveRecord(record_name, raw=resp)

    def get_metadata(self, record_name):
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
        return HiveRecord(record_name, raw=resp)

    def set(self, record):
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

    def delete(self, record_name):
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

    def validate(self, record):
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

    def rename(self, record_name, new_name):
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
            query_params={"new_name": urlescape(new_name, safe="")},
        )

    def update_tx(self, record_name, callback, max_retries=5):
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
                if e.status_code == 409:
                    continue  # etag mismatch, retry
                raise
        raise ApiError("Transaction failed after max retries (etag conflict).", status_code=409)
