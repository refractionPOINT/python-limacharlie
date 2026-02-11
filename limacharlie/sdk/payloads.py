"""Payloads SDK for LimaCharlie v2."""

import os


class Payloads:
    """Payload management."""

    def __init__(self, org):
        self._org = org

    @property
    def client(self):
        return self._org.client

    def list(self):
        return self.client.request("GET", f"payload/{self._org.oid}")

    def upload(self, name, file_path):
        """Upload a payload.

        Args:
            name: Payload name.
            file_path: Local file path.

        Returns:
            dict: Upload response.
        """
        with open(file_path, "rb") as f:
            data = f.read()
        return self.client.request(
            "POST",
            f"payload/{self._org.oid}/{name}",
            raw_body=data,
            content_type="application/octet-stream",
        )

    def download(self, name):
        """Download a payload.

        Args:
            name: Payload name.

        Returns:
            dict: Payload data/URL.
        """
        return self.client.request("GET", f"payload/{self._org.oid}/{name}")

    def delete(self, name):
        return self.client.request("DELETE", f"payload/{self._org.oid}/{name}")
