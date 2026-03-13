"""Search/LCQL SDK for LimaCharlie v2.

Provides LCQL query execution, validation, and saved query management.
All search errors include query_id, region, and oid for troubleshooting.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Generator
from typing import Any, TYPE_CHECKING

from ..errors import SearchError

if TYPE_CHECKING:
    from .organization import Organization


# Pattern to extract region from search URL, e.g. "search-prod-usa.limacharlie.io"
_REGION_PATTERN = re.compile(r"search-([a-z0-9-]+)\.")


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
        """Extract region from the search URL for error context.

        Returns:
            Region string (e.g. 'prod-usa') or None if not extractable.
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

    def execute(self, query: str, start_time: int, end_time: int,
                stream: str | None = None, limit: int | None = None) -> Generator[dict[str, Any], None, None]:
        """Execute an LCQL query and return results.

        Args:
            query: LCQL query string.
            start_time: Start time (unix seconds).
            end_time: End time (unix seconds).
            stream: Stream type ('event', 'detect', 'audit').
            limit: Max results.

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
                f"Failed to initiate search: {exc}",
                region=region,
                oid=oid,
            ) from exc

        # Check for error in initiation response
        if resp.get("error"):
            raise SearchError(
                f"Failed to initiate search: {resp['error']}",
                region=region,
                oid=oid,
            )

        query_id = resp.get("queryId", resp.get("query_id"))
        if not query_id:
            raise SearchError(
                "Failed to initiate search: missing queryId in response",
                region=region,
                oid=oid,
            )

        count = 0
        token: str | None = None
        try:
            while True:
                qp: dict[str, str] = {}
                if token:
                    qp["token"] = token

                poll = self._org.client.request(
                    "GET", f"search/{query_id}",
                    query_params=qp or None,
                    alt_root=search_url,
                )

                # Check for error in poll response
                if poll.get("error"):
                    raise SearchError(
                        f"Search query failed: {poll['error']}",
                        query_id=query_id,
                        region=region,
                        oid=oid,
                    )

                # The nextToken for pagination lives inside each
                # SearchResult, not at the top level of SearchResponse.
                next_token: str | None = None
                for item in poll.get("results", []):
                    if item.get("nextToken"):
                        next_token = item["nextToken"]
                    yield item
                    count += 1
                    if limit and count >= limit:
                        return

                if poll.get("completed", False):
                    if next_token:
                        # More pages available - use the token to
                        # fetch the next page (may trigger a subquery).
                        token = next_token
                    else:
                        break
                else:
                    # Page still processing, poll again after a delay.
                    poll_ms = poll.get("nextPollInMs", 1000)
                    time.sleep(max(poll_ms / 1000, 0.5))
        except SearchError:
            raise
        except Exception as exc:
            raise SearchError(
                f"Search failed: {exc}",
                query_id=query_id,
                region=region,
                oid=oid,
            ) from exc
        finally:
            # Cancel search to clean up
            try:
                self._org.client.request("DELETE", f"search/{query_id}", alt_root=search_url)
            except Exception:
                pass
