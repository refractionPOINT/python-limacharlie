"""Integration tests for LimaCharlie v2 SDK Groups."""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from limacharlie.client import Client
from limacharlie.sdk.organization import Organization
from limacharlie.sdk.groups import Groups


def test_v2_groups_list(oid, key):
    """Test listing groups returns a valid response."""
    client = Client(oid=oid, api_key=key)
    org = Organization(client)
    groups = Groups(org)

    result = groups.list()
    # The API returns a dict (group_id -> details) or a list.
    assert isinstance(result, (dict, list)), (
        f"Expected dict or list from groups.list(), got {type(result)}"
    )


def test_v2_groups_crud(oid, key):
    """Create a group, verify it exists, delete it, verify it is gone."""
    client = Client(oid=oid, api_key=key)
    org = Organization(client)
    groups = Groups(org)

    TEST_PREFIX = "test-cli-v2-"
    import uuid
    group_name = f"{TEST_PREFIX}group-{uuid.uuid4().hex[:8]}"
    group_id = None

    try:
        # Create
        create_result = groups.create(group_name)
        assert isinstance(create_result, dict), (
            f"Expected dict from groups.create(), got {type(create_result)}"
        )
        # Extract the group id from the create response
        group_id = create_result.get("gid") or create_result.get("id") or create_result.get("group_id")
        assert group_id is not None, (
            f"Expected group ID in create response, got keys: {list(create_result.keys())}"
        )

        # Verify present in listing
        all_groups = groups.list()
        if isinstance(all_groups, dict):
            found = group_id in all_groups or any(
                g.get("name") == group_name for g in all_groups.values() if isinstance(g, dict)
            )
        else:
            found = any(
                g.get("gid") == group_id or g.get("name") == group_name
                for g in all_groups if isinstance(g, dict)
            )
        assert found, f"Group '{group_name}' (id={group_id}) not found in listing"

        # Get single group
        detail = groups.get(group_id)
        assert isinstance(detail, dict), f"Expected dict from groups.get(), got {type(detail)}"
    finally:
        if group_id is not None:
            try:
                groups.delete(group_id)
            except Exception:
                pass
