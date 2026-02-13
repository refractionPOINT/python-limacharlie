"""Integration tests for LimaCharlie v2 SDK exfil watch rules."""

import sys
import os
import uuid
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from limacharlie.client import Client
from limacharlie.sdk.organization import Organization
from limacharlie.sdk.exfil import Exfil

TEST_PREFIX = "test-cli-v2-"


def _unique_name(base=""):
    return f"{TEST_PREFIX}{base}{uuid.uuid4().hex[:8]}"


def test_v2_exfil_watch_crud(oid, key):
    """Create an exfil watch rule, verify it appears in the list, delete it, verify gone."""
    client = Client(oid=oid, api_key=key)
    org = Organization(client)
    exfil = Exfil(org)
    rule_name = _unique_name("exfil-watch-")

    try:
        # Create a watch rule
        exfil.create_watch(
            name=rule_name,
            event="NEW_PROCESS",
            value="test-never-match.exe",
            operator="is",
            path="FILE_PATH",
        )

        # Allow eventual consistency
        time.sleep(2)

        # Verify present in list
        rules = exfil.list()
        # The list response may be nested; find our rule name somewhere in it.
        rules_str = str(rules)
        assert rule_name in rules_str, (
            f"Watch rule '{rule_name}' not found in exfil list. Response: {rules}"
        )
    finally:
        # Always clean up
        try:
            exfil.delete_watch(rule_name)
        except Exception:
            pass

    # Verify deletion
    time.sleep(2)
    rules_after = exfil.list()
    rules_after_str = str(rules_after)
    assert rule_name not in rules_after_str, (
        f"Watch rule '{rule_name}' still present after deletion"
    )


def test_v2_exfil_event_crud(oid, key):
    """Create an exfil event rule, verify it appears, delete it, verify gone."""
    client = Client(oid=oid, api_key=key)
    org = Organization(client)
    exfil = Exfil(org)
    rule_name = _unique_name("exfil-event-")

    try:
        # Create an event rule
        exfil.create_event(
            name=rule_name,
            events=["DNS_REQUEST"],
        )

        # Allow eventual consistency
        time.sleep(2)

        # Verify present in list
        rules = exfil.list()
        rules_str = str(rules)
        assert rule_name in rules_str, (
            f"Event rule '{rule_name}' not found in exfil list. Response: {rules}"
        )
    finally:
        # Always clean up
        try:
            exfil.delete_event(rule_name)
        except Exception:
            pass

    # Verify deletion
    time.sleep(2)
    rules_after = exfil.list()
    rules_after_str = str(rules_after)
    assert rule_name not in rules_after_str, (
        f"Event rule '{rule_name}' still present after deletion"
    )


def test_v2_exfil_list(oid, key):
    """Verify listing exfil rules does not error."""
    client = Client(oid=oid, api_key=key)
    org = Organization(client)
    exfil = Exfil(org)

    result = exfil.list()
    assert result is not None, "Exfil list returned None"
    assert isinstance(result, dict), f"Expected dict from exfil.list(), got {type(result)}"
