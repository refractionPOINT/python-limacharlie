"""Integration tests for LimaCharlie v2 SDK Spout (streaming)."""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from limacharlie.client import Client
from limacharlie.sdk.organization import Organization
from limacharlie.sdk.spout import Spout, _VALID_DATA_TYPES
from limacharlie.errors import ValidationError


def test_v2_spout_construct_and_shutdown(oid, key):
    """Create a Spout, verify it connects, then shut it down cleanly."""
    client = Client(oid=oid, api_key=key)
    org = Organization(client)
    spout = None
    try:
        spout = Spout(org, "event")
        assert spout.is_running, "Spout should be running after construction"
        assert spout.dropped == 0, "Dropped count should start at zero"
    finally:
        if spout is not None:
            spout.shutdown()

    assert not spout.is_running, "Spout should not be running after shutdown"


def test_v2_spout_invalid_data_type(oid, key):
    """Verify that an invalid data_type raises a ValidationError."""
    client = Client(oid=oid, api_key=key)
    org = Organization(client)
    raised = False
    try:
        Spout(org, "not_a_real_type")
    except ValidationError:
        raised = True
    assert raised, "Expected ValidationError for invalid data_type"


def test_v2_spout_get_timeout(oid, key):
    """Create a Spout, call get() with a short timeout, expect None (no data)."""
    client = Client(oid=oid, api_key=key)
    org = Organization(client)
    spout = None
    try:
        spout = Spout(org, "detect")
        # With no sensors generating detections, we expect None back quickly.
        result = spout.get(timeout=2)
        # result is either None (no data) or a dict (unlikely in test org)
        assert result is None or isinstance(result, dict), (
            f"Expected None or dict from get(), got {type(result)}"
        )
    finally:
        if spout is not None:
            spout.shutdown()


def test_v2_spout_valid_data_types(oid, key):
    """Verify all documented valid data types can be used to construct a Spout."""
    client = Client(oid=oid, api_key=key)
    org = Organization(client)
    for dt in _VALID_DATA_TYPES:
        spout = None
        try:
            spout = Spout(org, dt)
            assert spout.is_running, f"Spout for data_type '{dt}' should be running"
        finally:
            if spout is not None:
                spout.shutdown()
