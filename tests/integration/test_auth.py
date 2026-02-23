"""Integration tests for LimaCharlie v2 SDK authentication and identity."""

import sys
import os
import uuid

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from limacharlie.client import Client
from limacharlie.sdk.organization import Organization

TEST_PREFIX = "test-cli-v2-"


def test_v2_credentials(oid, key):
    """Verify that test_auth succeeds and recognizes common permissions."""
    client = Client(oid=oid, api_key=key)
    org = Organization(client)

    # Basic auth must succeed.
    assert org.test_auth() is True

    # Verify specific permissions that every integration-test key should have.
    assert org.test_auth(["org.get", "sensor.list"]) is True


def test_v2_whoami(oid, key):
    """Verify who_am_i returns identity information with permissions."""
    client = Client(oid=oid, api_key=key)
    org = Organization(client)

    result = org.who_am_i()

    # The response must contain either user_perms (user-scoped key) or
    # orgs+perms (org-scoped key).
    has_user_perms = "user_perms" in result
    has_org_perms = "orgs" in result and "perms" in result
    assert has_user_perms or has_org_perms, (
        f"who_am_i response missing expected permission fields: {list(result.keys())}"
    )

    # Our OID must appear somewhere in the response.
    if has_user_perms:
        assert oid in result["user_perms"], (
            f"OID {oid} not found in user_perms keys"
        )
    else:
        assert oid in result["orgs"], (
            f"OID {oid} not found in orgs list"
        )
