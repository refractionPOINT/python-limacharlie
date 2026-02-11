"""Insight (IOC search, event queries) SDK for LimaCharlie v2."""

import json
from urllib.parse import quote as urlescape


class Insight:
    """IOC search, object information, and enrichment."""

    def __init__(self, org):
        self._org = org

    @property
    def client(self):
        return self._org.client

    def is_enabled(self):
        """Check if Insight (retention) is enabled."""
        data = self.client.request("GET", f"insight/{self._org.oid}")
        return bool(data.get("insight_bucket"))

    def search_ioc(self, obj_type, obj_name, case_sensitive=False, wildcards=False, limit=None):
        """Search for an IOC.

        Args:
            obj_type: IOC type (domain, ip, file_hash, file_path, etc.).
            obj_name: IOC value to search for.
            case_sensitive: Case-sensitive matching.
            wildcards: Enable wildcard matching.
            limit: Max results.

        Returns:
            dict: Search results with prevalence data.
        """
        qp = {"name": obj_name, "info": "true"}
        if case_sensitive:
            qp["case_sensitive"] = "true"
        if wildcards:
            qp["with_wildcards"] = "true"
        if limit:
            qp["limit"] = str(limit)

        return self.client.request(
            "GET",
            f"insight/{self._org.oid}/objects/{urlescape(obj_type, safe='')}",
            query_params=qp,
        )

    def batch_search(self, objects):
        """Batch IOC search.

        Args:
            objects: Dict of type -> list of values.

        Returns:
            dict: Batch results.
        """
        return self.client.request(
            "POST",
            f"insight/{self._org.oid}/objects",
            raw_body=json.dumps({"objects": objects}).encode(),
            content_type="application/json",
        )

    def get_object_timeline(self, start, end, objects, sid=None, bucketing="day"):
        """Get object timeline data.

        Args:
            start: Start time (unix seconds).
            end: End time (unix seconds).
            objects: Dict of type -> list of values.
            sid: Optional sensor filter.
            bucketing: Time bucketing ('day' or 'hour').

        Returns:
            dict: Timeline data.
        """
        qp = {"start": str(start), "end": str(end), "bucketing": bucketing, "is_compressed": "true"}
        if sid:
            qp["sid"] = str(sid)

        return self.client.request(
            "POST",
            f"insight/{self._org.oid}/objects_timeline",
            query_params=qp,
            raw_body=json.dumps({"objects": objects}).encode(),
            content_type="application/json",
        )
