"""Integrity monitoring SDK for LimaCharlie v2."""

import json


class Integrity:
    """Integrity monitoring rule management (via replicant)."""

    def __init__(self, org):
        self._org = org

    def list(self):
        return self._org.service_request("integrity", {"action": "list"})

    def get(self, name):
        return self._org.service_request("integrity", {"action": "get", "name": name})

    def create(self, name, patterns, tags=None, platforms=None):
        params = {"action": "add", "name": name, "patterns": json.dumps(patterns)}
        if tags:
            params["tags"] = json.dumps(tags)
        if platforms:
            params["platforms"] = json.dumps(platforms)
        return self._org.service_request("integrity", params)

    def delete(self, name):
        return self._org.service_request("integrity", {"action": "remove", "name": name})
