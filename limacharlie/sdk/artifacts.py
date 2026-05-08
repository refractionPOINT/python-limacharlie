"""Artifacts SDK for LimaCharlie v2.

Artifact/log upload and management. Uses v1 Logs.py API patterns.
"""

from __future__ import annotations

import base64
import json
import os
import uuid
from typing import Any, TYPE_CHECKING
from urllib.error import HTTPError
from urllib.request import Request as URLRequest
from urllib.request import urlopen

if TYPE_CHECKING:
    from .organization import Organization


MAX_UPLOAD_PART_SIZE = 1024 * 1024 * 15


class Artifacts:
    """Artifact upload, download, and rule management."""

    def __init__(self, org: Organization, access_token: str | None = None) -> None:
        """Initialize Artifacts.

        Args:
            org: Organization SDK object.
            access_token: Optional ingestion key for uploads. Falls back to
                         LC_LOGS_TOKEN env var if not provided.
        """
        self._org = org
        self._access_token = access_token
        if self._access_token is None:
            self._access_token = os.environ.get("LC_LOGS_TOKEN")
        if self._access_token is not None:
            self._access_token = str(uuid.UUID(str(self._access_token)))
        self._upload_url: str | None = None

    @property
    def client(self) -> Any:
        """The underlying API client."""
        return self._org.client

    def upload(self, file_path: str, source: str | None = None, hint: str | None = None,
               retention_days: int = 30, original_path: str | None = None,
               payload_id: str | None = None) -> dict[str, Any]:
        """Upload an artifact/log file.

        Uses the ingestion endpoint with Basic auth (oid:access_token),
        matching the v1 Logs.upload pattern.

        Args:
            file_path: Local file path.
            source: Source identifier.
            hint: Parse hint.
            retention_days: Retention period in days.
            original_path: Original file path on the source system.
            payload_id: Optional unique payload ID for idempotent uploads.

        Returns:
            dict: Upload response.
        """
        if self._access_token is None:
            from ..errors import LimaCharlieError
            raise LimaCharlieError("Access token not specified. Set LC_LOGS_TOKEN or pass access_token.")

        if self._upload_url is None:
            urls = self._org.get_urls()
            self._upload_url = urls.get("logs", "")

        headers: dict[str, str] = {
            "Authorization": "Basic %s" % base64.b64encode(
                ("%s:%s" % (self._org.oid, self._access_token)).encode()
            ).decode(),
        }

        if source is not None:
            headers["lc-source"] = source
        if hint is not None:
            headers["lc-hint"] = hint
        if payload_id is not None:
            headers["lc-payload-id"] = payload_id
        if original_path is not None:
            headers["lc-path"] = base64.b64encode(
                os.path.abspath(original_path).encode()
            ).decode()
        if retention_days is not None:
            headers["lc-retention-days"] = str(retention_days)

        with open(file_path, "rb") as f:
            f.seek(0, 2)
            file_size = f.tell()
            f.seek(0)

            if MAX_UPLOAD_PART_SIZE > file_size:
                request = URLRequest(
                    "https://%s/ingest" % self._upload_url,
                    data=f.read(),
                    headers=headers,
                )
                try:
                    u = urlopen(request)
                except HTTPError as e:
                    raise Exception("%s: %s" % (str(e), e.read().decode()))
                try:
                    response = json.loads(u.read().decode())
                except Exception:
                    response = {}
            else:
                part_id = 0
                if payload_id is None:
                    headers["lc-payload-id"] = str(uuid.uuid4())

                response: dict[str, Any] = {}
                while True:
                    chunk = f.read(MAX_UPLOAD_PART_SIZE)
                    if not chunk:
                        break

                    if len(chunk) != MAX_UPLOAD_PART_SIZE:
                        headers["lc-part"] = "done"
                    else:
                        headers["lc-part"] = str(part_id)

                    request = URLRequest(
                        "https://%s/ingest" % self._upload_url,
                        data=chunk,
                        headers=headers,
                    )
                    try:
                        u = urlopen(request)
                    except HTTPError as e:
                        raise Exception("%s: %s" % (str(e), e.read().decode()))
                    try:
                        response = json.loads(u.read().decode())
                    except Exception:
                        response = {}
                    part_id += 1

        return response

    def list(self, sid: str | None = None, start: int | None = None, end: int | None = None,
             cursor: str | None = None) -> dict[str, Any]:
        """List artifacts.

        Args:
            sid: Optional sensor ID filter.
            start: Start time (unix seconds). Defaults to 24 hours ago.
            end: End time (unix seconds). Defaults to now.
            cursor: Pagination cursor.

        Returns:
            dict: Artifact list.
        """
        import time as _time
        qp: dict[str, str] = {}
        if sid:
            qp["sid"] = str(sid)
        if cursor:
            qp["cursor"] = cursor
        else:
            if start is None:
                start = int(_time.time()) - 86400
            if end is None:
                end = int(_time.time())
            qp["start"] = str(int(start))
            qp["end"] = str(int(end))
        return self.client.request("GET", f"insight/{self._org.oid}/artifacts",
                                   query_params=qp)

    def get_url(self, artifact_id: str) -> dict[str, Any]:
        """Get download URL or inline data for an artifact.

        Requests the original artifact data.  For small artifacts the
        payload may be returned inline; for larger ones a signed
        download URL is returned in the 'export' field.

        Args:
            artifact_id: Artifact identifier.

        Returns:
            dict: Response with 'payload' (inline) or 'export' (URL).
        """
        return self.client.request(
            "POST", f"insight/{self._org.oid}/artifacts/originals/{artifact_id}",
        )

    def get_rules(self) -> dict[str, Any]:
        """List artifact collection rules.

        Returns:
            dict: Artifact rules.
        """
        return self.client.request("GET", f"insight/{self._org.oid}/artifacts/rules")

    def set_rule(self, rule_name: str, platforms: list[str], patterns: list[str],
                 is_delete_after: bool = False, retention_days: int = 30,
                 tags: list[str] | None = None) -> dict[str, Any]:
        """Create or update an artifact collection rule.

        Args:
            rule_name: Rule name.
            platforms: List of platform strings.
            patterns: List of file path patterns to collect.
            is_delete_after: Delete file after collection.
            retention_days: Retention period.
            tags: Optional tag filter.

        Returns:
            dict: API response.
        """
        params: dict[str, Any] = {
            "name": rule_name,
            "platforms": platforms,
            "patterns": patterns,
            "is_delete_after": is_delete_after,
            "days_retention": retention_days,
        }
        if tags:
            params["tags"] = tags
        return self.client.request(
            "POST", f"insight/{self._org.oid}/artifacts/rules",
            raw_body=json.dumps(params).encode(),
            content_type="application/json",
        )

    def delete_rule(self, rule_name: str) -> dict[str, Any]:
        """Delete an artifact collection rule.

        Args:
            rule_name: Rule name.

        Returns:
            dict: API response.
        """
        return self.client.request(
            "DELETE", f"insight/{self._org.oid}/artifacts/rules",
            params={"name": rule_name},
        )
