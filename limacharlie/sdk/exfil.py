"""Exfil prevention SDK for LimaCharlie v2."""

import json


class Exfil:
    """Exfil prevention rule management (via replicant)."""

    def __init__(self, org):
        self._org = org

    def list(self):
        return self._org.service_request("exfil", {"action": "list"})

    def create_watch(self, name, event, value, operator, path, tags=None, platforms=None):
        params = {
            "action": "add_watch",
            "name": name,
            "event": event,
            "value": value,
            "operator": operator,
            "path": path,
        }
        if tags:
            params["tags"] = json.dumps(tags)
        if platforms:
            params["platforms"] = json.dumps(platforms)
        return self._org.service_request("exfil", params)

    def create_event(self, name, events, tags=None, platforms=None):
        params = {
            "action": "add_event",
            "name": name,
            "events": json.dumps(events),
        }
        if tags:
            params["tags"] = json.dumps(tags)
        if platforms:
            params["platforms"] = json.dumps(platforms)
        return self._org.service_request("exfil", params)

    def delete(self, name):
        return self._org.service_request("exfil", {"action": "remove", "name": name})
