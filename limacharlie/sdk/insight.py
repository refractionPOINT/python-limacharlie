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

    def search_ioc(self, obj_type, obj_name, info="summary", case_sensitive=True,
                   wildcards=False, limit=None, per_object=None):
        """Search for an IOC.

        Args:
            obj_type: IOC type (domain, ip, file_hash, file_path, file_name, user, service_name, package_name).
            obj_name: IOC value to search for.
            info: Type of information to query ('summary' or 'locations').
            case_sensitive: Case-sensitive matching (default True).
            wildcards: Enable wildcard matching with '%'.
            limit: Max results.
            per_object: Group results per object when wildcards are present.

        Returns:
            dict: Search results with prevalence data.
        """
        if per_object is None:
            per_object_str = "true" if (wildcards and info == "summary") else "false"
        else:
            per_object_str = "true" if per_object else "false"

        qp = {
            "name": obj_name,
            "info": info,
            "case_sensitive": "true" if case_sensitive else "false",
            "with_wildcards": "true" if wildcards else "false",
            "per_object": per_object_str,
        }
        if limit is not None:
            qp["limit"] = str(limit)

        return self.client.request(
            "GET",
            f"insight/{self._org.oid}/objects/{urlescape(obj_type, safe='')}",
            query_params=qp,
        )

    def batch_search(self, objects, case_sensitive=True):
        """Batch IOC search.

        Args:
            objects: Dict of type -> list of values.
            case_sensitive: Case-sensitive matching.

        Returns:
            dict: Batch results.
        """
        # V1 uses form-encoded params
        params = {
            "objects": json.dumps({k: list(v) for k, v in objects.items()}),
            "case_sensitive": "true" if case_sensitive else "false",
        }
        return self.client.request(
            "POST",
            f"insight/{self._org.oid}/objects",
            params=params,
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
        params = {
            "oid": self._org.oid,
            "start": str(int(start)),
            "end": str(int(end)),
            "bucketing": bucketing,
            "is_compressed": "true",
            "objects": json.dumps({k: list(v) for k, v in objects.items()}),
        }
        if sid:
            params["sid"] = str(sid)

        return self.client.request(
            "POST",
            f"insight/{self._org.oid}/objects_timeline",
            params=params,
        )

    def get_host_count_per_platform(self):
        """Get the number of hosts per platform with Insight data.

        Returns:
            dict: Platform to count mapping.
        """
        return self.client.request("GET", f"insight/{self._org.oid}/host_count")
