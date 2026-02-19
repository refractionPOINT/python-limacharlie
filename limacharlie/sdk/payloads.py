"""Payloads SDK for LimaCharlie v2."""

from __future__ import annotations

import ssl
from typing import Any, TYPE_CHECKING
from urllib.request import Request as URLRequest
from urllib.request import urlopen

if TYPE_CHECKING:
    from .organization import Organization


def _create_ssl_context() -> ssl.SSLContext | None:
    try:
        ctx = ssl.create_default_context()
        if hasattr(ssl, "OP_IGNORE_UNEXPECTED_EOF"):
            ctx.options |= ssl.OP_IGNORE_UNEXPECTED_EOF
        return ctx
    except Exception:
        return None


class Payloads:
    """Payload management."""

    def __init__(self, org: Organization) -> None:
        self._org = org
        self._ssl_context = _create_ssl_context()

    @property
    def client(self) -> Any:
        """The underlying API client."""
        return self._org.client

    def list(self) -> dict[str, Any]:
        """List all payloads."""
        resp = self.client.request("GET", f"payload/{self._org.oid}")
        return resp.get("payloads", resp)

    def upload(self, name: str, file_path: str | None = None,
               payload_content: bytes | None = None) -> bytes | None:
        """Upload a payload using the signed URL pattern.

        Args:
            name: Payload name.
            file_path: Local file path (mutually exclusive with payload_content).
            payload_content: Raw bytes to upload.

        Returns:
            bytes: Response from the upload.
        """
        if file_path is None and payload_content is None:
            raise ValueError("Either file_path or payload_content must be provided.")

        # Step 1: POST to get the signed PUT URL.
        data = self.client.request("POST", f"payload/{self._org.oid}/{name}")
        put_url = data.get("put_url")
        if put_url is None:
            return None

        if payload_content is None:
            with open(file_path, "rb") as f:
                payload_content = f.read()

        # Step 2: PUT the payload content to the signed URL.
        request = URLRequest(
            str(put_url),
            headers={"Content-Type": "application/octet-stream"},
        )
        request.get_method = lambda: "PUT"
        if self._ssl_context is not None:
            u = urlopen(request, data=payload_content, context=self._ssl_context)
        else:
            u = urlopen(request, data=payload_content)
        try:
            return u.read()
        finally:
            u.close()

    def download(self, name: str) -> bytes | None:
        """Download a payload using the signed URL pattern.

        Args:
            name: Payload name.

        Returns:
            bytes: Raw payload content.
        """
        # Step 1: GET to retrieve the signed download URL.
        data = self.client.request("GET", f"payload/{self._org.oid}/{name}")
        get_url = data.get("get_url")
        if get_url is None:
            return None

        # Step 2: GET the actual payload content from the signed URL.
        request = URLRequest(str(get_url))
        request.get_method = lambda: "GET"
        if self._ssl_context is not None:
            u = urlopen(request, context=self._ssl_context)
        else:
            u = urlopen(request)
        try:
            return u.read()
        finally:
            u.close()

    def delete(self, name: str) -> dict[str, Any]:
        """Delete a payload.

        Args:
            name: Payload name.
        """
        return self.client.request("DELETE", f"payload/{self._org.oid}/{name}")
