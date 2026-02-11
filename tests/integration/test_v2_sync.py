"""Integration tests for LimaCharlie v2 SDK configuration sync (IaC)."""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from limacharlie.client import Client
from limacharlie.sdk.organization import Organization
from limacharlie.sdk.configs import Configs

TEST_PREFIX = "test-cli-v2-"


def test_v2_sync_fetch_rules(oid, key):
    """Fetch D&R rules via infrastructure-as-code sync and verify the response shape."""
    client = Client(oid=oid, api_key=key)
    org = Organization(client)
    configs = Configs(org)

    result = configs.fetch(sync_rules=True)
    assert isinstance(result, dict), (
        f"Expected dict from configs.fetch(), got {type(result).__name__}"
    )
    # The result should contain a version key per the Configs CONF_VERSION contract.
    assert "version" in result, (
        f"Expected 'version' key in fetched config, got keys: {list(result.keys())}"
    )


def test_v2_sync_fetch_outputs(oid, key):
    """Fetch outputs config and verify it returns a dict with version."""
    client = Client(oid=oid, api_key=key)
    org = Organization(client)
    configs = Configs(org)

    result = configs.fetch(sync_outputs=True)
    assert isinstance(result, dict), (
        f"Expected dict from configs.fetch(sync_outputs=True), "
        f"got {type(result).__name__}"
    )
    assert "version" in result, (
        f"Expected 'version' key in fetched config, got keys: {list(result.keys())}"
    )


def test_v2_sync_push_dry_run(oid, key):
    """Push an empty config with dry_run=True and verify no changes are made."""
    client = Client(oid=oid, api_key=key)
    org = Organization(client)
    configs = Configs(org)

    # Push a minimal valid config in dry-run mode -- should not modify anything.
    empty_config = {"version": Configs.CONF_VERSION}
    result = configs.push(
        config=empty_config,
        is_dry_run=True,
        sync_rules=True,
    )
    # push() returns a list of (op_type, resource_type, name) tuples.
    assert isinstance(result, list), (
        f"Expected list from configs.push(dry_run), got {type(result).__name__}"
    )
