"""Hive SDK class for LimaCharlie v2.

Hive is a key-value store for LimaCharlie configuration data.
Supports records with data, metadata, etag-based transactions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Iterator, TYPE_CHECKING
from urllib.parse import quote as urlescape

from ..errors import HIVE_LISTING_TOO_LARGE, ApiError, PermissionDeniedError

if TYPE_CHECKING:
    from ..client import Client
    from .organization import Organization


# Records per page asked of the server when the caller does not choose. The
# server caps the limit it honors, so the max is only a request.
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 500


def _lc_error_code(exc: Exception) -> str | None:
    """Return the ``lc_error_code`` of an HTTP 400 API answer, if any.

    The gateway reports hive failures as HTTP 400 whose body error is
    ``"lc_error_code:<CODE> - <detail>"``, so the code in the body is the
    only reliable signal of what went wrong.
    """
    if not isinstance(exc, ApiError) or not isinstance(exc.response_body, dict):
        return None
    error = exc.response_body.get("error")
    prefix = "lc_error_code:"
    if not isinstance(error, str) or not error.startswith(prefix):
        return None
    return error[len(prefix):].split(" ", 1)[0]


def is_record_not_found(exc: Exception) -> bool:
    """Check whether an exception is the API's RECORD_NOT_FOUND answer.

    A missing record comes back as HTTP 400 with ``RECORD_NOT_FOUND``, not
    as a 404. Any other failure (permissions, network, unknown hive, ...) is
    not "the record is missing".

    Args:
        exc: The exception raised by a hive read.

    Returns:
        bool: True only for a missing-record answer.
    """
    return _lc_error_code(exc) == "RECORD_NOT_FOUND"


def is_permission_denied(exc: Exception) -> bool:
    """Check whether an exception means the caller lacks a permission.

    The hive denies an operation with HTTP 400 and ``UNAUTHORIZED``; an
    HTTP 403 raises :class:`PermissionDeniedError`.

    Args:
        exc: The exception raised by a hive call.

    Returns:
        bool: True for either form of permission denial.
    """
    return isinstance(exc, PermissionDeniedError) or _lc_error_code(exc) == "UNAUTHORIZED"


def is_listing_too_large(exc: Exception) -> bool:
    """Check whether an exception is the API refusing a whole-hive listing.

    A hive too big to list in one response is refused with HTTP 413 and
    ``HIVE_LISTING_TOO_LARGE``. The listing has to be read page by page
    instead (:meth:`Hive.iter_pages`); :meth:`Hive.list` does this by itself.

    Args:
        exc: The exception raised by a hive listing.

    Returns:
        bool: True only for a too-large-listing answer.
    """
    if not isinstance(exc, ApiError):
        return False
    code = exc.error_code
    if code is not None:
        # Another 413 (a story answer with too much left out) is not this one.
        return code == HIVE_LISTING_TOO_LARGE
    return exc.status_code == 413 or HIVE_LISTING_TOO_LARGE in str(exc)


def _looks_like_record(value: Any) -> bool:
    return isinstance(value, dict) and ("sys_mtd" in value or "usr_mtd" in value)


def _split_listing(resp: Any) -> tuple[dict[str, Any], str, bool]:
    """Split a hive listing answer into its records and next cursor.

    The paged answer is ``{"records": {...}, "next_cursor": "..."}``. A server
    that predates paging ignores the paging parameters and answers with the
    plain ``{name: record}`` map, which is then one final page.

    A ``next_cursor`` that is a string (or null) marks the envelope: every
    value of a plain map is a record object, so a record named
    ``next_cursor`` cannot be mistaken for it, and a page with no visible
    records but more to come is still recognized. Without ``next_cursor``,
    ``records`` as the only key is still read as an envelope unless its value
    is a record (a plain map holding one record named ``records``): a missing
    cursor means the last page, and reading that as a plain map would silently
    drop every record.

    Args:
        resp: Parsed JSON answer of the listing endpoint.

    Returns:
        tuple: (records as raw dicts, next cursor ("" when there is no more), True for a paged envelope and False for a plain map).

    Raises:
        ApiError: If the answer is neither shape.
    """
    if not resp:
        return {}, "", False
    if not isinstance(resp, dict):
        raise ApiError(f"Unexpected hive listing response of type {type(resp).__name__}.")
    if "next_cursor" in resp and (resp["next_cursor"] is None or isinstance(resp["next_cursor"], str)):
        records = resp.get("records")
        if records is not None and not isinstance(records, dict):
            raise ApiError("Unexpected hive listing response: 'records' is not an object.")
        return records or {}, resp["next_cursor"] or "", True
    if list(resp) == ["records"] and (resp["records"] is None or (
            isinstance(resp["records"], dict) and not _looks_like_record(resp["records"]))):
        return resp["records"] or {}, "", True
    return resp, "", False


def _has_tag_prefix(raw: dict[str, Any], prefix: str) -> bool:
    tags = (raw.get("usr_mtd") or {}).get("tags") or []
    return any(isinstance(t, str) and t.startswith(prefix) for t in tags)


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

    def _list_path(self) -> str:
        return f"hive/{self._hive_name}/{self._partition_key}"

    def list(self) -> dict[str, HiveRecord]:
        """List all records in this hive, with their data.

        A hive too big for the server to list in one response is read page by
        page transparently (see :meth:`iter_pages`), so the result is always
        the whole hive. Use :meth:`list_mtd` when the data is not needed, and
        :meth:`iter_pages` to bound memory on a big hive. A gateway timeout
        is raised, not retried: the whole-hive request is heavy for the
        backend.

        Returns:
            dict: Mapping of record name -> HiveRecord.
        """
        try:
            resp = self.client.request("GET", self._list_path(), retry_gateway_timeout=False)
        except ApiError as e:
            if not is_listing_too_large(e):
                raise
            return self._list_all_pages(mtd_only=False)
        return {
            name: HiveRecord.from_raw(name, record)
            for name, record in resp.items()
        }

    def list_mtd(self) -> dict[str, HiveRecord]:
        """List all records in this hive without their data.

        The server does not load the record data at all. Records have
        ``data`` set to ``None``.

        Returns:
            dict: Mapping of record name -> HiveRecord (metadata only).
        """
        try:
            resp = self.client.request(
                "GET", self._list_path(), query_params={"mtd_only": "true"}, retry_gateway_timeout=False,
            )
        except ApiError as e:
            if not is_listing_too_large(e):
                raise
            return self._list_all_pages(mtd_only=True)
        return {name: self._mtd_record(name, record) for name, record in resp.items()}

    @staticmethod
    def _mtd_record(name: str, raw: dict[str, Any]) -> HiveRecord:
        # A server that predates ``mtd_only`` answers with the data anyway;
        # drop it so the result does not depend on the server version.
        record = HiveRecord.from_raw(name, raw)
        record.data = None
        return record

    def list_page(
        self,
        limit: int | None = None,
        cursor: str | None = None,
        mtd_only: bool = False,
        tag_prefix: str | None = None,
        max_bytes: int | None = None,
    ) -> tuple[dict[str, HiveRecord], str]:
        """Get one page of this hive's records, in record name order.

        A server that predates paging answers with the whole hive, which is
        returned as a single final page (``mtd_only`` and ``tag_prefix`` are
        then applied here).

        Args:
            limit: Maximum number of records in the page (the server caps it and also bounds the page size in bytes).
            cursor: ``next_cursor`` of the previous page; omit for the first page.
            mtd_only: Return the records without their data.
            tag_prefix: Only return records with a tag starting with this prefix.
            max_bytes: Lower the server-side size bound of the page.

        Returns:
            tuple: (mapping of record name -> HiveRecord, next cursor). An empty cursor means this was the last page.

        Raises:
            ApiError: On any failure, including an invalid cursor (HTTP 400).
        """
        # "limit" is what selects the paged answer, so it is always sent.
        query: dict[str, Any] = {"limit": limit if limit and limit > 0 else DEFAULT_PAGE_SIZE}
        if cursor:
            query["cursor"] = cursor
        if mtd_only:
            query["mtd_only"] = "true"
        if tag_prefix:
            query["tag_prefix"] = tag_prefix
        if max_bytes:
            query["max_bytes"] = max_bytes
        resp = self.client.request("GET", self._list_path(), query_params=query)
        raw_records, next_cursor, is_paged = _split_listing(resp)
        if tag_prefix and not is_paged:
            # A server that predates paging ignores tag_prefix too.
            raw_records = {n: r for n, r in raw_records.items() if _has_tag_prefix(r, tag_prefix)}
        if mtd_only:
            records = {name: self._mtd_record(name, raw) for name, raw in raw_records.items()}
        else:
            records = {name: HiveRecord.from_raw(name, raw) for name, raw in raw_records.items()}
        return records, next_cursor

    def iter_pages(
        self,
        limit: int | None = None,
        mtd_only: bool = False,
        tag_prefix: str | None = None,
        max_bytes: int | None = None,
        cursor: str | None = None,
    ) -> Iterator[dict[str, HiveRecord]]:
        """Walk this hive page by page, so only one page is in memory at a time.

        Args:
            limit: Maximum number of records per page.
            mtd_only: Return the records without their data.
            tag_prefix: Only return records with a tag starting with this prefix.
            max_bytes: Lower the server-side size bound of each page.
            cursor: Resume from this cursor instead of the start of the hive.

        Yields:
            dict: Mapping of record name -> HiveRecord for each page.

        Raises:
            ApiError: On any failure, or if the server returns a cursor that does not advance.
        """
        while True:
            page, next_cursor = self.list_page(
                limit=limit, cursor=cursor, mtd_only=mtd_only,
                tag_prefix=tag_prefix, max_bytes=max_bytes,
            )
            yield page
            if not next_cursor:
                return
            if next_cursor == cursor:
                raise ApiError("Hive listing did not advance: server returned the same cursor.")
            cursor = next_cursor

    def _list_all_pages(self, mtd_only: bool) -> dict[str, HiveRecord]:
        records: dict[str, HiveRecord] = {}
        for page in self.iter_pages(limit=MAX_PAGE_SIZE, mtd_only=mtd_only):
            records.update(page)
        return records

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
