"""Integrity monitoring SDK for LimaCharlie v2."""


class Integrity:
    """Integrity monitoring rule management (via replicant)."""

    def __init__(self, org):
        self._org = org

    def list(self):
        return self._org.service_request("integrity", {"action": "list_rules"})

    def get(self, name):
        rules = self.list()
        if isinstance(rules, dict):
            for rule_name, rule_data in rules.items():
                if rule_name == name:
                    return rule_data
        return None

    def create(self, name, patterns, tags=None, platforms=None):
        params = {"action": "add_rule", "name": name, "patterns": patterns}
        if tags:
            params["tags"] = tags
        if platforms:
            params["platforms"] = platforms
        return self._org.service_request("integrity", params)

    def delete(self, name):
        return self._org.service_request("integrity", {"action": "remove_rule", "name": name})
