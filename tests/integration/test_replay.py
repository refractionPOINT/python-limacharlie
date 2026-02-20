"""Integration tests for LimaCharlie v2 SDK replay."""

import sys
import os
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from limacharlie.client import Client
from limacharlie.sdk.organization import Organization
from limacharlie.sdk.replay import Replay
from limacharlie.errors import LimaCharlieError

TEST_PREFIX = "test-cli-v2-"


def test_v2_replay_dry_run(oid, key):
    """Run a replay in dry-run mode — may fail if replay service is not subscribed."""
    client = Client(oid=oid, api_key=key)
    org = Organization(client)
    replay = Replay(org)

    now = int(time.time())
    one_hour_ago = now - 3600

    detect = {
        "op": "is",
        "event": "NEW_PROCESS",
        "path": "event/FILE_PATH",
        "value": "test-cli-v2-nonexistent-binary.exe",
    }
    respond = [{"action": "report", "name": TEST_PREFIX + "replay-test"}]

    try:
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
    except LimaCharlieError as e:
        # Replay requires the org to be subscribed to the replay extension.
        assert "not registered to service" in str(e).lower() or "replay" in str(e).lower(), (
            f"Unexpected replay error: {e}"
        )
