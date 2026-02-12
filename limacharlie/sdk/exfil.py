"""Exfil prevention SDK for LimaCharlie v2."""


class Exfil:
    """Exfil prevention rule management (via replicant)."""

    def __init__(self, org):
        self._org = org

    def list(self):
        return self._org.service_request("exfil", {"action": "list_rules"})

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
            params["tags"] = tags
        if platforms:
            params["platforms"] = platforms
        return self._org.service_request("exfil", params)

    def create_event(self, name, events, tags=None, platforms=None):
        params = {
            "action": "add_event_rule",
            "name": name,
            "events": events,
        }
        if tags:
            params["tags"] = tags
        if platforms:
            params["platforms"] = platforms
        return self._org.service_request("exfil", params)

    def delete_event(self, name):
        return self._org.service_request("exfil", {"action": "remove_event_rule", "name": name})

    def delete_watch(self, name):
        return self._org.service_request("exfil", {"action": "remove_watch", "name": name})
