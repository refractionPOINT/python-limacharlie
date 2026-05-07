import sys
import os
import uuid
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from limacharlie.client import Client
from limacharlie.sdk.organization import Organization
from limacharlie.sdk.hive import Hive, HiveRecord

TEST_PREFIX = "test-cli-v2-"


def _make_org(oid, key):
    client = Client(oid=oid, api_key=key)
    return Organization(client)


def test_v2_hive_crud(oid, key):
    org = _make_org(oid, key)
    hive = Hive(org, "fp")
    unique_name = TEST_PREFIX + str(uuid.uuid4())

    # Build a valid FP rule — the "fp" hive validates data as FP rules.
    record = HiveRecord(unique_name, data={
        "op": "is",
        "event": "NEW_PROCESS",
        "path": "event/FILE_PATH",
        "value": "test-cli-v2-nonexistent.exe",
    })
    record.enabled = True
    record.expiry = 0
    record.tags = []
    record.comment = "integration test"

    try:
        # Create
        set_resp = hive.set(record)
        assert set_resp is not None

        # Small delay for eventual consistency
        time.sleep(2)

        # Get and verify data
        fetched = hive.get(unique_name)
        assert fetched is not None
        assert isinstance(fetched.data, dict)
        assert fetched.data.get("op") == "is"

        # List and verify presence
        records = hive.list()
        assert isinstance(records, dict)
        assert unique_name in records, (
            f"Expected '{unique_name}' in hive list, got keys: {list(records.keys())[:10]}"
        )
    finally:
        # Always clean up
        try:
            hive.delete(unique_name)
        except Exception:
            pass

    # Verify deletion
    time.sleep(2)
    records_after = hive.list()
    assert unique_name not in records_after
