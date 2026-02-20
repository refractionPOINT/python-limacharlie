"""Integration tests for LimaCharlie v2 SDK extensions."""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from limacharlie.client import Client
from limacharlie.sdk.organization import Organization
from limacharlie.sdk.extensions import Extensions

TEST_PREFIX = "test-cli-v2-"


def test_v2_extensions_list_subscribed(oid, key):
    """List subscribed extensions and verify the response is a dict or list."""
    client = Client(oid=oid, api_key=key)
    org = Organization(client)
    extensions = Extensions(org)

    result = extensions.list_subscribed()
    assert isinstance(result, (dict, list)), (
        f"Expected dict or list from extensions.list_subscribed(), "
        f"got {type(result).__name__}"
    )
