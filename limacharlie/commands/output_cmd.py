"""Output commands for LimaCharlie CLI v2.

Commands for listing, creating, and deleting output integrations.
Outputs forward telemetry data (events, detections, audit logs) to
external systems such as S3, syslog, GCS, Slack, and more.
"""

from __future__ import annotations

from typing import Any, Callable

import json
import sys

import click
import yaml

from ..cli import pass_context
from ..config import resolve_credentials
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.outputs import Outputs
from ..output import format_output, detect_output_format
from ..discovery import register_explain


# ---------------------------------------------------------------------------
# Explain texts
# ---------------------------------------------------------------------------

_EXPLAIN_LIST = """\
List all configured outputs for the organization.  Outputs forward
telemetry data to external destinations.  Each output has a name,
module type (e.g., 'syslog', 's3', 'gcs', 'slack'), and a data type
filter (e.g., 'event', 'detect', 'audit').

The output includes the full configuration for each output.
"""

_EXPLAIN_CREATE = """\
Create a new output integration.  You must provide:

  --name     A unique name for this output.
  --module   The output module type (e.g., 'syslog', 's3', 'gcs', 'slack').
  --type     The data type to forward ('event', 'detect', 'audit', etc.).

Module-specific parameters can be provided via --input-file as a JSON
or YAML document.  The file contents are passed as additional keyword
arguments to the API.

Examples:
  limacharlie output create --name my-syslog --module syslog \\
      --type event --input-file syslog-config.yaml

  limacharlie output create --name my-s3 --module s3 --type detect \\
      --input-file s3-config.json
"""

_EXPLAIN_DELETE = """\
Delete an output integration by name.  This stops all data forwarding
for this output immediately.  The --confirm flag is required to prevent
accidental deletion.
"""

register_explain("output.list", _EXPLAIN_LIST)
register_explain("output.create", _EXPLAIN_CREATE)
register_explain("output.delete", _EXPLAIN_DELETE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_explain_callback(text: str) -> Callable[..., None]:
    def callback(ctx: click.Context, param: click.Parameter, value: Any) -> None:
        if value:
            click.echo(text.strip())
            ctx.exit()
    return callback


def _output(ctx: click.Context, data: Any) -> None:
    fmt = ctx.obj.output_format or detect_output_format()
    if not ctx.obj.quiet:
        click.echo(format_output(data, fmt))


def _get_org(ctx: click.Context) -> Organization:
    creds = resolve_credentials(oid=ctx.obj.oid, environment=ctx.obj.environment)
    client = Client(oid=creds["oid"], api_key=creds.get("api_key"), uid=creds.get("uid"))
    return Organization(client)


def _load_file(path: str) -> Any:
    """Load a JSON or YAML file and return parsed content."""
    with open(path, "r") as f:
        content = f.read()
    try:
        return yaml.safe_load(content)
    except Exception:
        pass
    return json.loads(content)


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------

@click.group("output")
def group() -> None:
    """Manage output integrations.

    Outputs forward telemetry data (events, detections, audit logs) to
    external systems such as S3, syslog, GCS, Slack, and more.
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
def list_outputs(ctx: click.Context) -> None:
    """List configured outputs.

    Example:
        limacharlie output list
    """
    org = _get_org(ctx)
    outputs = Outputs(org)
    data = outputs.list()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------

@group.command()
@click.option("--name", required=True, help="Output name.")
@click.option("--module", required=True, help="Output module type (e.g., syslog, s3, gcs, slack).")
@click.option("--type", "data_type", required=True, help="Data type to forward (event, detect, audit).")
@click.option("--input-file", default=None, type=click.Path(exists=True), help="Path to module-specific config (JSON or YAML).")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_CREATE),
    help="Show detailed explanation of this command.",
)
@pass_context
def create(ctx: click.Context, name: str, module: str, data_type: str, input_file: str | None) -> None:
    """Create a new output integration.

    Examples:
        limacharlie output create --name my-syslog --module syslog \\
            --type event --input-file syslog-config.yaml

        limacharlie output create --name my-s3 --module s3 --type detect \\
            --input-file s3-config.json
    """
    extra_params = {}
    if input_file:
        extra_params = _load_file(input_file)
        if not isinstance(extra_params, dict):
            click.echo("Error: --input-file must be a JSON/YAML object with module-specific parameters.", err=True)
            ctx.exit(4)
            return

    org = _get_org(ctx)
    outputs = Outputs(org)
    data = outputs.create(name, module, data_type, **extra_params)
    if not ctx.obj.quiet:
        click.echo(f"Output '{name}' created.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

@group.command()
@click.option("--name", required=True, help="Output name to delete.")
@click.option("--confirm", is_flag=True, default=False, help="Confirm deletion (required).")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_DELETE),
    help="Show detailed explanation of this command.",
)
@pass_context
def delete(ctx: click.Context, name: str, confirm: bool) -> None:
    """Delete an output integration.

    This is a destructive operation.  Pass --confirm to proceed.

    Example:
        limacharlie output delete --name my-syslog --confirm
    """
    if not confirm:
        click.echo(
            "Error: Destructive operation requires --confirm flag.\n"
            "Suggestion: Re-run with --confirm to delete the output.",
            err=True,
        )
        ctx.exit(4)
        return

    org = _get_org(ctx)
    outputs = Outputs(org)
    data = outputs.delete(name)
    if not ctx.obj.quiet:
        click.echo(f"Output '{name}' deleted.")
    _output(ctx, data)
