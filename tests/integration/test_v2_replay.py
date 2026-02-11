"""Integration tests for LimaCharlie v2 SDK replay."""

import sys
import os
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from limacharlie.client import Client
from limacharlie.sdk.organization import Organization
from limacharlie.sdk.replay import Replay

TEST_PREFIX = "test-cli-v2-"


def test_v2_replay_dry_run(oid, key):
    """Run a replay in dry-run mode with a simple rule and verify the response."""
    client = Client(oid=oid, api_key=key)
    org = Organization(client)
    replay = Replay(org)

    now = int(time.time())
    one_hour_ago = now - 3600

    # Use a simple detection rule that will not match anything meaningful.
    detect = {
        "op": "is",
        "event": "NEW_PROCESS",
        "path": "event/FILE_PATH",
        "value": "test-cli-v2-nonexistent-binary.exe",
    }
    respond = [{"action": "report", "name": TEST_PREFIX + "replay-test"}]

    result = replay.run(
        detect=detect,
        respond=respond,
        start=one_hour_ago,
        end=now,
        dry_run=True,
        limit_events=10,
    )
    assert isinstance(result, dict), (
        f"Expected dict from replay.run(), got {type(result).__name__}"
    )
