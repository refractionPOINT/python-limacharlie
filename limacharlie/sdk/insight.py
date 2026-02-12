"""Insight (IOC search, event queries) SDK for LimaCharlie v2."""

from __future__ import annotations

import json
from typing import Any, TYPE_CHECKING
from urllib.parse import quote as urlescape

if TYPE_CHECKING:
    from .organization import Organization


class Insight:
    """IOC search, object information, and enrichment."""

    def __init__(self, org: Organization) -> None:
        self._org = org

    @property
    def client(self) -> Any:
        return self._org.client

    def is_enabled(self) -> bool:
        """Check if Insight (retention) is enabled."""
        data = self.client.request("GET", f"insight/{self._org.oid}")
        return bool(data.get("insight_bucket"))

    def search_ioc(self, obj_type: str, obj_name: str, info: str = "summary",
                   case_sensitive: bool = True, wildcards: bool = False,
                   limit: int | None = None, per_object: bool | None = None) -> dict[str, Any]:
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

        qp: dict[str, str] = {
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

    def batch_search(self, objects: dict[str, list[str]], case_sensitive: bool = True) -> dict[str, Any]:
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

    def get_object_information(self, obj_type: str, obj_name: str, info: str = "summary",
                               case_sensitive: bool = True, wildcards: bool = False,
                               limit: int | None = None) -> dict[str, Any]:
        """Get enrichment/object information for an indicator.

        This is an alias for search_ioc with a clearer name for enrichment
        use cases.  It queries the Insight data lake for detailed information
        about an observed object (IOC).

        Args:
            obj_type: Object type (domain, ip, file_hash, file_path, file_name, user, service_name, package_name).
            obj_name: Object value to look up.
            info: Type of information ('summary' or 'locations').
            case_sensitive: Case-sensitive matching (default True).
            wildcards: Enable wildcard matching with '%'.
            limit: Max results.

        Returns:
            dict: Object information/enrichment data.
        """
        return self.search_ioc(
            obj_type, obj_name,
            info=info,
            case_sensitive=case_sensitive,
            wildcards=wildcards,
            limit=limit,
        )

