"""Search/LCQL SDK for LimaCharlie v2.

Provides LCQL query execution, validation, and saved query management.
All search errors include query_id, region, and oid for troubleshooting.
"""

from __future__ import annotations

import json
import re
import ssl
import time
from collections.abc import Callable, Generator
from typing import Any, TYPE_CHECKING

from ..errors import (
    ApiError,
    AuthenticationError,
    LimaCharlieError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    SearchError,
    ValidationError,
)

if TYPE_CHECKING:
    from .organization import Organization


def _exc_message(exc: Exception) -> str:
    """Extract a clean message from an exception.

    For LimaCharlieError subclasses, uses raw_message to avoid
    duplicating the suggestion text when wrapping in SearchError.
    """
    if isinstance(exc, LimaCharlieError):
        return exc.raw_message
    return str(exc)


# Transient HTTP status codes that are safe to retry on poll requests.
# These indicate server-side or infrastructure issues, not client errors.
_TRANSIENT_STATUS_CODES = frozenset({500, 502, 503, 504})

# Maximum backoff delay in seconds for poll retries.
_MAX_BACKOFF_SECONDS = 30


def _is_transient_poll_error(exc: Exception) -> bool:
    """Classify whether a poll exception is transient and safe to retry.

    Retryable: ApiError with 5xx status, ConnectionError, TimeoutError,
    OSError (network errors), ssl.SSLError.

    NOT retryable: AuthenticationError (401), RateLimitError (429),
    NotFoundError (404), ValidationError (422), PermissionDeniedError (403),
    or any other non-transient error.

    Args:
        exc: The exception raised during a poll request.

    Returns:
        True if the error is transient and the poll should be retried.
    """
    # Non-retryable LimaCharlie error types - these are permanent failures.
    if isinstance(exc, (AuthenticationError, RateLimitError, NotFoundError,
                        ValidationError, PermissionDeniedError)):
        return False

    # ApiError with a transient HTTP status code.
    if isinstance(exc, ApiError):
        return exc.status_code in _TRANSIENT_STATUS_CODES

    # Network-level errors are transient.
    if isinstance(exc, (ConnectionError, TimeoutError, ssl.SSLError)):
        return True

    # OSError covers low-level socket errors (ECONNRESET, EPIPE, etc.)
    # but we exclude subclasses that are not network-related.
    if isinstance(exc, OSError) and not isinstance(exc, (FileNotFoundError,
                                                          PermissionError,
                                                          IsADirectoryError)):
        return True

    return False


# Pattern to extract region identifier from search URL.
# Real URLs look like: https://9157798c50af372c.replay-search.limacharlie.io/v1/search/
# The region identifier is the hex hash prefix before ".replay-search".
_REGION_PATTERN = re.compile(r"(?:https?://)?([a-f0-9]+)\.replay-search\.")


class Search:
    """LCQL query execution and saved query management."""

    def __init__(self, org: Organization) -> None:
        self._org = org
        self._search_url: str | None = None

    def _get_search_url(self) -> str:
        if self._search_url is None:
            urls = self._org.get_urls()
            search_url = urls.get("search", urls.get("search_api", ""))
            # Add https:// prefix if needed
            if search_url and not search_url.startswith("http://") and not search_url.startswith("https://"):
                search_url = "https://" + search_url
            # Add /v1 API version suffix
            search_url = search_url.rstrip("/") + "/v1"
            self._search_url = search_url
        return self._search_url

    def _extract_region(self) -> str | None:
        """Extract region identifier from the search URL for error context.

        Real search URLs look like:
            https://9157798c50af372c.replay-search.limacharlie.io/v1/search/

        The region identifier is the hex hash prefix (e.g. '9157798c50af372c').

        Returns:
            Region identifier string or None if not extractable.
        """
        url = self._get_search_url()
        match = _REGION_PATTERN.search(url)
        return match.group(1) if match else None

    def validate(self, query: str, start_time: int | None = None, end_time: int | None = None,
                 stream: str | None = None) -> dict[str, Any]:
        """Validate LCQL syntax.

        Args:
            query: LCQL query string.
            start_time: Optional start time (unix seconds).
            end_time: Optional end time (unix seconds).
            stream: Optional stream type.

        Returns:
            dict: Validation result.
        """
        search_url = self._get_search_url()
        if start_time is None:
            start_time = int(time.time()) - 86400
        if end_time is None:
            end_time = int(time.time())
        body: dict[str, Any] = {
            "oid": self._org.oid,
            "query": query,
            "startTime": str(int(start_time)),
            "endTime": str(int(end_time)),
        }
        if stream:
            body["stream"] = stream
        return self._org.client.request(
            "POST", "search/validate",
            raw_body=json.dumps(body).encode(),
            content_type="application/json",
            alt_root=search_url,
        )

    def estimate(self, query: str, start_time: int, end_time: int,
                 stream: str | None = None) -> dict[str, Any]:
        """Estimate billing cost for a query.

        Returns:
            dict: Billing estimate.
        """
        # Estimate uses the validate endpoint with additional parameters
        return self.validate(query, start_time, end_time, stream)

    def _poll_with_retry(
        self,
        query_id: str,
        search_url: str,
        query_params: dict[str, str] | None,
        max_retries: int = 3,
        progress_fn: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        """Execute a single poll GET request with retry on transient errors.

        Uses exponential backoff (2^attempt seconds, capped at 30s) between
        retries. Only retries on transient errors as classified by
        ``_is_transient_poll_error`` - permanent errors (auth, validation,
        rate limit) are raised immediately.

        Poll responses containing an ``"error"`` key in the body are NOT
        retried - these are search-engine errors (e.g. "context canceled"),
        not transport errors.

        Args:
            query_id: Active search query ID.
            search_url: Base search API URL.
            query_params: Query parameters for the GET request (e.g. pagination token).
            max_retries: Maximum number of retry attempts (default 3).
            progress_fn: Optional callback for retry status messages.

        Returns:
            The poll response dict.

        Raises:
            The original exception if all retries are exhausted or the
            error is not transient.
        """
        last_exc: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                return self._org.client.request(
                    "GET", f"search/{query_id}",
                    query_params=query_params,
                    alt_root=search_url,
                )
            except Exception as exc:
                if attempt >= max_retries or not _is_transient_poll_error(exc):
                    raise
                last_exc = exc
                backoff = min(2 ** attempt, _MAX_BACKOFF_SECONDS)
                if progress_fn:
                    progress_fn(
                        f"Retrying poll (attempt {attempt + 2}/{max_retries + 1}, "
                        f"waiting {backoff}s)..."
                    )
                time.sleep(backoff)

        # Should not reach here, but satisfy type checker.
        raise last_exc  # type: ignore[misc]

    def execute(
        self,
        query: str,
        start_time: int,
        end_time: int,
        stream: str | None = None,
        limit: int | None = None,
        progress_fn: Callable[[str], None] | None = None,
        poll_max_retries: int = 3,
        start_token: str | None = None,
        start_page: int = 1,
    ) -> Generator[dict[str, Any], None, None]:
        """Execute an LCQL query and return results.

        Args:
            query: LCQL query string.
            start_time: Start time (unix seconds).
            end_time: End time (unix seconds).
            stream: Stream type ('event', 'detect', 'audit').
            limit: Max results.
            progress_fn: Optional callback for progress messages (e.g.,
                "Running search...", "Fetching page 2...").  Called with
                a human-readable status string.  Intended for CLI progress
                output to stderr in interactive mode.
            poll_max_retries: Maximum number of retries for each individual
                poll request on transient errors (default 3). Set to 0 to
                disable retries.
            start_token: Resume pagination from this token. When provided,
                the first poll request immediately uses this token to skip
                ahead to the page following the one that produced it.
                Used by checkpoint/resume to avoid re-fetching already-
                fetched pages.
            start_page: Starting page number for progress display (default 1).
                Used with start_token to show accurate page numbers when
                resuming mid-search.

        Yields:
            dict: Result records.

        Raises:
            SearchError: On search failure. Includes query_id, region, and oid
                for troubleshooting.
        """
        search_url = self._get_search_url()
        oid = self._org.oid
        region = self._extract_region()
        body: dict[str, Any] = {
            "oid": oid,
            "query": query,
            "startTime": str(int(start_time)),
            "endTime": str(int(end_time)),
            "paginated": True,
        }
        if stream:
            body["stream"] = stream

        # Initiate search - wrap transport exceptions so the caller always
        # gets a SearchError with region/oid context for troubleshooting.
        try:
            resp = self._org.client.request(
                "POST", "search",
                raw_body=json.dumps(body).encode(),
                content_type="application/json",
                alt_root=search_url,
            )
        except SearchError:
            raise
        except Exception as exc:
            raise SearchError(
                f"Failed to initiate search: {_exc_message(exc)}",
                region=region,
                oid=oid,
                query=query,
            ) from exc

        # Check for error in initiation response
        if resp.get("error"):
            raise SearchError(
                f"Failed to initiate search: {resp['error']}",
                region=region,
                oid=oid,
                query=query,
            )

        query_id = resp.get("queryId", resp.get("query_id"))
        if not query_id:
            raise SearchError(
                "Failed to initiate search: missing queryId in response",
                region=region,
                oid=oid,
                query=query,
            )

        if progress_fn:
            progress_fn(f"Running search... query_id: {query_id}")

        count = 0
        page = start_page
        total_events = 0
        start_ts = time.monotonic()
        token: str | None = start_token
        _interrupted = False

        if start_token and progress_fn:
            tok_display = "..." + start_token[-12:] if len(start_token) > 16 else start_token
            progress_fn(f"Resuming from page {page} (token={tok_display})")
        try:
            while True:
                qp: dict[str, str] = {}
                if token:
                    qp["token"] = token

                poll = self._poll_with_retry(
                    query_id, search_url,
                    query_params=qp or None,
                    max_retries=poll_max_retries,
                    progress_fn=progress_fn,
                )

                # Check for error in poll response
                if poll.get("error"):
                    raise SearchError(
                        f"Search query failed: {poll['error']}",
                        query_id=query_id,
                        region=region,
                        oid=oid,
                        query=query,
                    )

                # The nextToken for pagination lives inside each
                # SearchResult, not at the top level of SearchResponse.
                next_token: str | None = None
                for item in poll.get("results", []):
                    if item.get("nextToken"):
                        next_token = item["nextToken"]
                    if item.get("type") == "events":
                        total_events += len(item.get("rows") or [])
                    yield item
                    count += 1
                    if limit and count >= limit:
                        return

                if poll.get("completed", False):
                    if next_token:
                        # More pages available - use the token to
                        # fetch the next page (may trigger a subquery).
                        token = next_token
                        page += 1
                        if progress_fn:
                            elapsed = time.monotonic() - start_ts
                            # Show last 12 chars of token (the prefix is
                            # always the same, the suffix varies).
                            tok_display = "..." + next_token[-12:] if len(next_token) > 16 else next_token
                            progress_fn(
                                f"Fetching page {page}... "
                                f"({total_events:,} events, {elapsed:.0f}s elapsed, "
                                f"token={tok_display})"
                            )
                    else:
                        break
                else:
                    # Page still processing, poll again after a delay.
                    poll_ms = poll.get("nextPollInMs", 1000)
                    if progress_fn:
                        elapsed = time.monotonic() - start_ts
                        progress_fn(
                            f"Waiting for results... "
                            f"(page {page}, {total_events:,} events, {elapsed:.0f}s elapsed)"
                        )
                    time.sleep(max(poll_ms / 1000, 0.5))
        except KeyboardInterrupt:
            _interrupted = True
            raise
        except SearchError:
            raise
        except Exception as exc:
            raise SearchError(
                f"Search failed: {_exc_message(exc)}",
                query_id=query_id,
                region=region,
                oid=oid,
                query=query,
            ) from exc
        finally:
            # Cancel search on server to free resources.  Runs on
            # normal completion, errors, and Ctrl+C (KeyboardInterrupt).
            self._cancel_query(query_id, search_url, progress_fn if _interrupted else None)

    def _cancel_query(
        self,
        query_id: str,
        search_url: str,
        progress_fn: Callable[[str], None] | None = None,
    ) -> None:
        """Cancel a search query on the server.

        Always called in the finally block of execute() to clean up
        server resources.  On keyboard interrupt, prints a cancel
        message via progress_fn.
        """
        if progress_fn:
            progress_fn(f"Canceling search query {query_id} on server...")
        try:
            self._org.client.request("DELETE", f"search/{query_id}", alt_root=search_url)
        except Exception:
            pass

    # -----------------------------------------------------------------
    # Open queries
    # -----------------------------------------------------------------

    def list_open_queries(
        self,
        state: str = "all",
        limit: int | None = None,
        offset: int | None = None,
    ) -> dict[str, Any]:
        """List the searches this organization currently has open.

        A search is "open" from the moment it is submitted until it finishes,
        is cancelled, or its state expires.  That is not the same population
        as the searches consuming the organization's concurrency limit: a
        paginated search sitting between pages is open and resumable but
        holds no slot.  The response reports both numbers separately, so
        ``slotsHeld`` (not ``count``) is what ``limit`` applies to.

        This is the endpoint to reach for when a search is refused with
        "maximum concurrent queries reached": it names what is holding the
        slots, how long each has been running, and how much each has
        scanned, so the query worth cancelling is identifiable.

        Args:
            state: Which searches to return.  ``"all"`` (default),
                ``"executing"`` (a page is running or a slot is held and
                the work has not reached a worker yet) or ``"idle"``
                (open and resumable, consuming no slot).
            limit: Page size.  Server default is 50, clamped to 200.
            offset: Offset into the listing, newest first.

        Returns:
            dict with:
              ``oid``, ``limit`` (the organization's concurrency limit),
              ``slotsHeld``, ``count``, ``truncated``, and ``queries``.

            Each entry in ``queries`` carries ``queryId``, ``state``,
            ``holdsSlot``, the query text and time range as submitted,
            ``submittedBy`` / ``userAgent``, ``submittedAt``, timing
            (``startedAt``, ``runningForMs``, ``lastActivityAt``),
            progress (``pagesCompleted``, ``batchesCompleted``,
            ``batchesInScope``, ``progressPercent``, ``eventsScanned``,
            ``billedEvents``), and the two expiries ``slotExpiresAt`` and
            ``resumableUntil``.

            ``progressPercent`` is absent when the scope estimate was
            unavailable, which means progress cannot be computed rather
            than that nothing has been done.  Progress advances at page
            boundaries, so a search that returns everything in one page -
            any aggregation, which does not paginate - reports 0 for its
            whole life.

            ``state`` is ``"unknown"`` with a null ``holdsSlot`` when the
            deployment is not tracking slots per query; the field says so
            rather than guessing.

        Raises:
            SearchError: if the listing cannot be retrieved.
        """
        if state not in ("all", "executing", "idle"):
            raise ValidationError(
                f"state must be one of all, executing, idle (got {state!r})"
            )

        query_params: dict[str, str] = {"state": state}
        if limit is not None:
            query_params["limit"] = str(int(limit))
        if offset is not None:
            query_params["offset"] = str(int(offset))

        try:
            return self._org.client.request(
                "GET", f"search/{self._org.oid}/queries",
                query_params=query_params,
                alt_root=self._get_search_url(),
            )
        except (SearchError, ValidationError):
            raise
        except Exception as exc:
            raise SearchError(
                f"Failed to list open queries: {_exc_message(exc)}",
                region=self._extract_region(),
                oid=self._org.oid,
            ) from exc

    def iter_open_queries(
        self,
        state: str = "all",
        page_size: int = 200,
    ) -> Generator[dict[str, Any], None, None]:
        """Yield every open search, walking the listing page by page.

        Pages by offset against a listing ordered newest first.  An
        organization can open and finish searches while this iterates, so
        treat the result as a sample rather than a transaction; the
        endpoint reports ``count`` if an exact total at one instant is what
        is needed.

        Args:
            state: Same filter as :meth:`list_open_queries`.
            page_size: Rows per request.  Clamped to 200 by the server.

        Yields:
            dict: One open search per entry, same shape as the ``queries``
            entries of :meth:`list_open_queries`.
        """
        offset = 0
        seen: set[str] = set()
        while True:
            page = self.list_open_queries(state=state, limit=page_size, offset=offset)
            rows = page.get("queries") or []
            for row in rows:
                # The filter is applied after paging, so a page can come back
                # empty while more entries exist; de-duplicate by id because
                # entries leaving the index mid-walk shift later offsets back.
                query_id = row.get("queryId")
                if query_id and query_id in seen:
                    continue
                if query_id:
                    seen.add(query_id)
                yield row

            # truncated describes the index page rather than the filtered
            # rows, so it - not len(rows) - is what says whether to continue.
            if not page.get("truncated"):
                return
            offset += page_size

    def get_limits(self) -> dict[str, Any]:
        """Report this organization's resolved search limits.

        Every limit here is otherwise discoverable only by hitting it: a
        refusal for concurrency arrives with no indication of what the cap
        was, and a paginated search stops being resumable with no way to
        have known the window.  Read this once and size the client's
        behaviour to it - how many searches to run at a time, how long a
        user may leave one paused, whether to offer the open-query view.

        Two conventions in the response are load-bearing:

        * A limit that is not enforced is ``None``, never ``0``.  Several
          of these use zero internally as the sentinel for "disabled"; in
          a document of limits, ``0`` would read as "zero allowed".
        * Values are the ones actually applied, not raw configuration.
          ``pageResultsForSeconds`` in particular reflects the resolved
          retention, which can differ from what is configured.

        Returns:
            dict with:
              ``oid``, and the groups ``concurrency``, ``pagination``,
              ``retention``, ``execution``, ``request`` and
              ``capabilities``.

            ``concurrency.maxConcurrentQueries`` is how many searches may
            be *executing* at once; a search parked between pages consumes
            nothing, so this is not a cap on how many may be open.

            ``pagination`` carries ``resultsPerPage``,
            ``maxPageDurationSeconds`` (reaching it is normal for a broad
            query and does not mean the search failed) and
            ``maxCursorBytes``.

            ``retention`` carries ``resumableForSeconds`` - measured from
            submission and never extended by activity - and
            ``pageResultsForSeconds``.  The latter can be shorter, in which
            case re-reading an older page recomputes it rather than
            failing, so it is a latency characteristic and not a deadline.

            ``execution`` carries ``maxQueryDurationSeconds``,
            ``maxAggregationDurationSeconds`` and ``maxResponseBytes``,
            each ``None`` when not enforced.

            ``capabilities.openQueryListing`` says whether
            :meth:`list_open_queries` reports searches that are open but
            idle.  When false it can still be called, but only sees
            searches currently holding a slot.

            Fields are additive: ignore ones you do not recognise, and
            treat an absent field as "not applicable to this deployment"
            rather than as zero.

        Raises:
            SearchError: if the limits cannot be retrieved.
        """
        try:
            return self._org.client.request(
                "GET", f"search/{self._org.oid}/limits",
                alt_root=self._get_search_url(),
            )
        except (SearchError, ValidationError):
            raise
        except Exception as exc:
            raise SearchError(
                f"Failed to get search limits: {_exc_message(exc)}",
                region=self._extract_region(),
                oid=self._org.oid,
            ) from exc
