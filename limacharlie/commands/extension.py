"""Extension commands for LimaCharlie CLI v2.

Commands for managing extension subscriptions.  Extensions are
third-party or LimaCharlie-provided add-ons that provide extra
detection rules, response actions, services, and integrations.
"""

import click

from ..cli import pass_context
from ..config import resolve_credentials
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.extensions import Extensions
from ..output import format_output, detect_output_format
from ..discovery import register_explain


# ---------------------------------------------------------------------------
# Explain texts
# ---------------------------------------------------------------------------

_EXPLAIN_LIST = """\
List all extensions the organization is currently subscribed to.
Extensions provide additional detection rules, response actions,
services, and integrations beyond the core LimaCharlie platform.

The output includes extension names and subscription metadata.
"""

_EXPLAIN_SUBSCRIBE = """\
Subscribe the organization to an extension by name.  Once subscribed,
the extension's rules, services, and capabilities become available
to the organization.

Example:
  limacharlie extension subscribe --name ext-zeek
"""

_EXPLAIN_UNSUBSCRIBE = """\
Unsubscribe from an extension by name.  This removes the extension's
rules and services from the organization.  Any D&R rules or configs
that depend on the extension will stop functioning.

Example:
  limacharlie extension unsubscribe --name ext-zeek
"""

register_explain("extension.list", _EXPLAIN_LIST)
register_explain("extension.subscribe", _EXPLAIN_SUBSCRIBE)
register_explain("extension.unsubscribe", _EXPLAIN_UNSUBSCRIBE)


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

@click.group("extension")
def group():
    """Manage extension subscriptions.

    Extensions are add-ons that provide extra detection rules, response
    actions, services, and integrations for the organization.
    """


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

@group.command("list")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_LIST),
    help="Show detailed explanation of this command.",
)
@pass_context
def list_extensions(ctx):
    """List subscribed extensions.

    Example:
        limacharlie extension list
    """
    org = _get_org(ctx)
    extensions = Extensions(org)
    data = extensions.list_subscribed()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# subscribe
# ---------------------------------------------------------------------------

@group.command()
@click.option("--name", required=True, help="Extension name to subscribe to.")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_SUBSCRIBE),
    help="Show detailed explanation of this command.",
)
@pass_context
def subscribe(ctx, name):
    """Subscribe to an extension.

    Example:
        limacharlie extension subscribe --name ext-zeek
    """
    org = _get_org(ctx)
    extensions = Extensions(org)
    data = extensions.subscribe(name)
    if not ctx.obj.quiet:
        click.echo(f"Subscribed to extension '{name}'.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# unsubscribe
# ---------------------------------------------------------------------------

@group.command()
@click.option("--name", required=True, help="Extension name to unsubscribe from.")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_UNSUBSCRIBE),
    help="Show detailed explanation of this command.",
)
@pass_context
def unsubscribe(ctx, name):
    """Unsubscribe from an extension.

    Example:
        limacharlie extension unsubscribe --name ext-zeek
    """
    org = _get_org(ctx)
    extensions = Extensions(org)
    data = extensions.unsubscribe(name)
    if not ctx.obj.quiet:
        click.echo(f"Unsubscribed from extension '{name}'.")
    _output(ctx, data)
