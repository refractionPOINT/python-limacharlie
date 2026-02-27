"""Billing commands for LimaCharlie CLI v2.

Commands for viewing billing status, details, invoice URLs, and
available plans for the organization.
"""

from __future__ import annotations

from typing import Any

import click

from ..cli import pass_context
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.billing import Billing as BillingSDK
from ..output import format_output, detect_output_format
from ..discovery import register_explain


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _output(ctx: click.Context, data: Any) -> None:
    fmt = ctx.obj.output_format or detect_output_format()
    if not ctx.obj.quiet:
        click.echo(format_output(data, fmt))


def _get_org(ctx: click.Context) -> Organization:
    client = Client(oid=ctx.obj.oid, environment=ctx.obj.environment)
    return Organization(client)


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------

@click.group("billing")
def group() -> None:
    """View billing status, details, invoices, and plans.

    Billing commands provide visibility into the organization's
    current plan, usage, costs, and invoice history.
    """


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

_EXPLAIN_STATUS = """\
Get the current billing status for the organization.  Shows the
current plan, usage summary, and billing period information.
"""
register_explain("billing.status", _EXPLAIN_STATUS)


@group.command()
@pass_context
def status(ctx) -> None:
    org = _get_org(ctx)
    billing = BillingSDK(org)
    data = billing.get_status()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# details
# ---------------------------------------------------------------------------

_EXPLAIN_DETAILS = """\
Get detailed billing information for the organization.  Includes
per-SKU usage breakdown, costs, and quota information.

SKUs include sensor-months, event volume, output volume, artifact
storage, and add-on services.
"""
register_explain("billing.details", _EXPLAIN_DETAILS)


@group.command()
@pass_context
def details(ctx) -> None:
    org = _get_org(ctx)
    billing = BillingSDK(org)
    data = billing.get_details()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# invoice
# ---------------------------------------------------------------------------

_EXPLAIN_INVOICE = """\
Get the URL for a specific monthly invoice.  Provide --year and
--month to specify the billing period.

Examples:
  limacharlie billing invoice --year 2024 --month 6
  limacharlie billing invoice --year 2025 --month 1
"""
register_explain("billing.invoice", _EXPLAIN_INVOICE)


@group.command()
@click.option("--year", required=True, type=int, help="Invoice year (e.g., 2024).")
@click.option("--month", required=True, type=int, help="Invoice month (1-12).")
@pass_context
def invoice(ctx, year, month) -> None:
    org = _get_org(ctx)
    billing = BillingSDK(org)
    data = billing.get_invoice_url(year, month)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# plans
# ---------------------------------------------------------------------------

_EXPLAIN_PLANS = """\
List all available billing plans.  Shows plan names, pricing tiers,
and included features for each plan level.
"""
register_explain("billing.plans", _EXPLAIN_PLANS)


@group.command()
@pass_context
def plans(ctx) -> None:
    org = _get_org(ctx)
    billing = BillingSDK(org)
    data = billing.get_plans()
    _output(ctx, data)
