"""Integration tests for LimaCharlie v2 SDK USP (Universal Sensor Protocol)."""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from limacharlie.client import Client
from limacharlie.sdk.organization import Organization
from limacharlie.sdk.usp import USP


def test_v2_usp_validate_json(oid, key):
    """Test USP validate with a minimal JSON adapter config."""
    client = Client(oid=oid, api_key=key)
    org = Organization(client)
    usp = USP(org)

    result = usp.validate(
        platform="json",
        mapping={
            "event_type_path": "event_type",
            "event_time_path": "timestamp",
        },
        json_input={
            "event_type": "test_event",
            "timestamp": "2024-01-01T00:00:00Z",
            "data": "hello",
        },
    )
    assert isinstance(result, dict), f"Expected dict from usp.validate(), got {type(result)}"


def test_v2_usp_validate_text(oid, key):
    """Test USP validate with a text input and a minimal adapter config."""
    client = Client(oid=oid, api_key=key)
    org = Organization(client)
    usp = USP(org)

    result = usp.validate(
        platform="text",
        mapping={
            "event_type_path": "event_type",
            "event_time_path": "event_time",
        },
        text_input="2024-01-01T00:00:00Z test_event some log line here",
    )
    assert isinstance(result, dict), f"Expected dict from usp.validate(), got {type(result)}"


def test_v2_usp_validate_with_hostname(oid, key):
    """Test USP validate with hostname parameter."""
    client = Client(oid=oid, api_key=key)
    org = Organization(client)
    usp = USP(org)

    result = usp.validate(
        platform="json",
        mapping={
            "event_type_path": "type",
            "event_time_path": "ts",
        },
        json_input={
            "type": "test",
            "ts": "2024-01-01T00:00:00Z",
        },
        hostname="test-cli-v2-host",
    )
    assert isinstance(result, dict), f"Expected dict from usp.validate(), got {type(result)}"
