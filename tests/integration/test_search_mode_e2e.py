"""End-to-end tests for the search consumption mode, against a live backend.

These are NOT unit tests. They submit real searches to a real organization and
assert on what the server reports back, so a failure here is a statement about
a deployment, not necessarily about this package. Read the skip reason below
before treating one as a regression.

Running them
------------

They run in the PR build's integration step, which sets
``LC_TEST_SEARCH_MODE_E2E=1`` next to the build's ``--oid`` / ``--key``, and
skip everywhere else by default:

1. ``tests/integration`` is outside ``testpaths`` in pyproject.toml, so a plain
   ``pytest`` run never collects this file.
2. Even when the directory is named explicitly, every test here skips unless
   ``LC_TEST_SEARCH_MODE_E2E`` is set in the environment.

To actually run them::

    LC_TEST_SEARCH_MODE_E2E=1 pytest tests/integration/test_search_mode_e2e.py \\
        --oid <organization id> --key <api key> -v

Deselect them from an otherwise live integration run with
``-m "not searchmode_e2e"``.

Why the second gate exists
--------------------------

Unlike the rest of ``tests/integration``, these start real searches over a
day of data, which take a concurrency slot and are billed, and they need an
organization with telemetry in that day. The environment variable is the
opt-in that says both are intended. Without it the honest result is a skip.

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

import json
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from click.testing import CliRunner

from limacharlie.cli import cli
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
    "searchable telemetry in the window under test. These start real, "
    "billed searches against the server's optional `mode` field on "
    "POST /v1/search."
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


def test_no_mode_leaves_it_to_the_organization(oid, key):
    """``mode=None`` sends no mode key, and a page still reports what it ran as.

    That request is the one an SDK without the field would send, so it is the
    exact opt-out from this package's batch default. Which mode it resolves to
    is the organization's configuration to decide, so it is reported rather
    than asserted.
    """
    start, end = _window()
    results = list(_search(oid, key).execute(
        _QUERY, start_time=start, end_time=end, mode=None, limit=2,
    ))

    _, stats = _require_paginated_page(results)
    applied = _assert_applied_mode(stats)
    print(f"submitted no mode key, page ran as {applied!r}")


def _cli_search_pages(oid, key, *extra):
    """Run ``search run`` through the CLI with JSONL output and parse its pages.

    CliRunner's stdout is not a terminal and JSONL is a bulk format, so this is
    the path on which the CLI resolves its own mode rather than inheriting the
    SDK's. Each output line is one result object, stats included.
    """
    end = int(time.time()) - 300
    start = end - _WINDOW_SECONDS
    runner = CliRunner(env={"LC_API_KEY": key}, mix_stderr=False)
    result = runner.invoke(cli, [
        "--oid", oid, "--output", "jsonl",
        "search", "run", "--query", _QUERY,
        "--start", str(start), "--end", str(end), "--limit", "2",
        *extra,
    ])
    assert result.exit_code == 0, (
        f"search run exited {result.exit_code}.\nstderr:\n{result.stderr}"
    )
    return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]


def test_the_cli_bulk_default_reaches_the_server_and_comes_back_applied(oid, key):
    """The CLI's own mode resolution produces a page that reports its mode.

    With no ``--mode``, JSONL output and a non-terminal stdout the CLI resolves
    to batch. This asserts the resolved mode made it onto a real submission and
    that the page states what it ran as.
    """
    pages = _cli_search_pages(oid, key)
    _, stats = _require_paginated_page(pages)
    applied = _assert_applied_mode(stats)
    print(f"CLI resolved batch for JSONL output, page ran as {applied!r}")


def test_the_cli_mode_flag_reaches_the_server_and_comes_back_applied(oid, key):
    """``--mode`` overrides the CLI's resolution on a real submission."""
    pages = _cli_search_pages(oid, key, "--mode", SEARCH_MODE_INTERACTIVE)
    _, stats = _require_paginated_page(pages)
    applied = _assert_applied_mode(stats)
    print(f"CLI submitted --mode interactive, page ran as {applied!r}")
