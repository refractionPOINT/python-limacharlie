"""Search/LCQL SDK for LimaCharlie v2."""

import json
import time


class Search:
    """LCQL query execution and saved query management."""

    def __init__(self, org):
        self._org = org
        self._search_url = None

    def _get_search_url(self):
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

    def validate(self, query, start_time=None, end_time=None, stream=None):
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
        body = {
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

    def estimate(self, query, start_time, end_time, stream=None):
        """Estimate billing cost for a query.

        Returns:
            dict: Billing estimate.
        """
        # Estimate uses the validate endpoint with additional parameters
        return self.validate(query, start_time, end_time, stream)

    def execute(self, query, start_time, end_time, stream=None, limit=None):
        """Execute an LCQL query and return results.

        Args:
            query: LCQL query string.
            start_time: Start time (unix seconds).
            end_time: End time (unix seconds).
            stream: Stream type ('event', 'detect', 'audit').
            limit: Max results.

        Yields:
            dict: Result records.
        """
        search_url = self._get_search_url()
        body = {
            "oid": self._org.oid,
            "query": query,
            "startTime": str(int(start_time)),
            "endTime": str(int(end_time)),
            "paginated": True,
        }
        if stream:
            body["stream"] = stream

        # Initiate search
        resp = self._org.client.request(
            "POST", "search",
            raw_body=json.dumps(body).encode(),
            content_type="application/json",
            alt_root=search_url,
        )
        query_id = resp.get("queryId", resp.get("query_id"))
        if not query_id:
            return

        count = 0
        token = None
        try:
            while True:
                qp = {}
                if token:
                    qp["token"] = token

                poll = self._org.client.request(
                    "GET", f"search/{query_id}",
                    query_params=qp or None,
                    alt_root=search_url,
                )

                for item in poll.get("results", []):
                    yield item
                    count += 1
                    if limit and count >= limit:
                        return

                if poll.get("completed", False):
                    break

                token = poll.get("nextToken")
                if not token:
                    time.sleep(1)
        finally:
            # Cancel search to clean up
            try:
                self._org.client.request("DELETE", f"search/{query_id}", alt_root=search_url)
            except Exception:
                pass
