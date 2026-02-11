"""Integration tests for LimaCharlie v2 SDK D&R rules and false positives."""

import sys
import os
import uuid

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from limacharlie.client import Client
from limacharlie.sdk.organization import Organization

TEST_PREFIX = "test-cli-v2-"


def _unique_name(base=""):
    return f"{TEST_PREFIX}{base}{uuid.uuid4().hex[:8]}"


def test_v2_rules_crud(oid, key):
    """Create a D&R rule, verify it appears in the list, delete it, verify it is gone."""
    client = Client(oid=oid, api_key=key)
    org = Organization(client)
    rule_name = _unique_name("rule-")

    detection = {"op": "is", "event": "NEW_PROCESS", "path": "event/FILE_PATH", "value": "test-never-match.exe"}
    response = [{"action": "report", "name": rule_name}]

    try:
        # Create
        org.add_rule(rule_name, detection, response, is_replace=True)

        # Verify present
        rules = org.get_rules()
        assert rule_name in rules, f"Rule '{rule_name}' not found in rules list"
    finally:
        # Cleanup - always attempt deletion
        try:
            org.delete_rule(rule_name)
        except Exception:
            pass

    # Verify gone after deletion
    rules_after = org.get_rules()
    assert rule_name not in rules_after, f"Rule '{rule_name}' still present after deletion"


def test_v2_fps_crud(oid, key):
    """Create a false-positive rule, verify it appears, delete it, verify it is gone."""
    client = Client(oid=oid, api_key=key)
    org = Organization(client)
    fp_name = _unique_name("fp-")

    fp_rule = {"op": "is", "path": "detect/event/FILE_PATH", "value": "test-never-match.exe"}

    try:
        # Create
        org.add_fp(fp_name, fp_rule, is_replace=True)

        # Verify present
        fps = org.get_fps()
        assert fp_name in fps, f"FP rule '{fp_name}' not found in FP list"
    finally:
        # Cleanup
        try:
            org.delete_fp(fp_name)
        except Exception:
            pass

    # Verify gone
    fps_after = org.get_fps()
    assert fp_name not in fps_after, f"FP rule '{fp_name}' still present after deletion"


def test_v2_rules_namespace(oid, key):
    """Create a D&R rule in the 'managed' namespace, verify, and delete."""
    client = Client(oid=oid, api_key=key)
    org = Organization(client)
    rule_name = _unique_name("ns-rule-")

    detection = {"op": "is", "event": "NEW_PROCESS", "path": "event/FILE_PATH", "value": "test-never-match.exe"}
    response = [{"action": "report", "name": rule_name}]

    try:
        # Create in managed namespace
        org.add_rule(rule_name, detection, response, is_replace=True, namespace="managed")

        # Verify present when querying managed namespace
        rules = org.get_rules(namespace="managed")
        assert rule_name in rules, (
            f"Rule '{rule_name}' not found in managed namespace rules"
        )
    finally:
        # Cleanup
        try:
            org.delete_rule(rule_name, namespace="managed")
        except Exception:
            pass

    # Verify gone
    rules_after = org.get_rules(namespace="managed")
    assert rule_name not in rules_after, (
        f"Rule '{rule_name}' still present in managed namespace after deletion"
    )
