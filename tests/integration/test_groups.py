"""Integration tests for LimaCharlie v2 SDK Groups."""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from limacharlie.client import Client
from limacharlie.sdk.organization import Organization
from limacharlie.sdk.groups import Groups
from limacharlie.errors import LimaCharlieError


def test_v2_groups_list(oid, key):
    """Test listing groups — requires user auth, so may return 401 with API key."""
    client = Client(oid=oid, api_key=key)
    org = Organization(client)
    groups = Groups(org)

    try:
        result = groups.list()
        assert isinstance(result, (dict, list)), (
            f"Expected dict or list from groups.list(), got {type(result)}"
        )
    except LimaCharlieError as e:
        # Group management only accepts user-level JWT.
        assert "unauthorized" in str(e).lower() or "401" in str(e), (
            f"Unexpected error (expected 401 unauthorized): {e}"
        )


def test_v2_groups_crud(oid, key):
    """Test group CRUD — requires user auth, so may return 401 with API key."""
    client = Client(oid=oid, api_key=key)
    org = Organization(client)
    groups = Groups(org)

    import uuid
    group_name = f"test-cli-v2-group-{uuid.uuid4().hex[:8]}"
    group_id = None

    try:
        create_result = groups.create(group_name)
        assert isinstance(create_result, dict), (
            f"Expected dict from groups.create(), got {type(create_result)}"
        )
        group_id = create_result.get("gid") or create_result.get("id") or create_result.get("group_id")
        assert group_id is not None, (
            f"Expected group ID in create response, got keys: {list(create_result.keys())}"
        )
    except LimaCharlieError as e:
        # Group management only accepts user-level JWT.
        assert "unauthorized" in str(e).lower() or "401" in str(e), (
            f"Unexpected error (expected 401 unauthorized): {e}"
        )
    finally:
        if group_id is not None:
            try:
                groups.delete(group_id)
            except Exception:
                pass
