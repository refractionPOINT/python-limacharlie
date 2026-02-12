"""Logging rules SDK for LimaCharlie v2."""


class LoggingRules:
    """Log collection rule management (via replicant)."""

    def __init__(self, org):
        self._org = org

    def list(self):
        return self._org.service_request("logging", {"action": "list_rules"})

    def get(self, name):
        rules = self.list()
        if isinstance(rules, dict):
            for rule_name, rule_data in rules.items():
                if rule_name == name:
                    return rule_data
        return None

    def create(self, name, patterns, tags=None, platforms=None, retention_days=None, delete_after=False):
        params = {"action": "add_rule", "name": name, "patterns": patterns}
        if tags:
            params["tags"] = tags
        if platforms:
            params["platforms"] = platforms
        if retention_days:
            params["days_retention"] = str(retention_days)
        if delete_after:
            params["is_delete_after"] = "true"
        return self._org.service_request("logging", params)

    def delete(self, name):
        return self._org.service_request("logging", {"action": "remove_rule", "name": name})
