"""Logging rules SDK for LimaCharlie v2."""

import json


class LoggingRules:
    """Log collection rule management (via replicant)."""

    def __init__(self, org):
        self._org = org

    def list(self):
        return self._org.service_request("logging", {"action": "list"})

    def get(self, name):
        return self._org.service_request("logging", {"action": "get", "name": name})

    def create(self, name, patterns, tags=None, platforms=None, retention_days=None, delete_after=False):
        params = {"action": "add", "name": name, "patterns": json.dumps(patterns)}
        if tags:
            params["tags"] = json.dumps(tags)
        if platforms:
            params["platforms"] = json.dumps(platforms)
        if retention_days:
            params["retention_days"] = str(retention_days)
        if delete_after:
            params["delete_after"] = "true"
        return self._org.service_request("logging", params)

    def delete(self, name):
        return self._org.service_request("logging", {"action": "remove", "name": name})
