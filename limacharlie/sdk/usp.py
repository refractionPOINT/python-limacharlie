"""USP (Universal Sensor Protocol) SDK for LimaCharlie v2."""

import json


class USP:
    """USP adapter validation."""

    def __init__(self, org):
        self._org = org

    @property
    def client(self):
        return self._org.client

    def validate(self, platform, mapping=None, mappings=None, text_input=None,
                 json_input=None, hostname=None, indexing=None):
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
        body = {"platform": platform}
        if mapping:
            body["mapping"] = mapping
        if mappings:
            body["mappings"] = mappings
        if text_input:
            body["text_input"] = text_input
        if json_input:
            body["json_input"] = json_input
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
