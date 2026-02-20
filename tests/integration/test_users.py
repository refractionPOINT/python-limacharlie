"""Integration tests for LimaCharlie v2 SDK users."""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from limacharlie.client import Client
from limacharlie.sdk.organization import Organization
from limacharlie.sdk.users import Users

TEST_PREFIX = "test-cli-v2-"


def test_v2_users_list(oid, key):
    """List users in the org and verify the response is a dict or list."""
    client = Client(oid=oid, api_key=key)
    org = Organization(client)
    users = Users(org)

    result = users.list()
    assert isinstance(result, (dict, list)), (
        f"Expected dict or list from users.list(), got {type(result).__name__}"
    )
    # There should be at least one user (the current API key owner).
    if isinstance(result, dict):
        assert len(result) > 0, "Expected at least one user in the org"
    elif isinstance(result, list):
        assert len(result) > 0, "Expected at least one user in the org"


def test_v2_users_list_permissions(oid, key):
    """List user permissions and verify the response is a dict or list."""
    client = Client(oid=oid, api_key=key)
    org = Organization(client)
    users = Users(org)

    result = users.list_permissions()
    assert isinstance(result, (dict, list)), (
        f"Expected dict or list from users.list_permissions(), "
        f"got {type(result).__name__}"
    )
