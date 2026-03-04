"""Integration tests for LimaCharlie v2 SDK search (LCQL)."""

import sys
import os
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from limacharlie.client import Client
from limacharlie.sdk.organization import Organization
from limacharlie.sdk.search import Search

TEST_PREFIX = "test-cli-v2-"


def test_v2_search_validate(oid, key):
    """Validate a simple LCQL query and verify the response is valid."""
    client = Client(oid=oid, api_key=key)
    org = Organization(client)
    search = Search(org)

    # Use a simple, syntactically valid LCQL query
    result = search.validate("* | NEW_PROCESS | event/FILE_PATH exists")
    assert isinstance(result, dict), (
        f"Expected dict from search.validate(), got {type(result).__name__}"
    )


def test_v2_search_execute(oid, key):
    """Execute an LCQL query over a short recent window. Empty results are acceptable."""
    client = Client(oid=oid, api_key=key)
    org = Organization(client)
    search = Search(org)

    now = int(time.time())
    one_hour_ago = now - 3600

    # Execute a query that is unlikely to match anything but is syntactically valid.
    # The generator may yield zero results, which is fine -- we just verify no errors.
    results = list(search.execute(
        "* | NEW_PROCESS | *",
        start_time=one_hour_ago,
        end_time=now,
        limit=5,
    ))
    assert isinstance(results, list), (
        f"Expected list from search.execute(), got {type(results).__name__}"
    )
