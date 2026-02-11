"""Extensions SDK for LimaCharlie v2."""

import base64
import gzip
import json


class Extensions:
    """Extension subscription and request management."""

    def __init__(self, org):
        self._org = org

    def list_subscribed(self):
        return self._org.client.request("GET", f"orgs/{self._org.oid}/subscriptions")

    def subscribe(self, name):
        return self._org.client.request(
            "POST", f"orgs/{self._org.oid}/subscription/extension/{name}", params={}
        )

    def unsubscribe(self, name):
        return self._org.client.request(
            "DELETE", f"orgs/{self._org.oid}/subscription/extension/{name}", params={}
        )

    def rekey(self, name):
        return self._org.client.request(
            "PATCH", f"orgs/{self._org.oid}/subscription/extension/{name}", params={}
        )

    def get_all(self):
        """List all available extensions."""
        return self._org.client.request("GET", "extension/definition", params={})

    def get(self, name):
        """Get extension details."""
        return self._org.client.request("GET", f"extension/definition/{name}")

    def get_schema(self, name):
        """Get extension schema."""
        return self._org.client.request(
            "GET", f"extension/schema/{name}",
            query_params={"oid": self._org.oid},
        )

    def create(self, ext_obj):
        """Create an extension."""
        return self._org.client.request(
            "POST", "extension/definition", params={},
            raw_body=json.dumps(ext_obj).encode(),
            content_type="application/json",
        )

    def update(self, ext_obj):
        """Update an extension."""
        return self._org.client.request(
            "PUT", "extension/definition", params={},
            raw_body=json.dumps(ext_obj).encode(),
            content_type="application/json",
        )

    def delete(self, name):
        """Delete an extension."""
        return self._org.client.request("DELETE", f"extension/definition/{name}")

    def request(self, extension_name, action, data=None, is_impersonated=False):
        """Call an extension.

        Args:
            extension_name: Extension name.
            action: Action to invoke.
            data: Request data dict.
            is_impersonated: If True, impersonate the caller.

        Returns:
            dict: Extension response.
        """
        if data is None:
            data = {}
        params = {
            "oid": self._org.oid,
            "action": action,
            "gzdata": base64.b64encode(gzip.compress(json.dumps(data).encode())),
        }
        if is_impersonated:
            client = self._org.client
            if client._jwt is None:
                client.refresh_jwt()
            params["impersonator_jwt"] = client._jwt
        return self._org.client.request(
            "POST", f"extension/request/{extension_name}", params=params
        )
