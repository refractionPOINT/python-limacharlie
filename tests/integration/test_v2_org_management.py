"""Integration tests for LimaCharlie v2 SDK Organization management (read-only)."""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from limacharlie.client import Client
from limacharlie.sdk.organization import Organization


def _make_org(oid, key):
    client = Client(oid=oid, api_key=key)
    return Organization(client)


def test_v2_org_urls(oid, key):
    """Test that get_urls returns a non-empty dict of service URLs."""
    org = _make_org(oid, key)
    urls = org.get_urls()
    assert isinstance(urls, dict), f"Expected dict from get_urls(), got {type(urls)}"
    assert len(urls) > 0, "Expected at least one URL entry"


def test_v2_org_tags(oid, key):
    """Test that get_all_tags returns a list."""
    org = _make_org(oid, key)
    tags = org.get_all_tags()
    assert isinstance(tags, list), f"Expected list from get_all_tags(), got {type(tags)}"


def test_v2_org_who_am_i(oid, key):
    """Test who_am_i returns identity information."""
    org = _make_org(oid, key)
    identity = org.who_am_i()
    assert isinstance(identity, dict), f"Expected dict from who_am_i(), got {type(identity)}"


def test_v2_org_test_auth(oid, key):
    """Test that test_auth succeeds with valid credentials."""
    org = _make_org(oid, key)
    result = org.test_auth()
    assert result is True, "Expected test_auth() to return True for valid credentials"


def test_v2_org_get_info(oid, key):
    """Test that get_info returns org details containing the oid."""
    org = _make_org(oid, key)
    info = org.get_info()
    assert isinstance(info, dict), f"Expected dict from get_info(), got {type(info)}"
    assert "oid" in info, f"Expected 'oid' key in org info, got keys: {list(info.keys())}"
    assert info["oid"] == oid


def test_v2_org_schemas(oid, key):
    """Test that get_schemas returns a dict of schema definitions."""
    org = _make_org(oid, key)
    schemas = org.get_schemas()
    assert isinstance(schemas, dict), f"Expected dict from get_schemas(), got {type(schemas)}"


def test_v2_org_list_accessible_orgs(oid, key):
    """Test listing accessible orgs returns the expected structure."""
    org = _make_org(oid, key)
    result = org.list_accessible_orgs()
    assert isinstance(result, dict), f"Expected dict from list_accessible_orgs(), got {type(result)}"
    assert "orgs" in result, f"Expected 'orgs' key, got keys: {list(result.keys())}"
    assert "names" in result, f"Expected 'names' key, got keys: {list(result.keys())}"
    assert isinstance(result["orgs"], list), "Expected 'orgs' to be a list"
    assert isinstance(result["names"], dict), "Expected 'names' to be a dict"
    # The current org should appear in the accessible orgs list
    assert oid in result["orgs"], f"Current oid {oid} not found in accessible orgs"
