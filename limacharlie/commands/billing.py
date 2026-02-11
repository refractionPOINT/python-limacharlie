"""Billing commands for LimaCharlie CLI v2.

Commands for viewing billing status, details, invoice URLs, and
available plans for the organization.
"""

import click

from ..cli import pass_context
from ..config import resolve_credentials
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.billing import Billing as BillingSDK
from ..output import format_output, detect_output_format
from ..discovery import register_explain


# ---------------------------------------------------------------------------
# Explain texts
# ---------------------------------------------------------------------------

_EXPLAIN_STATUS = """\
Get the current billing status for the organization.  Shows the
current plan, usage summary, and billing period information.
"""

_EXPLAIN_DETAILS = """\
Get detailed billing information for the organization.  Includes
per-SKU usage breakdown, costs, and quota information.
"""

_EXPLAIN_INVOICE = """\
Get the URL for a specific monthly invoice.  Provide --year and
--month to specify the billing period.

Examples:
  limacharlie billing invoice --year 2024 --month 6
  limacharlie billing invoice --year 2025 --month 1
"""

_EXPLAIN_PLANS = """\
List all available billing plans.  Shows plan names, pricing tiers,
and included features for each plan level.
"""

register_explain("billing.status", _EXPLAIN_STATUS)
register_explain("billing.details", _EXPLAIN_DETAILS)
register_explain("billing.invoice", _EXPLAIN_INVOICE)
register_explain("billing.plans", _EXPLAIN_PLANS)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_explain_callback(text):
    def callback(ctx, param, value):
        if value:
            click.echo(text.strip())
            ctx.exit()
    return callback


def _output(ctx, data):
    fmt = ctx.obj.output_format or detect_output_format()
    if not ctx.obj.quiet:
        click.echo(format_output(data, fmt))


def _get_org(ctx):
    creds = resolve_credentials(oid=ctx.obj.oid, environment=ctx.obj.environment)
    client = Client(oid=creds["oid"], api_key=creds.get("api_key"), uid=creds.get("uid"))
    return Organization(client)


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------

@click.group("billing")
def group():
    """View billing status, details, invoices, and plans.

    Billing commands provide visibility into the organization's
    current plan, usage, costs, and invoice history.
    """


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

@group.command()
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_STATUS),
    help="Show detailed explanation of this command.",
)
@pass_context
def status(ctx):
    """Get billing status.

    Example:
        limacharlie billing status
    """
    org = _get_org(ctx)
    billing = BillingSDK(org)
    data = billing.get_status()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# details
# ---------------------------------------------------------------------------

@group.command()
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_DETAILS),
    help="Show detailed explanation of this command.",
)
@pass_context
def details(ctx):
    """Get detailed billing information.

    Example:
        limacharlie billing details
    """
    org = _get_org(ctx)
    billing = BillingSDK(org)
    data = billing.get_details()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# invoice
# ---------------------------------------------------------------------------

@group.command()
@click.option("--year", required=True, type=int, help="Invoice year (e.g., 2024).")
@click.option("--month", required=True, type=int, help="Invoice month (1-12).")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_INVOICE),
    help="Show detailed explanation of this command.",
)
@pass_context
def invoice(ctx, year, month):
    """Get invoice URL for a specific month.

    Example:
        limacharlie billing invoice --year 2024 --month 6
    """
    org = _get_org(ctx)
    billing = BillingSDK(org)
    data = billing.get_invoice_url(year, month)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# plans
# ---------------------------------------------------------------------------

@group.command()
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_PLANS),
    help="Show detailed explanation of this command.",
)
@pass_context
def plans(ctx):
    """List available billing plans.

    Example:
        limacharlie billing plans
    """
    org = _get_org(ctx)
    billing = BillingSDK(org)
    data = billing.get_plans()
    _output(ctx, data)
