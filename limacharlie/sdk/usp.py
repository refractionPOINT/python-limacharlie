"""USP (Universal Sensor Protocol) SDK for LimaCharlie v2."""

from __future__ import annotations

import json
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .organization import Organization


class USP:
    """USP adapter validation."""

    def __init__(self, org: Organization) -> None:
        self._org = org

    @property
    def client(self) -> Any:
        return self._org.client

    def validate(self, platform: str, mapping: dict[str, Any] | None = None,
                 mappings: list[dict[str, Any]] | None = None, text_input: str | None = None,
                 json_input: dict[str, Any] | None = None, hostname: str | None = None,
                 indexing: dict[str, Any] | None = None) -> dict[str, Any]:
        """Validate USP adapter configuration.

        Args:
            platform: Platform identifier.
            mapping: Single mapping dict.
            mappings: Multiple mappings list.
            text_input: Text input for testing.
            json_input: JSON input for testing.
            hostname: Optional hostname.
            indexing: Indexing configuration.

        Returns:
            dict: Validation results.
        """
        body: dict[str, Any] = {"platform": platform}
        if mapping:
            body["mapping"] = mapping
        if mappings:
            body["mappings"] = mappings
        if text_input:
            body["text_input"] = text_input
        if json_input:
            body["json_input"] = json_input if isinstance(json_input, list) else [json_input]
        if hostname:
            body["hostname"] = hostname
        if indexing:
            body["indexing"] = indexing

        return self.client.request(
            "POST",
            f"usp/validate/{self._org.oid}",
            raw_body=json.dumps(body).encode(),
            content_type="application/json",
        )
