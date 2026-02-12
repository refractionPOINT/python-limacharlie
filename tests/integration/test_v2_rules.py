"""Integration tests for LimaCharlie v2 SDK D&R rules and false positives (Hive-backed)."""

import sys
import os
import uuid

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from limacharlie.client import Client
from limacharlie.sdk.organization import Organization
from limacharlie.sdk.hive import Hive, HiveRecord

TEST_PREFIX = "test-cli-v2-"


def _unique_name(base=""):
    return f"{TEST_PREFIX}{base}{uuid.uuid4().hex[:8]}"


def test_v2_rules_crud(oid, key):
    """Create a D&R rule via hive, verify it appears in the list, delete it, verify it is gone."""
    client = Client(oid=oid, api_key=key)
    org = Organization(client)
    rule_name = _unique_name("rule-")
    hive = Hive(org, "dr-general")

    rule_data = {
        "detect": {"op": "is", "event": "NEW_PROCESS", "path": "event/FILE_PATH", "value": "test-never-match.exe"},
        "respond": [{"action": "report", "name": rule_name}],
    }

    try:
        # Create
        record = HiveRecord(rule_name, data=rule_data)
        hive.set(record)

        # Verify present
        rules = hive.list()
        assert rule_name in rules, f"Rule '{rule_name}' not found in rules list"
    finally:
        # Cleanup - always attempt deletion
        try:
            hive.delete(rule_name)
        except Exception:
            pass

    # Verify gone after deletion
    rules_after = hive.list()
    assert rule_name not in rules_after, f"Rule '{rule_name}' still present after deletion"


def test_v2_fps_crud(oid, key):
    """Create a false-positive rule via hive, verify it appears, delete it, verify it is gone."""
    client = Client(oid=oid, api_key=key)
    org = Organization(client)
    fp_name = _unique_name("fp-")
    hive = Hive(org, "fp")

    fp_rule = {"op": "is", "path": "detect/event/FILE_PATH", "value": "test-never-match.exe"}

    try:
        # Create
        record = HiveRecord(fp_name, data=fp_rule)
        hive.set(record)

        # Verify present
        fps = hive.list()
        assert fp_name in fps, f"FP rule '{fp_name}' not found in FP list"
    finally:
        # Cleanup
        try:
            hive.delete(fp_name)
        except Exception:
            pass

    # Verify gone
    fps_after = hive.list()
    assert fp_name not in fps_after, f"FP rule '{fp_name}' still present after deletion"


def test_v2_rules_namespace(oid, key):
    """Create a D&R rule in the 'managed' namespace via hive, verify, and delete."""
    client = Client(oid=oid, api_key=key)
    org = Organization(client)
    rule_name = _unique_name("ns-rule-")
    hive = Hive(org, "dr-managed")

    rule_data = {
        "detect": {"op": "is", "event": "NEW_PROCESS", "path": "event/FILE_PATH", "value": "test-never-match.exe"},
        "respond": [{"action": "report", "name": rule_name}],
    }

    try:
        # Create in managed namespace
        record = HiveRecord(rule_name, data=rule_data)
        hive.set(record)

        # Verify present when querying managed namespace
        rules = hive.list()
        assert rule_name in rules, (
            f"Rule '{rule_name}' not found in managed namespace rules"
        )
    finally:
        # Cleanup
        try:
            hive.delete(rule_name)
        except Exception:
            pass

    # Verify gone
    rules_after = hive.list()
    assert rule_name not in rules_after, (
        f"Rule '{rule_name}' still present in managed namespace after deletion"
    )
