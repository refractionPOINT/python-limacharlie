"""Billing SDK for LimaCharlie v2."""

from __future__ import annotations

import json
from datetime import date
from typing import Any, Literal, TYPE_CHECKING

SecurityProduct = Literal["mail_security", "code_security"]

if TYPE_CHECKING:
    from .organization import Organization


class Billing:
    """Billing and subscription management for a LimaCharlie organization."""

    def __init__(self, org: Organization) -> None:
        self._org = org

    @property
    def client(self) -> Any:
        """The underlying API client."""
        return self._org.client

    def get_status(self) -> dict[str, Any]:
        """Get the current billing status for the organization."""
        return self.client.request("GET", f"orgs/{self._org.oid}/billing/status")

    def get_details(self) -> dict[str, Any]:
        """Get detailed billing information for the organization."""
        return self.client.request("GET", f"orgs/{self._org.oid}/billing/details")

    def get_invoice_url(self, year: int | str, month: int | str, fmt: str | None = None) -> dict[str, Any]:
        """Get the invoice URL for a specific month.

        Args:
            year: Invoice year.
            month: Invoice month (1-12).
            fmt: Optional format (e.g. 'pdf').

        Returns:
            dict: Invoice URL data.
        """
        year = str(int(year))
        month = str(int(month)).zfill(2)
        qp: dict[str, str] = {}
        if fmt:
            qp["format"] = fmt
        return self.client.request("GET", f"orgs/{self._org.oid}/billing/invoice/{year}/{month}",
                                   query_params=qp or None)

    def get_plans(self) -> dict[str, Any]:
        """Get available billing plans."""
        return self.client.request("GET", "plans")

    def get_security(self, product: SecurityProduct, *, from_date: str | None = None,
                     until_date: str | None = None) -> dict[str, Any]:
        """Get acknowledged security product billing and trial status.

        Args:
            product: ``mail_security`` or ``code_security``.
            from_date: Inclusive UTC date, YYYY-MM-DD. Supply with until_date.
            until_date: Exclusive UTC date. Range is at most 366 days.

        Returns:
            dict: Authoritative status, rates, period, daily usage and accrued cents.

        Raises:
            ValueError: If the product or date range is invalid.
        """
        self._check_security_product(product)
        query = None
        if (from_date is None) != (until_date is None):
            raise ValueError("from_date and until_date must be provided together")
        if from_date is not None and until_date is not None:
            start, end = date.fromisoformat(from_date), date.fromisoformat(until_date)
            if start.isoformat() != from_date or end.isoformat() != until_date:
                raise ValueError("dates must be YYYY-MM-DD")
            if not 1 <= (end - start).days <= 366:
                raise ValueError("date range must contain 1..366 days")
            query = {"from": from_date, "until": until_date}
        return self.client.request("GET", f"orgs/{self._org.oid}/billing/security/{product}",
                                   query_params=query)

    def activate_security(self, product: SecurityProduct, *, accept_pricing: bool,
                          accepted_quote: dict[str, Any]) -> dict[str, Any]:
        """Request paid coverage after explicit price acceptance.

        Args:
            product: ``mail_security`` or ``code_security``.
            accept_pricing: Must be True after reviewing the disclosed rates.
            accepted_quote: Complete ``status.pricing_quote`` from get_security.
                Review it before acceptance; never substitute a freshly fetched quote.

        Returns:
            dict: Activation response. Read get_security for acknowledged protection;
                an HTTP 200 with acknowledged=False is pending, not paid coverage.
                A 409 security_quote_changed requires refetch and fresh consent;
                a 503 is retryable. Neither is automatically retried.

        Raises:
            ValueError: If the product is invalid or pricing was not accepted.
        """
        self._check_security_product(product)
        if accept_pricing is not True:
            raise ValueError("explicit pricing acceptance is required")
        self._check_security_quote(product, accepted_quote)
        return self.client.request("POST", f"orgs/{self._org.oid}/billing/security/{product}",
                                   raw_body=json.dumps({"accept_pricing": True,
                                                        "accepted_quote": accepted_quote}).encode("utf-8"),
                                   content_type="application/json")

    def stop_security(self, product: SecurityProduct) -> dict[str, Any]:
        """Request stopping future paid coverage without resetting the trial.

        Accrued usage remains payable. Code stop retains the separate Cloud fee.

        Args:
            product: ``mail_security`` or ``code_security``.

        Returns:
            dict: Stop response; get_security shows the acknowledged transition.

        Raises:
            ValueError: If the product is invalid.
        """
        self._check_security_product(product)
        return self.client.request("DELETE", f"orgs/{self._org.oid}/billing/security/{product}")

    @staticmethod
    def _check_security_product(product: str) -> None:
        if product not in ("mail_security", "code_security"):
            raise ValueError("product must be mail_security or code_security")

    @staticmethod
    def _check_security_quote(product: str, quote: dict[str, Any]) -> None:
        fields = {"version", "quote_id", "product", "currency", "monthly_cents", "days_per_month",
                  "cloud_base_monthly_cents", "meter_price_id", "cloud_price_id"}
        if not isinstance(quote, dict) or set(quote) != fields:
            raise ValueError("complete accepted_quote from status.pricing_quote is required")
        if (type(quote["version"]) is not int or quote["version"] != 1 or
                quote["product"] != product or quote["currency"] != "usd" or
                type(quote["monthly_cents"]) is not int or quote["monthly_cents"] <= 0 or
                type(quote["days_per_month"]) is not int or quote["days_per_month"] != 30 or
                type(quote["cloud_base_monthly_cents"]) is not int or quote["cloud_base_monthly_cents"] < 0 or
                not isinstance(quote["quote_id"], str) or len(quote["quote_id"]) != 64 or
                any(c not in "0123456789abcdef" for c in quote["quote_id"]) or
                not isinstance(quote["meter_price_id"], str) or not quote["meter_price_id"] or
                not isinstance(quote["cloud_price_id"], str) or
                (product == "mail_security" and (quote["cloud_price_id"] != "" or quote["cloud_base_monthly_cents"] != 0)) or
                (product == "code_security" and not quote["cloud_price_id"])):
            raise ValueError("invalid accepted_quote; review status.pricing_quote")
