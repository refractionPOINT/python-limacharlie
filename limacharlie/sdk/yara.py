"""YARA SDK for LimaCharlie v2."""

import json


class Yara:
    """YARA scanning and rule management (via replicant)."""

    def __init__(self, org):
        self._org = org

    def scan(self, sid, rule, timeout=None):
        """Run ad-hoc YARA scan on a sensor.

        Args:
            sid: Sensor ID.
            rule: YARA rule content.
            timeout: Scan timeout.

        Returns:
            dict: Scan results.
        """
        params = {"action": "scan", "sid": str(sid), "rule": rule}
        if timeout:
            params["timeout"] = str(timeout)
        return self._org.service_request("yara", params)

    def list_rules(self):
        return self._org.service_request("yara", {"action": "list_rules"})

    def add_rule(self, name, sources, tags=None, platforms=None):
        params = {"action": "add_rule", "name": name, "sources": json.dumps(sources)}
        if tags:
            params["tags"] = json.dumps(tags)
        if platforms:
            params["platforms"] = json.dumps(platforms)
        return self._org.service_request("yara", params)

    def delete_rule(self, name):
        return self._org.service_request("yara", {"action": "remove_rule", "name": name})

    def list_sources(self):
        return self._org.service_request("yara", {"action": "list_sources"})

    def get_source(self, name):
        return self._org.service_request("yara", {"action": "get_source", "name": name})

    def add_source(self, name, source):
        return self._org.service_request("yara", {"action": "add_source", "name": name, "source": source})

    def delete_source(self, name):
        return self._org.service_request("yara", {"action": "remove_source", "name": name})
