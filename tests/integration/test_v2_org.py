import sys
import os
import uuid

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from limacharlie.client import Client
from limacharlie.sdk.organization import Organization


def _make_org(oid, key):
    client = Client(oid=oid, api_key=key)
    return Organization(client)


def test_v2_org_info(oid, key):
    org = _make_org(oid, key)
    info = org.get_info()
    assert isinstance(info, dict)
    assert "oid" in info, f"Expected 'oid' key in org info, got keys: {list(info.keys())}"
    assert info["oid"] == oid


def test_v2_org_urls(oid, key):
    org = _make_org(oid, key)
    urls = org.get_urls()
    assert isinstance(urls, dict)
    assert len(urls) > 0, "Expected at least one URL entry"


def test_v2_org_errors(oid, key):
    org = _make_org(oid, key)
    errors = org.get_errors()
    # The API may return a dict with an "errors" key or a list directly.
    # Normalize: if it is a dict, pull the list from it.
    if isinstance(errors, dict):
        errors = errors.get("errors", [])
    assert isinstance(errors, list)


def test_v2_org_stats(oid, key):
    org = _make_org(oid, key)
    stats = org.get_stats()
    assert isinstance(stats, dict)
