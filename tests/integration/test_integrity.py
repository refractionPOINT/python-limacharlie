"""Integration tests for LimaCharlie v2 SDK Integrity monitoring rules."""

import sys
import os
import uuid
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from limacharlie.client import Client
from limacharlie.sdk.organization import Organization
from limacharlie.sdk.integrity import Integrity

TEST_PREFIX = "test-cli-v2-"


def _unique_name(base=""):
    return f"{TEST_PREFIX}{base}{uuid.uuid4().hex[:8]}"


def test_v2_integrity_list(oid, key):
    """Test listing integrity rules returns a valid response."""
    client = Client(oid=oid, api_key=key)
    org = Organization(client)
    integrity = Integrity(org)

    result = integrity.list()
    assert isinstance(result, dict), f"Expected dict from integrity.list(), got {type(result)}"


def test_v2_integrity_crud(oid, key):
    """Create an integrity rule, verify it exists, delete it, verify it is gone."""
    client = Client(oid=oid, api_key=key)
    org = Organization(client)
    integrity = Integrity(org)
    rule_name = _unique_name("integ-")

    patterns = ["/tmp/test-cli-v2-*"]

    try:
        # Create
        create_result = integrity.create(
            rule_name,
            patterns,
            tags=["test-cli-v2"],
            platforms=["linux"],
        )
        assert isinstance(create_result, dict), (
            f"Expected dict from integrity.create(), got {type(create_result)}"
        )

        # Small delay for eventual consistency
        time.sleep(2)

        # Verify present via list
        rules = integrity.list()
        assert isinstance(rules, dict), f"Expected dict from integrity.list(), got {type(rules)}"
        # The list response may nest rules under a key or be a flat dict.
        # Check if our rule name is somewhere in the response.
        found = _find_rule_in_response(rules, rule_name)
        assert found, f"Integrity rule '{rule_name}' not found in listing: {list(rules.keys())[:10]}"

        # Verify via get
        detail = integrity.get(rule_name)
        assert isinstance(detail, dict), f"Expected dict from integrity.get(), got {type(detail)}"
    finally:
        # Always clean up
        try:
            integrity.delete(rule_name)
        except Exception:
            pass

    # Verify gone after deletion
    time.sleep(2)
    rules_after = integrity.list()
    assert not _find_rule_in_response(rules_after, rule_name), (
        f"Integrity rule '{rule_name}' still present after deletion"
    )


def test_v2_integrity_create_with_multiple_patterns(oid, key):
    """Create an integrity rule with multiple patterns, then delete it."""
    client = Client(oid=oid, api_key=key)
    org = Organization(client)
    integrity = Integrity(org)
    rule_name = _unique_name("integ-multi-")

    patterns = [
        "/etc/test-cli-v2-*.conf",
        "/var/log/test-cli-v2-*.log",
    ]

    try:
        create_result = integrity.create(rule_name, patterns)
        assert isinstance(create_result, dict), (
            f"Expected dict from integrity.create(), got {type(create_result)}"
        )

        time.sleep(2)

        detail = integrity.get(rule_name)
        assert isinstance(detail, dict), f"Expected dict from integrity.get(), got {type(detail)}"
    finally:
        try:
            integrity.delete(rule_name)
        except Exception:
            pass


def _find_rule_in_response(response, rule_name):
    """Search for a rule name in the integrity list response."""
    # Direct key match
    if rule_name in response:
        return True
    # Check nested structures
    for key, value in response.items():
        if isinstance(value, dict):
            if value.get("name") == rule_name:
                return True
            if rule_name in value:
                return True
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict) and item.get("name") == rule_name:
                    return True
                if item == rule_name:
                    return True
    return False
