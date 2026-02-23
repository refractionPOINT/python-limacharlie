"""Integration tests for LimaCharlie v2 SDK key management (API, installation, ingestion)."""

import sys
import os
import uuid

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from limacharlie.client import Client
from limacharlie.sdk.organization import Organization

TEST_PREFIX = "test-cli-v2-"


def _unique_name(base=""):
    return f"{TEST_PREFIX}{base}{uuid.uuid4().hex[:8]}"


def test_v2_api_keys_crud(oid, key):
    """Create an API key, verify it appears in the list, delete it, verify it is gone."""
    client = Client(oid=oid, api_key=key)
    org = Organization(client)
    key_name = _unique_name("apikey-")
    created_key_hash = None

    try:
        # Create with minimal permissions
        result = org.add_api_key(key_name, ["org.get"])

        # The response should contain a key hash we can use for deletion.
        # Depending on the API version the hash may be in different fields.
        created_key_hash = result.get("key_hash") or result.get("hash")
        assert created_key_hash is not None, (
            f"API key creation did not return a key_hash. Response: {result}"
        )

        # Verify present in the key list
        keys = org.get_api_keys()
        # get_api_keys returns a dict where keys are key hashes or a list -
        # handle both shapes.
        if isinstance(keys, dict):
            found = any(
                entry.get("key_name") == key_name or entry.get("name") == key_name
                for entry in (keys.values() if not isinstance(list(keys.values())[0] if keys else None, str) else [keys])
                if isinstance(entry, dict)
            ) or created_key_hash in keys
        else:
            found = any(
                (entry.get("key_name") == key_name or entry.get("name") == key_name or entry.get("key_hash") == created_key_hash)
                for entry in keys
                if isinstance(entry, dict)
            )
        assert found, f"API key '{key_name}' (hash={created_key_hash}) not found in keys list"
    finally:
        # Cleanup
        if created_key_hash:
            try:
                org.remove_api_key(created_key_hash)
            except Exception:
                pass

    # Verify gone
    keys_after = org.get_api_keys()
    if isinstance(keys_after, dict):
        assert created_key_hash not in keys_after, (
            f"API key hash '{created_key_hash}' still present after deletion"
        )
    else:
        still_present = any(
            entry.get("key_hash") == created_key_hash
            for entry in keys_after
            if isinstance(entry, dict)
        )
        assert not still_present, (
            f"API key hash '{created_key_hash}' still present after deletion"
        )


def test_v2_installation_keys_crud(oid, key):
    """Create an installation key, verify it exists, delete it, verify it is gone."""
    client = Client(oid=oid, api_key=key)
    org = Organization(client)
    desc = _unique_name("instkey-")
    created_iid = None

    try:
        # Create
        result = org.create_installation_key(desc)
        created_iid = result.get("iid")
        assert created_iid is not None, (
            f"Installation key creation did not return an iid. Response: {result}"
        )

        # Verify present
        keys = org.get_installation_keys()
        # The response may be a dict keyed by iid or a list.
        if isinstance(keys, dict):
            found = created_iid in keys
        else:
            found = any(
                entry.get("iid") == created_iid
                for entry in keys
                if isinstance(entry, dict)
            )
        assert found, (
            f"Installation key '{created_iid}' not found in keys list"
        )
    finally:
        # Cleanup
        if created_iid:
            try:
                org.delete_installation_key(created_iid)
            except Exception:
                pass

    # Verify gone
    keys_after = org.get_installation_keys()
    if isinstance(keys_after, dict):
        assert created_iid not in keys_after, (
            f"Installation key '{created_iid}' still present after deletion"
        )
    else:
        still_present = any(
            entry.get("iid") == created_iid
            for entry in keys_after
            if isinstance(entry, dict)
        )
        assert not still_present, (
            f"Installation key '{created_iid}' still present after deletion"
        )


def test_v2_ingestion_keys_crud(oid, key):
    """Create an ingestion key, verify it exists, delete it, verify it is gone."""
    client = Client(oid=oid, api_key=key)
    org = Organization(client)
    key_name = _unique_name("ingkey-")

    try:
        # Create
        result = org.create_ingestion_key(key_name)
        # The response should acknowledge creation.
        assert result is not None, "Ingestion key creation returned None"

        # Verify present
        keys = org.get_ingestion_keys()
        # The response shape varies; look for our key name.
        if isinstance(keys, dict):
            found = key_name in keys or any(
                entry.get("name") == key_name
                for entry in keys.values()
                if isinstance(entry, dict)
            )
        elif isinstance(keys, list):
            found = any(
                (entry.get("name") == key_name if isinstance(entry, dict) else entry == key_name)
                for entry in keys
            )
        else:
            found = False
        assert found, f"Ingestion key '{key_name}' not found in keys list"
    finally:
        # Cleanup
        try:
            org.delete_ingestion_key(key_name)
        except Exception:
            pass

    # Verify gone
    keys_after = org.get_ingestion_keys()
    if isinstance(keys_after, dict):
        gone = key_name not in keys_after and not any(
            entry.get("name") == key_name
            for entry in keys_after.values()
            if isinstance(entry, dict)
        )
    elif isinstance(keys_after, list):
        gone = not any(
            (entry.get("name") == key_name if isinstance(entry, dict) else entry == key_name)
            for entry in keys_after
        )
    else:
        gone = True
    assert gone, f"Ingestion key '{key_name}' still present after deletion"
