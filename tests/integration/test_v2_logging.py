"""Integration tests for LimaCharlie v2 SDK logging rules."""

import sys
import os
import uuid
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from limacharlie.client import Client
from limacharlie.sdk.organization import Organization
from limacharlie.sdk.logging_rules import LoggingRules

TEST_PREFIX = "test-cli-v2-"


def _unique_name(base=""):
    return f"{TEST_PREFIX}{base}{uuid.uuid4().hex[:8]}"


def test_v2_logging_list(oid, key):
    """Verify listing logging rules does not error."""
    client = Client(oid=oid, api_key=key)
    org = Organization(client)
    logging_rules = LoggingRules(org)

    result = logging_rules.list()
    assert result is not None, "Logging rules list returned None"
    assert isinstance(result, dict), (
        f"Expected dict from logging_rules.list(), got {type(result)}"
    )


def test_v2_logging_crud(oid, key):
    """Create a logging rule, verify it appears, get it, delete it, verify gone."""
    client = Client(oid=oid, api_key=key)
    org = Organization(client)
    logging_rules = LoggingRules(org)
    rule_name = _unique_name("log-rule-")

    try:
        # Create a logging rule with a dummy pattern
        logging_rules.create(
            name=rule_name,
            patterns=["*.exe"],
        )

        # Allow eventual consistency
        time.sleep(2)

        # Verify present in list
        rules = logging_rules.list()
        rules_str = str(rules)
        assert rule_name in rules_str, (
            f"Logging rule '{rule_name}' not found in list. Response: {rules}"
        )

        # Get the specific rule
        fetched = logging_rules.get(rule_name)
        assert fetched is not None, f"get('{rule_name}') returned None"
    finally:
        # Always clean up
        try:
            logging_rules.delete(rule_name)
        except Exception:
            pass

    # Verify deletion
    time.sleep(2)
    rules_after = logging_rules.list()
    rules_after_str = str(rules_after)
    assert rule_name not in rules_after_str, (
        f"Logging rule '{rule_name}' still present after deletion"
    )
