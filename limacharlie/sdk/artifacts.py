"""Artifacts SDK for LimaCharlie v2.

Artifact/log upload and management. Uses v1 Logs.py API patterns.
"""

import json
import os


class Artifacts:
    """Artifact upload, download, and rule management."""

    def __init__(self, org):
        self._org = org

    @property
    def client(self):
        return self._org.client

    def upload(self, file_path, source=None, hint=None, retention_days=None,
               original_path=None, sid=None):
        """Upload an artifact/log file.

        Args:
            file_path: Local file path.
            source: Source identifier.
            hint: Parse hint.
            retention_days: Retention period.
            original_path: Original file path on the source system.
            sid: Associated sensor ID.

        Returns:
            dict: Upload response.
        """
        # Get the upload URL first
        params = {}
        if source:
            params["source"] = source
        if hint:
            params["hint"] = hint
        if retention_days:
            params["retention_days"] = str(retention_days)
        if original_path:
            params["original_path"] = original_path
        if sid:
            params["sid"] = str(sid)

        file_name = os.path.basename(file_path)
        params["file_name"] = file_name

        with open(file_path, "rb") as f:
            file_data = f.read()

        # Upload artifact via the artifact upload endpoint
        return self.client.request(
            "POST",
            f"insight/{self._org.oid}/artifacts/upload",
            params=params,
            raw_body=file_data,
            content_type="application/octet-stream",
        )

    def list(self, sid=None):
        """List artifacts.

        Args:
            sid: Optional sensor ID filter.

        Returns:
            dict: Artifact list.
        """
        qp = {}
        if sid:
            qp["sid"] = str(sid)
        return self.client.request("GET", f"insight/{self._org.oid}/artifacts",
                                   query_params=qp or None)

    def get(self, artifact_id):
        """Get artifact details.

        Args:
            artifact_id: Artifact identifier.

        Returns:
            dict: Artifact details.
        """
        return self.client.request("GET", f"insight/{self._org.oid}/artifacts/{artifact_id}")
