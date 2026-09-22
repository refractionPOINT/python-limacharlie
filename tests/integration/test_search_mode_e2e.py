"""End-to-end tests for the search consumption mode, against a live backend.

These are NOT unit tests. They submit real searches to a real organization and
assert on what the server reports back, so a failure here is a statement about
a deployment, not necessarily about this package. Read the skip reason below
before treating one as a regression.

Running them
------------

They are gated twice over and skip by default:

1. ``tests/integration`` is outside ``testpaths`` in pyproject.toml, so a plain
   ``pytest`` run, which is what CI runs, never collects this file.
2. Even when the directory is named explicitly, every test here skips unless
   ``LC_TEST_SEARCH_MODE_E2E`` is set in the environment.

To actually run them::

    LC_TEST_SEARCH_MODE_E2E=1 pytest tests/integration/test_search_mode_e2e.py \\
        --oid <organization id> --key <api key> -v

Deselect them from an otherwise live integration run with
``-m "not searchmode_e2e"``.

Why the second gate exists
--------------------------

The ``mode`` field is served by the search backend. Until that support is
deployed and enabled for the organization under test, these fail for a
server-side reason with nothing wrong in this package. The environment
variable is the opt-in that says "the backend this is pointed at is expected
to support mode". Without it the honest result is a skip, not a red build.

What they assert, and what they deliberately do not
---------------------------------------------------

``mode`` is a hint. It is enabled per organization and the server may also
select the mode itself, so a page can legitimately run as something other than
what was asked for. **These tests therefore never assert that ``searchMode``
equals the requested mode.** A test that demanded it would fail for a correct
reason and teach whoever sees it to ignore the file. What is asserted is that
the server reports an applied mode at all, that it is a mode this package
knows, that it does not change underneath a single paginated search, and that
the rows arrive whole. Asserting the equality is only sound where the test
also controls the organization's configuration, which these do not.
"""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from limacharlie.client import Client
from limacharlie.sdk.organization import Organization
from limacharlie.sdk.search import (
    SEARCH_MODE_BATCH,
    SEARCH_MODE_INTERACTIVE,
    SEARCH_MODES,
    Search,
)

# The opt-in that says the backend under test is expected to serve `mode`.
_E2E_ENV_VAR = "LC_TEST_SEARCH_MODE_E2E"

_SKIP_REASON = (
    "Live search-mode end-to-end test, skipped by default. To run: set "
    f"{_E2E_ENV_VAR}=1 and pass --oid and --key for an organization with "
    "searchable telemetry in the window under test. These exercise the "
    "server's optional `mode` field on POST /v1/search, which must be "
    "deployed and enabled for that organization first; until it is, they "
    "fail for a server-side reason and not because of a defect in this "
    "package."
)

pytestmark = [
    pytest.mark.searchmode_e2e,
    pytest.mark.skipif(not os.environ.get(_E2E_ENV_VAR), reason=_SKIP_REASON),
]

# A broad query over a recent window, chosen to have the best chance of
# returning enough data to paginate on any organization with live sensors.
_QUERY = "* | * | *"
_WINDOW_SECONDS = 24 * 3600

# Safety cap on how many pages the pagination test will walk. Reaching it is
# not a failure: it means the result set is larger than this test needs, which
# is exactly the case it wants to observe.
_MAX_PAGES = 5

# The three fields a paginated page reports about its own shape.
_PAGINATION_STAT_FIELDS = ("searchMode", "pageSize", "paginatedByteCap")


def _search(oid, key):
    """Build a Search bound to the organization under test."""
    return Search(Organization(Client(oid=oid, api_key=key)))


def _window():
    """The time range every test here searches over."""
    now = int(time.time())
    return now - _WINDOW_SECONDS, now


def _page_stats(result):
    """The stats dict of a result, or None when it carries none."""
    stats = result.get("stats")
    return stats if isinstance(stats, dict) else None


def _paginated_pages(results):
    """The subset of results that report a mode, i.e. that paginated.

    A search that returns everything at once reports none of the three
    pagination fields, which is the documented contract rather than a fault,
    so the tests that need a paginated page look for one rather than assuming
    the first result is one.
    """
    pages = []
    for result in results:
        stats = _page_stats(result)
        if stats and stats.get("searchMode") is not None:
            pages.append((result, stats))
    return pages


def _require_paginated_page(results):
    """Return the first paginated page, or skip explaining why there is none."""
    pages = _paginated_pages(results)
    if not pages:
        pytest.skip(
            "The organization returned no paginated page for this window, so "
            "there is no applied mode to inspect. Point the test at an "
            "organization with more telemetry in the last "
            f"{_WINDOW_SECONDS // 3600}h, or widen _WINDOW_SECONDS."
        )
    return pages[0]


def _assert_applied_mode(stats):
    """Assert the server reported a mode this package understands.

    Deliberately not an equality check against the requested mode: see the
    module docstring. A value outside SEARCH_MODES means either the server
    grew a mode this package does not know, which is worth surfacing here, or
    the field changed shape.
    """
    applied = stats.get("searchMode")
    assert isinstance(applied, str) and applied, (
        f"expected the page to report a searchMode string, got {applied!r}"
    )
    assert applied in SEARCH_MODES, (
        f"server reported searchMode {applied!r}, which is not one of "
        f"{sorted(SEARCH_MODES)}. Either the server has a mode this package "
        f"does not know about, or the field has changed."
    )
    return applied


def _assert_rows_are_whole(result):
    """Assert every row on a page is a complete record.

    The point of the mode is that it moves page boundaries. A boundary must
    fall between records, never through one, so a row that arrives without its
    metadata or its body would mean a page was cut mid-record.
    """
    for index, row in enumerate(result.get("rows") or []):
        assert isinstance(row, dict), (
            f"row {index} is {type(row).__name__}, expected a dict"
        )
        assert "data" in row, f"row {index} arrived without its 'data' body"
        assert isinstance(row["data"], dict), (
            f"row {index} has a {type(row['data']).__name__} body, expected a dict"
        )


@pytest.mark.parametrize("mode", [SEARCH_MODE_BATCH, SEARCH_MODE_INTERACTIVE])
def test_a_submitted_mode_comes_back_as_an_applied_mode(oid, key, mode):
    """Submitting a mode yields pages that report which mode they ran as.

    Both modes are exercised through the same assertions, because the contract
    is the same for each: the request is a hint and the page states the
    outcome.
    """
    start, end = _window()
    results = list(_search(oid, key).execute(
        _QUERY, start_time=start, end_time=end, mode=mode, limit=2,
    ))

    _, stats = _require_paginated_page(results)
    _assert_applied_mode(stats)


def test_a_paginated_page_reports_all_three_shape_fields(oid, key):
    """searchMode, pageSize and paginatedByteCap all arrive together."""
    start, end = _window()
    results = list(_search(oid, key).execute(
        _QUERY, start_time=start, end_time=end, mode=SEARCH_MODE_BATCH, limit=2,
    ))

    _, stats = _require_paginated_page(results)

    missing = [f for f in _PAGINATION_STAT_FIELDS if stats.get(f) is None]
    assert not missing, (
        f"paginated page is missing {missing}; a page that reports one of the "
        f"three should report all three. Got stats keys: {sorted(stats)}"
    )
    for field in ("pageSize", "paginatedByteCap"):
        assert isinstance(stats[field], int) and stats[field] > 0, (
            f"{field} is {stats[field]!r}, expected a positive integer"
        )


def test_the_applied_mode_holds_for_every_page_of_one_search(oid, key):
    """The mode is submitted once and the continuation pages inherit it.

    So every page of a single search must report the same applied mode. A page
    that disagreed with the one before it would mean the mode was not actually
    carried across the pagination boundary, which is the part of the contract
    this package relies on by never resending it.
    """
    start, end = _window()
    search = _search(oid, key)

    pages = []
    for result in search.execute(_QUERY, start_time=start, end_time=end,
                                 mode=SEARCH_MODE_BATCH):
        stats = _page_stats(result)
        if stats and stats.get("searchMode") is not None:
            pages.append((result, stats))
            _assert_rows_are_whole(result)
        if len(pages) >= _MAX_PAGES:
            break

    if len(pages) < 2:
        pytest.skip(
            f"The organization returned {len(pages)} paginated page(s) for "
            "this window, so there is no boundary to check the mode across. "
            "Point the test at an organization with more telemetry, or widen "
            "_WINDOW_SECONDS."
        )

    applied = [_assert_applied_mode(stats) for _, stats in pages]
    assert len(set(applied)) == 1, (
        f"the applied mode changed across the pages of one search: {applied}. "
        "The mode is submitted once and inherited by continuation pages, so "
        "it must not vary within a search."
    )


def test_both_modes_return_the_same_rows_in_the_same_order(oid, key):
    """Only the page boundaries differ between modes, never the result set.

    Runs the same bounded query twice, once per mode, and compares the rows
    flattened across page boundaries. This is the claim that makes the mode
    safe to default differently in the SDK and the CLI, so it is worth paying
    a second query to check.

    Skipped rather than failed when the window is not stable between the two
    runs, since live telemetry arriving mid-test is an environment condition
    and not a defect.
    """
    # A window that ends in the past, so no new data can land inside it
    # between the two runs.
    now = int(time.time())
    end = now - 300
    start = end - _WINDOW_SECONDS
    search = _search(oid, key)

    def rows_for(mode):
        collected = []
        for result in search.execute(_QUERY, start_time=start, end_time=end,
                                     mode=mode, limit=_MAX_PAGES):
            for row in result.get("rows") or []:
                collected.append(row)
        return collected

    batch_rows = rows_for(SEARCH_MODE_BATCH)
    interactive_rows = rows_for(SEARCH_MODE_INTERACTIVE)

    if not batch_rows or not interactive_rows:
        pytest.skip(
            "One of the two runs returned no rows, so there is nothing to "
            "compare. Point the test at an organization with telemetry in the "
            "window."
        )

    # The per-page limit means each run may stop at a different point in the
    # result set, so compare the common prefix rather than the whole thing.
    common = min(len(batch_rows), len(interactive_rows))
    assert batch_rows[:common] == interactive_rows[:common], (
        "the two modes returned different rows for the same query. Only the "
        "page boundaries are meant to differ between modes; the result set "
        "and its ordering are meant to be identical."
    )
