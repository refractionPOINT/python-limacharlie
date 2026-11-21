"""Output commands for LimaCharlie CLI v2.

Commands for listing, creating, and deleting output integrations.
Outputs forward telemetry data (events, detections, audit logs) to
external systems such as S3, syslog, GCS, Slack, and more.
"""

from __future__ import annotations

from typing import Any

import json

import click
import yaml

from ..cli import pass_context
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.outputs import Outputs
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

_EXPLAIN_LIST = """\
List all configured outputs for the organization.  Outputs forward
telemetry data to external destinations in real-time.

Each output has:
  name    - unique identifier for this output
  module  - destination type (syslog, s3, gcs, slack, webhook, etc.)
  type    - which data stream is forwarded

The four output stream types:
  event      - real-time sensor telemetry (NEW_PROCESS, DNS_REQUEST, etc.)
  detect     - D&R rule detections/alerts
  audit      - platform management actions (config changes, API calls)
  deployment - sensor lifecycle events (install, uninstall, upgrade)

Returns the full configuration for each output including module-specific
parameters and any filtering rules (event_white_list, tag, cat, etc.).
"""
register_explain("output.list", _EXPLAIN_LIST)


@group.command("list")
@pass_context
def list_outputs(ctx: click.Context) -> None:
    org = _get_org(ctx)
    outputs = Outputs(org)
    data = outputs.list()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------

_EXPLAIN_CREATE = """\
Create a new output integration.  You must provide:

  --name     A unique name for this output.
  --module   The output module type.
  --type     The data stream to forward.

Stream types:  event, detect, audit, deployment

Available modules and their key config parameters:
  syslog        - dest_host, is_tls, is_strict_tls, is_no_header
  s3            - bucket, key_id, secret_key, is_compression, region_name, dir
  gcs           - bucket, secret_key (GCP service account JSON), is_compression, dir
  slack         - slack_api_token, slack_channel
  webhook       - dest_host, secret_key, auth_header_name, auth_header_value
  webhook_bulk  - dest_host, auth_header_name, auth_header_value
  scp / sftp    - dest_host, username, password/secret_key, dir
  kafka         - brokers, topic, username, password
  elastic       - dest_host, username, password, index
  bigquery      - project_id, dataset, secret_key (service account JSON)
  pubsub        - project_id, topic, secret_key (service account JSON)

Module-specific parameters are provided via --input-file (YAML or JSON).

Example syslog config file (syslog-config.yaml):
    dest_host: siem.corp.com:514
    is_tls: "true"
    is_strict_tls: "true"

Example S3 config file (s3-config.yaml):
    bucket: my-security-logs
    key_id: AKIAEXAMPLEKEY
    secret_key: wJalrXUtnFEMI/EXAMPLE
    is_compression: "true"
    region_name: us-east-1

Optional filtering parameters (add to config file):
    event_white_list: |        # newline-separated event types
      NEW_PROCESS
      DNS_REQUEST
    tag: production            # only events from sensors with this tag
    cat: high-priority         # only detections with this category

Examples:
  limacharlie output create --name my-syslog --module syslog \\
      --type event --input-file syslog-config.yaml

  limacharlie output create --name my-s3 --module s3 --type detect \\
      --input-file s3-config.yaml
"""
register_explain("output.create", _EXPLAIN_CREATE)


@group.command()
@click.option("--name", required=True, help="Output name.")
@click.option("--module", required=True, help="Output module type (e.g., syslog, s3, gcs, slack).")
@click.option("--type", "data_type", required=True, help="Data type to forward (event, detect, audit).")
@click.option("--input-file", default=None, type=click.Path(exists=True), help="Path to module-specific config (JSON or YAML).")
@pass_context
def create(ctx: click.Context, name: str, module: str, data_type: str, input_file: str | None) -> None:
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

_EXPLAIN_DELETE = """\
Delete an output integration by name.  This stops all data forwarding
for this output immediately.  The --confirm flag is required to prevent
accidental deletion.

Example:
  limacharlie output delete --name my-syslog --confirm
"""
register_explain("output.delete", _EXPLAIN_DELETE)


@group.command()
@click.option("--name", required=True, help="Output name to delete.")
@click.option("--confirm", is_flag=True, default=False, help="Confirm deletion (required).")
@pass_context
def delete(ctx: click.Context, name: str, confirm: bool) -> None:
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
