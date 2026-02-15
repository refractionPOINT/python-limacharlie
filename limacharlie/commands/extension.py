"""Extension commands for LimaCharlie CLI v2.

Commands for managing extension subscriptions.  Extensions are
third-party or LimaCharlie-provided add-ons that provide extra
detection rules, response actions, services, and integrations.
"""

from __future__ import annotations

import json
import sys
from typing import Any

import click
import yaml

from ..cli import pass_context
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.extensions import Extensions
from ..sdk.hive import Hive, HiveRecord
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

_EXPLAIN_LIST_AVAILABLE = """\
List all available extensions in the LimaCharlie marketplace.  This
includes both subscribed and unsubscribed extensions.

Example:
  limacharlie extension list-available
"""

_EXPLAIN_REKEY = """\
Rotate the API key for an extension subscription.  This generates
a new key and invalidates the previous one.

Example:
  limacharlie extension rekey --name ext-zeek
"""

_EXPLAIN_SCHEMA = """\
Get the configuration schema for an extension.  The schema describes
the expected configuration format and available options.

Example:
  limacharlie extension schema --name ext-zeek
"""

_EXPLAIN_REQUEST = """\
Call an extension by invoking an action.  You can optionally pass
a JSON data payload with --data.

Example:
  limacharlie extension request --name ext-zeek --action status
  limacharlie extension request --name my-ext --action run --data '{"key": "value"}'
"""

_EXPLAIN_CONFIG_LIST = """\
List all extension configurations stored in the extension_config hive.

Example:
  limacharlie extension config-list
"""

_EXPLAIN_CONFIG_GET = """\
Get a specific extension configuration by name from the
extension_config hive.

Example:
  limacharlie extension config-get --name my-extension
"""

_EXPLAIN_CONFIG_SET = """\
Create or update an extension configuration in the extension_config
hive.  Provide data via --input-file (JSON/YAML) or stdin.

Example:
  limacharlie extension config-set --name my-extension --input-file config.yaml
"""

_EXPLAIN_CONFIG_DELETE = """\
Delete an extension configuration from the extension_config hive.
Requires --confirm for safety.

Example:
  limacharlie extension config-delete --name my-extension --confirm
"""

register_explain("extension.list", _EXPLAIN_LIST)
register_explain("extension.subscribe", _EXPLAIN_SUBSCRIBE)
register_explain("extension.unsubscribe", _EXPLAIN_UNSUBSCRIBE)
register_explain("extension.list-available", _EXPLAIN_LIST_AVAILABLE)
register_explain("extension.rekey", _EXPLAIN_REKEY)
register_explain("extension.schema", _EXPLAIN_SCHEMA)
register_explain("extension.request", _EXPLAIN_REQUEST)
register_explain("extension.config-list", _EXPLAIN_CONFIG_LIST)
register_explain("extension.config-get", _EXPLAIN_CONFIG_GET)
register_explain("extension.config-set", _EXPLAIN_CONFIG_SET)
register_explain("extension.config-delete", _EXPLAIN_CONFIG_DELETE)


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

@click.group("extension")
def group() -> None:
    """Manage extension subscriptions.

    Extensions are add-ons that provide extra detection rules, response
    actions, services, and integrations for the organization.
    """


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

@group.command("list")
@pass_context
def list_extensions(ctx) -> None:
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
@pass_context
def subscribe(ctx, name) -> None:
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
@pass_context
def unsubscribe(ctx, name) -> None:
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


# ---------------------------------------------------------------------------
# list-available
# ---------------------------------------------------------------------------

@group.command("list-available")
@pass_context
def list_available(ctx) -> None:
    """List all available extensions.

    Example:
        limacharlie extension list-available
    """
    org = _get_org(ctx)
    extensions = Extensions(org)
    data = extensions.get_all()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# rekey
# ---------------------------------------------------------------------------

@group.command()
@click.option("--name", required=True, help="Extension name to rekey.")
@pass_context
def rekey(ctx, name) -> None:
    """Rotate API key for an extension.

    Example:
        limacharlie extension rekey --name ext-zeek
    """
    org = _get_org(ctx)
    extensions = Extensions(org)
    data = extensions.rekey(name)
    if not ctx.obj.quiet:
        click.echo(f"Extension '{name}' rekeyed.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# schema
# ---------------------------------------------------------------------------

@group.command()
@click.option("--name", required=True, help="Extension name.")
@pass_context
def schema(ctx, name) -> None:
    """Get extension configuration schema.

    Example:
        limacharlie extension schema --name ext-zeek
    """
    org = _get_org(ctx)
    extensions = Extensions(org)
    data = extensions.get_schema(name)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# request
# ---------------------------------------------------------------------------

@group.command()
@click.option("--name", required=True, help="Extension name.")
@click.option("--action", required=True, help="Action to invoke.")
@click.option("--data", default=None, help="JSON string with request data.")
@pass_context
def request(ctx, name, action, data) -> None:
    """Call an extension action.

    Examples:
        limacharlie extension request --name ext-zeek --action status
        limacharlie extension request --name my-ext --action run \\
            --data '{"key": "value"}'
    """
    parsed_data = None
    if data is not None:
        parsed_data = json.loads(data)
    org = _get_org(ctx)
    extensions = Extensions(org)
    result = extensions.request(name, action, data=parsed_data)
    _output(ctx, result)


# ---------------------------------------------------------------------------
# config-list
# ---------------------------------------------------------------------------

@group.command("config-list")
@pass_context
def config_list(ctx) -> None:
    """List extension configurations.

    Example:
        limacharlie extension config-list
    """
    org = _get_org(ctx)
    hive = Hive(org, "extension_config")
    records = hive.list()
    data = {name: rec.to_dict() for name, rec in records.items()}
    _output(ctx, data)


# ---------------------------------------------------------------------------
# config-get
# ---------------------------------------------------------------------------

@group.command("config-get")
@click.option("--name", required=True, help="Extension config name.")
@pass_context
def config_get(ctx, name) -> None:
    """Get an extension configuration.

    Example:
        limacharlie extension config-get --name my-extension
    """
    org = _get_org(ctx)
    hive = Hive(org, "extension_config")
    record = hive.get(name)
    _output(ctx, record.to_dict())


# ---------------------------------------------------------------------------
# config-set
# ---------------------------------------------------------------------------

@group.command("config-set")
@click.option("--name", required=True, help="Extension config name.")
@click.option("--input-file", default=None, type=click.Path(exists=True), help="Path to config data (JSON or YAML). Reads stdin if omitted.")
@pass_context
def config_set(ctx, name, input_file) -> None:
    """Set an extension configuration.

    Example:
        limacharlie extension config-set --name my-extension --input-file config.yaml
    """
    if input_file:
        with open(input_file, "r") as f:
            content = f.read()
    elif not sys.stdin.isatty():
        content = sys.stdin.read()
    else:
        raise click.UsageError("Provide data via --input-file or pipe to stdin.")

    try:
        data = yaml.safe_load(content)
    except Exception:
        data = json.loads(content)

    if isinstance(data, dict) and "data" in data:
        raw = {
            "data": data["data"],
            "usr_mtd": data.get("usr_mtd", {}),
            "sys_mtd": {},
        }
        if data.get("etag"):
            raw["sys_mtd"]["etag"] = data["etag"]
        record = HiveRecord.from_raw(name, raw)
    else:
        record = HiveRecord(name, data=data)

    org = _get_org(ctx)
    hive = Hive(org, "extension_config")
    result = hive.set(record)
    if not ctx.obj.quiet:
        click.echo(f"Extension config '{name}' set.")
    _output(ctx, result)


# ---------------------------------------------------------------------------
# config-delete
# ---------------------------------------------------------------------------

@group.command("config-delete")
@click.option("--name", required=True, help="Extension config name to delete.")
@click.option("--confirm", is_flag=True, default=False, help="Confirm deletion (required).")
@pass_context
def config_delete(ctx, name, confirm) -> None:
    """Delete an extension configuration.

    This is a destructive operation.  Pass --confirm to proceed.

    Example:
        limacharlie extension config-delete --name my-extension --confirm
    """
    if not confirm:
        click.echo(
            "Error: Destructive operation requires --confirm flag.\n"
            "Suggestion: Re-run with --confirm to delete the extension config.",
            err=True,
        )
        ctx.exit(4)
        return

    org = _get_org(ctx)
    hive = Hive(org, "extension_config")
    result = hive.delete(name)
    if not ctx.obj.quiet:
        click.echo(f"Extension config '{name}' deleted.")
    _output(ctx, result)
