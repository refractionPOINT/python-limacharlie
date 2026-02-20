"""Integration tests for LimaCharlie v2 SDK jobs."""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from limacharlie.client import Client
from limacharlie.sdk.organization import Organization
from limacharlie.sdk.jobs import Jobs


def test_v2_jobs_list(oid, key):
    """Verify listing jobs returns a valid response without error."""
    client = Client(oid=oid, api_key=key)
    org = Organization(client)
    jobs = Jobs(org)

    result = jobs.list()
    assert result is not None, "Jobs list returned None"
    # The API may return a dict (with a 'jobs' key) or a list directly.
    assert isinstance(result, (dict, list)), (
        f"Expected dict or list from jobs.list(), got {type(result)}"
    )


def test_v2_jobs_list_with_limit(oid, key):
    """Verify listing jobs with a limit does not error."""
    client = Client(oid=oid, api_key=key)
    org = Organization(client)
    jobs = Jobs(org)

    result = jobs.list(limit=5)
    assert result is not None, "Jobs list with limit returned None"
    assert isinstance(result, (dict, list)), (
        f"Expected dict or list from jobs.list(limit=5), got {type(result)}"
    )
