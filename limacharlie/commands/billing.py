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
    client = Client(oid=ctx.obj.oid, environment=ctx.obj.environment, print_debug_fn=ctx.obj.debug_fn, debug_full_response=ctx.obj.debug_full, debug_curl=ctx.obj.debug_curl, debug_verbose=ctx.obj.debug_verbose)
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


@group.group("security")
def security() -> None:
    """Manage independent Email Security and Code Security billing.

    Rates use UTC daily high-water marks and a fixed 30-day month.
    Code also requires the separate Cloud Security base fee.
    """


_PRODUCT = click.Choice(["mail_security", "code_security"])

register_explain("billing.security.get", "Read authoritative security trial, protection, rates and costs. "
                 "Pending is not acknowledged paid coverage. Optional --from/--until are UTC dates.")
register_explain("billing.security.activate", "Explicitly accept daily billing with --accept-pricing: "
                 "Mail $1/mailbox-month; Code $0.80/repository-month plus Cloud base fee, divided by 30. "
                 "Requires billing.ctrl and user.ctrl. Read status until protection is acknowledged.")
register_explain("billing.security.stop", "Stop future paid eligibility with --confirm. "
                 "Accrued costs remain payable; trial does not reset; Code retains the Cloud base fee. "
                 "Configuration and data follow product retention policies.")


@security.command("get")
@click.argument("product", type=_PRODUCT)
@click.option("--from", "from_date", help="Inclusive UTC date YYYY-MM-DD (with --until).")
@click.option("--until", "until_date", help="Exclusive UTC date YYYY-MM-DD; at most 366 days.")
@pass_context
def security_get(ctx, product, from_date, until_date) -> None:
    """Read acknowledged status, trial limits and accrued costs."""
    try:
        data = BillingSDK(_get_org(ctx)).get_security(product, from_date=from_date, until_date=until_date)
    except ValueError as exc:
        raise click.UsageError(str(exc)) from exc
    _output(ctx, data)


@security.command("activate")
@click.argument("product", type=_PRODUCT)
@click.option("--accept-pricing", is_flag=True, required=True,
              help="Accept disclosed monthly rates divided by 30 per UTC entity-day, plus Code's Cloud fee.")
@pass_context
def security_activate(ctx, product, accept_pricing) -> None:
    """Request paid coverage after explicit pricing acceptance."""
    data = BillingSDK(_get_org(ctx)).activate_security(product, accept_pricing=accept_pricing)
    _output(ctx, data)


@security.command("stop")
@click.argument("product", type=_PRODUCT)
@click.option("--confirm", is_flag=True, required=True,
              help="Confirm paid coverage stop; accrued usage and Code's Cloud fee remain payable.")
@pass_context
def security_stop(ctx, product, confirm) -> None:
    """Request paid coverage stop without resetting the trial."""
    if not confirm:
        raise click.UsageError("--confirm is required")
    data = BillingSDK(_get_org(ctx)).stop_security(product)
    _output(ctx, data)
