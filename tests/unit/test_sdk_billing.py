"""Tests for limacharlie.sdk.billing module."""

from unittest.mock import MagicMock
import pytest

from limacharlie.sdk.billing import Billing


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
            "GET", "orgs/test-oid/billing/status",
        )
        assert result["status"] == "active"


class TestBillingGetDetails:
    def test_get_details(self, billing, mock_org):
        mock_org.client.request.return_value = {"plan": "enterprise"}
        result = billing.get_details()
        mock_org.client.request.assert_called_once_with(
            "GET", "orgs/test-oid/billing/details",
        )
        assert result["plan"] == "enterprise"


class TestBillingGetInvoiceUrl:
    def test_get_invoice_url(self, billing, mock_org):
        mock_org.client.request.return_value = {"url": "https://invoice.example.com"}
        billing.get_invoice_url(2024, 1)
        mock_org.client.request.assert_called_once_with(
            "GET", "orgs/test-oid/billing/invoice/2024/01",
            query_params=None,
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

    def test_string_year_month(self, billing, mock_org):
        mock_org.client.request.return_value = {}
        billing.get_invoice_url("2024", "7")
        path = mock_org.client.request.call_args[0][1]
        assert path == "orgs/test-oid/billing/invoice/2024/07"


class TestBillingGetPlans:
    def test_get_plans(self, billing, mock_org):
        mock_org.client.request.return_value = {"plans": []}
        result = billing.get_plans()
        mock_org.client.request.assert_called_once_with(
            "GET", "plans",
        )
        assert result == {"plans": []}


def security_quote(product="mail_security"):
    return {"version": 1, "quote_id": "a" * 64, "product": product, "currency": "usd",
            "monthly_cents": 100 if product == "mail_security" else 80, "days_per_month": 30,
            "cloud_base_monthly_cents": 0 if product == "mail_security" else 15000,
            "meter_price_id": "price_fixture_meter",
            "cloud_price_id": "" if product == "mail_security" else "price_fixture_cloud"}


class TestSecurityBilling:
    @pytest.mark.parametrize("product", ["mail_security", "code_security"])
    def test_get_status_preserves_response(self, billing, mock_org, product):
        reply = {"status": {"phase": "pending"}, "accrued_cents": 103}
        mock_org.client.request.return_value = reply
        assert billing.get_security(product) == reply
        mock_org.client.request.assert_called_once_with(
            "GET", f"orgs/test-oid/billing/security/{product}", query_params=None)

    def test_dates(self, billing, mock_org):
        billing.get_security("code_security", from_date="2026-10-01", until_date="2026-11-01")
        assert mock_org.client.request.call_args.kwargs["query_params"] == {
            "from": "2026-10-01", "until": "2026-11-01"}

    @pytest.mark.parametrize("kwargs", [
        {"from_date": "2026-10-01"}, {"until_date": "2026-10-01"},
        {"from_date": "2026-10-01", "until_date": "2026-10-01"},
        {"from_date": "2026-10-02", "until_date": "2026-10-01"},
        {"from_date": "2026-10-01", "until_date": "2028-10-01"},
        {"from_date": "20261001", "until_date": "2026-11-01"},
    ])
    def test_bad_dates_never_request(self, billing, mock_org, kwargs):
        with pytest.raises(ValueError):
            billing.get_security("mail_security", **kwargs)
        mock_org.client.request.assert_not_called()

    @pytest.mark.parametrize("accept", [False, 1, "true", None])
    def test_consent_required(self, billing, mock_org, accept):
        with pytest.raises(ValueError):
            billing.activate_security("mail_security", accept_pricing=accept, accepted_quote=security_quote())
        mock_org.client.request.assert_not_called()

    @pytest.mark.parametrize("product", ["mail_security", "code_security"])
    def test_json_consent(self, billing, mock_org, product):
        import json
        billing.activate_security(product, accept_pricing=True, accepted_quote=security_quote(product))
        args = mock_org.client.request.call_args
        assert args.args == ("POST", f"orgs/test-oid/billing/security/{product}")
        assert args.kwargs["content_type"] == "application/json"
        assert json.loads(args.kwargs["raw_body"]) == {"accept_pricing": True, "accepted_quote": security_quote(product)}

    def test_stop_no_trial_reset(self, billing, mock_org):
        billing.stop_security("code_security")
        mock_org.client.request.assert_called_once_with(
            "DELETE", "orgs/test-oid/billing/security/code_security")

    def test_invalid_product_never_request(self, billing, mock_org):
        with pytest.raises(ValueError):
            billing.stop_security("mail_security/../../quota")
        mock_org.client.request.assert_not_called()


@pytest.mark.parametrize("field", list(security_quote()))
def test_incomplete_quote_never_requests(billing, mock_org, field):
    quote = security_quote()
    del quote[field]
    with pytest.raises(ValueError):
        billing.activate_security("mail_security", accept_pricing=True, accepted_quote=quote)
    mock_org.client.request.assert_not_called()


@pytest.mark.parametrize("override", [
    {"product": "code_security"}, {"version": 2}, {"monthly_cents": True},
    {"quote_id": "invalid"}, {"cloud_base_monthly_cents": 1}, {"extra": "field"},
])
def test_invalid_quote_never_requests(billing, mock_org, override):
    with pytest.raises(ValueError):
        billing.activate_security("mail_security", accept_pricing=True,
                                  accepted_quote={**security_quote(), **override})
    mock_org.client.request.assert_not_called()
