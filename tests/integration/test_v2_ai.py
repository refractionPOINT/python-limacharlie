"""Integration tests for LimaCharlie v2 SDK AI generation."""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from limacharlie.client import Client
from limacharlie.sdk.organization import Organization
from limacharlie.sdk.ai import AI
from limacharlie.errors import LimaCharlieError


def test_v2_ai_generate_dr_rule(oid, key):
    """Test AI D&R rule generation with a simple prompt."""
    client = Client(oid=oid, api_key=key)
    org = Organization(client)
    ai = AI(org)

    result = ai.generate_dr_rule("detect any process named notepad.exe")
    assert isinstance(result, dict), f"Expected dict from generate_dr_rule, got {type(result)}"


def test_v2_ai_generate_detection(oid, key):
    """Test AI detection-only generation."""
    client = Client(oid=oid, api_key=key)
    org = Organization(client)
    ai = AI(org)

    result = ai.generate_detection("detect SSH connections from unusual IPs")
    assert isinstance(result, dict), f"Expected dict from generate_detection, got {type(result)}"


def test_v2_ai_generate_response(oid, key):
    """Test AI response-only generation."""
    client = Client(oid=oid, api_key=key)
    org = Organization(client)
    ai = AI(org)

    result = ai.generate_response("report the detection and tag the sensor as compromised")
    assert isinstance(result, dict), f"Expected dict from generate_response, got {type(result)}"


def test_v2_ai_generate_lcql(oid, key):
    """Test AI LCQL query generation."""
    client = Client(oid=oid, api_key=key)
    org = Organization(client)
    ai = AI(org)

    result = ai.generate_lcql("find all Windows sensors that have been online in the last hour")
    assert isinstance(result, dict), f"Expected dict from generate_lcql, got {type(result)}"
