"""Integration tests for LimaCharlie v2 SDK artifacts."""

import sys
import os
import uuid

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from limacharlie.client import Client
from limacharlie.sdk.organization import Organization
from limacharlie.sdk.artifacts import Artifacts

TEST_PREFIX = "test-cli-v2-"


def test_v2_artifacts_list(oid, key):
    """List artifacts and verify the call succeeds and returns a valid response."""
    client = Client(oid=oid, api_key=key)
    org = Organization(client)
    artifacts = Artifacts(org)

    result = artifacts.list()
    # The response should be a dict (possibly with an 'artifacts' key) or a list.
    assert isinstance(result, (dict, list)), (
        f"Expected dict or list from artifacts.list(), got {type(result).__name__}"
    )


def test_v2_artifacts_upload_and_cleanup(oid, key):
    """Upload a small artifact — requires LC_LOGS_TOKEN or ingestion key."""
    client = Client(oid=oid, api_key=key)
    org = Organization(client)

    # Get an ingestion key to use as access_token for artifact upload.
    ingestion_keys = org.get_ingestion_keys()
    if not ingestion_keys:
        # No ingestion keys available; create one for the test.
        org.create_ingestion_key(TEST_PREFIX + "artifact-token")
        ingestion_keys = org.get_ingestion_keys()

    # Pick the first ingestion key's value.
    # The API returns {name: key_uuid_string} (not {name: {"key": ...}}).
    access_token = None
    for ik_data in ingestion_keys.values():
        if isinstance(ik_data, str) and ik_data:
            access_token = ik_data
            break
        elif isinstance(ik_data, dict):
            access_token = ik_data.get("key")
            if access_token:
                break

    assert access_token is not None, (
        f"Could not find an ingestion key to use as access_token. Keys: {ingestion_keys}"
    )

    artifacts = Artifacts(org, access_token=access_token)

    tmp_path = os.path.join(
        os.path.dirname(__file__),
        f"{TEST_PREFIX}artifact-{uuid.uuid4().hex[:8]}.txt",
    )

    try:
        with open(tmp_path, "w") as f:
            f.write("integration test artifact content")

        upload_resp = artifacts.upload(
            tmp_path,
            source=TEST_PREFIX + "source",
            hint="txt",
            retention_days=1,
        )
        assert upload_resp is not None, "Artifact upload returned None"

        # Verify listing still succeeds after upload
        result = artifacts.list()
        assert isinstance(result, (dict, list)), (
            f"Expected dict or list from artifacts.list() after upload, "
            f"got {type(result).__name__}"
        )
    finally:
        # Clean up the local temp file
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
