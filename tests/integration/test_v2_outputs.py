"""Integration tests for LimaCharlie v2 SDK outputs."""

import sys
import os
import uuid

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from limacharlie.client import Client
from limacharlie.sdk.organization import Organization

TEST_PREFIX = "test-cli-v2-"


def _unique_name(base=""):
    return f"{TEST_PREFIX}{base}{uuid.uuid4().hex[:8]}"


def test_v2_outputs_crud(oid, key):
    """Create a syslog output, verify it appears in the list, delete it, verify it is gone."""
    client = Client(oid=oid, api_key=key)
    org = Organization(client)
    output_name = _unique_name("output-")

    try:
        # Create a syslog output pointing at a dummy destination.
        org.add_output(
            output_name,
            module="syslog",
            data_type="event",
            dest_host="127.0.0.1:514",
        )

        # Verify present
        outputs = org.get_outputs()
        assert output_name in outputs, (
            f"Output '{output_name}' not found in outputs list. "
            f"Available: {list(outputs.keys())}"
        )

        # Verify basic fields persisted
        output_entry = outputs[output_name]
        assert output_entry.get("module") == "syslog", (
            f"Expected module 'syslog', got '{output_entry.get('module')}'"
        )
        assert output_entry.get("type") == "event", (
            f"Expected type 'event', got '{output_entry.get('type')}'"
        )
    finally:
        # Cleanup
        try:
            org.delete_output(output_name)
        except Exception:
            pass

    # Verify gone after deletion
    outputs_after = org.get_outputs()
    assert output_name not in outputs_after, (
        f"Output '{output_name}' still present after deletion"
    )
