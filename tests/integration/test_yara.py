"""Integration tests for LimaCharlie v2 SDK YARA management."""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from limacharlie.client import Client
from limacharlie.sdk.organization import Organization
from limacharlie.sdk.yara import Yara


def test_v2_yara_list_sources(oid, key):
    """Verify listing YARA sources does not error."""
    client = Client(oid=oid, api_key=key)
    org = Organization(client)
    yara = Yara(org)

    result = yara.list_sources()
    assert result is not None, "YARA list_sources returned None"
    assert isinstance(result, dict), (
        f"Expected dict from yara.list_sources(), got {type(result)}"
    )


def test_v2_yara_list_rules(oid, key):
    """Verify listing YARA rules does not error."""
    client = Client(oid=oid, api_key=key)
    org = Organization(client)
    yara = Yara(org)

    result = yara.list_rules()
    assert result is not None, "YARA list_rules returned None"
    assert isinstance(result, dict), (
        f"Expected dict from yara.list_rules(), got {type(result)}"
    )
