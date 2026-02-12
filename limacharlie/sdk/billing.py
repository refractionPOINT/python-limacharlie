"""Billing SDK for LimaCharlie v2."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .organization import Organization

BILLING_URL = "https://billing.limacharlie.io/"


class Billing:
    def __init__(self, org: Organization) -> None:
        self._org = org

    @property
    def client(self) -> Any:
        return self._org.client

    def get_status(self) -> dict[str, Any]:
        return self.client.request("GET", f"orgs/{self._org.oid}/status", alt_root=BILLING_URL)

    def get_details(self) -> dict[str, Any]:
        return self.client.request("GET", f"orgs/{self._org.oid}/details", alt_root=BILLING_URL)

    def get_invoice_url(self, year: int | str, month: int | str, fmt: str | None = None) -> dict[str, Any]:
        year = str(int(year))
        month = str(int(month)).zfill(2)
        qp: dict[str, str] = {}
        if fmt:
            qp["format"] = fmt
        return self.client.request("GET", f"orgs/{self._org.oid}/invoice_url/{year}/{month}",
                                   alt_root=BILLING_URL, query_params=qp or None)

    def get_plans(self) -> dict[str, Any]:
        return self.client.request("GET", "user/self/plans", alt_root=BILLING_URL)

    def get_sku_definitions(self) -> dict[str, Any]:
        return self.client.request("GET", f"orgs/{self._org.oid}/sku-definitions", alt_root=BILLING_URL)
