"""D&R Rules SDK for LimaCharlie v2.

Thin wrapper - actual API calls go through Organization.
This module provides a dedicated class interface.
"""

import json
import time


class DRRules:
    """D&R rule management for a LimaCharlie organization."""

    def __init__(self, org):
        self._org = org

    def list(self, namespace=None):
        return self._org.get_rules(namespace=namespace)

    def get(self, name, namespace=None):
        rules = self.list(namespace=namespace)
        # Rules are typically keyed by name
        if isinstance(rules, dict):
            return rules.get(name)
        return None

    def create(self, name, detection, response, is_replace=False, namespace=None, is_enabled=True, ttl=None):
        return self._org.add_rule(name, detection, response, is_replace=is_replace,
                                  namespace=namespace, is_enabled=is_enabled, ttl=ttl)

    def update(self, name, detection, response, namespace=None):
        return self.create(name, detection, response, is_replace=True, namespace=namespace)

    def delete(self, name, namespace=None):
        return self._org.delete_rule(name, namespace=namespace)
