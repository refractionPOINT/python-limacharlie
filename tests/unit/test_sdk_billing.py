"""Tests for limacharlie.sdk.billing module."""

from unittest.mock import MagicMock
import pytest

from limacharlie.sdk.billing import Billing, BILLING_URL


@pytest.fixture
def mock_org():
    org = MagicMock()
    org.oid = "test-oid"
    org.client = MagicMock()
    return org


@pytest.fixture
def billing(mock_org):
    return Billing(mock_org)


class TestBillingGetStatus:
    def test_get_status(self, billing, mock_org):
        mock_org.client.request.return_value = {"status": "active"}
        result = billing.get_status()
        mock_org.client.request.assert_called_once_with(
            "GET", "orgs/test-oid/status", alt_root=BILLING_URL,
        )
        assert result["status"] == "active"


class TestBillingGetDetails:
    def test_get_details(self, billing, mock_org):
        mock_org.client.request.return_value = {"plan": "enterprise"}
        result = billing.get_details()
        mock_org.client.request.assert_called_once_with(
            "GET", "orgs/test-oid/details", alt_root=BILLING_URL,
        )
        assert result["plan"] == "enterprise"


class TestBillingGetInvoiceUrl:
    def test_get_invoice_url(self, billing, mock_org):
        mock_org.client.request.return_value = {"url": "https://invoice.example.com"}
        billing.get_invoice_url(2024, 1)
        mock_org.client.request.assert_called_once_with(
            "GET", "orgs/test-oid/invoice_url/2024/01",
            alt_root=BILLING_URL, query_params=None,
        )

    def test_month_zero_padded(self, billing, mock_org):
        mock_org.client.request.return_value = {}
        billing.get_invoice_url(2024, 3)
        path = mock_org.client.request.call_args[0][1]
        assert path.endswith("/2024/03")

    def test_double_digit_month(self, billing, mock_org):
        mock_org.client.request.return_value = {}
        billing.get_invoice_url(2024, 12)
        path = mock_org.client.request.call_args[0][1]
        assert path.endswith("/2024/12")

    def test_with_format_param(self, billing, mock_org):
        mock_org.client.request.return_value = {}
        billing.get_invoice_url(2024, 6, fmt="pdf")
        call_args = mock_org.client.request.call_args
        assert call_args[1]["query_params"] == {"format": "pdf"}
        assert call_args[1]["alt_root"] == BILLING_URL

    def test_string_year_month(self, billing, mock_org):
        mock_org.client.request.return_value = {}
        billing.get_invoice_url("2024", "7")
        path = mock_org.client.request.call_args[0][1]
        assert path == "orgs/test-oid/invoice_url/2024/07"


class TestBillingGetPlans:
    def test_get_plans(self, billing, mock_org):
        mock_org.client.request.return_value = {"plans": []}
        result = billing.get_plans()
        mock_org.client.request.assert_called_once_with(
            "GET", "user/self/plans", alt_root=BILLING_URL,
        )
        assert result == {"plans": []}

    def test_billing_url_constant(self):
        assert BILLING_URL == "https://billing.limacharlie.io/"
