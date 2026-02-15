"""Payload commands for LimaCharlie CLI v2.

Commands for listing and deleting payloads.  Payloads are binary
artifacts (executables, scripts, etc.) that can be deployed to
sensors via D&R response actions.
"""

from __future__ import annotations

from typing import Any

import click

from ..cli import pass_context
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.payloads import Payloads
from ..output import format_output, detect_output_format
from ..discovery import register_explain


# ---------------------------------------------------------------------------
# Explain texts
# ---------------------------------------------------------------------------

_EXPLAIN_LIST = """\
List all payloads stored in the organization.  Payloads are binary
artifacts (executables, scripts, configuration files) that can be
deployed to sensors via D&R response actions or tasking commands.

Payloads are referenced by name in D&R response actions:

    respond:
      - action: task
        command: run --payload-name my-script

Or deployed directly via the 'put' sensor command.

The output includes payload names and metadata.
"""

_EXPLAIN_DELETE = """\
Delete a payload by name.  This permanently removes the payload from
the organization.  Any D&R rules referencing this payload will fail
when triggered.  The --confirm flag is required to prevent accidental
deletion.
"""

_EXPLAIN_UPLOAD = """\
Upload a payload file to the organization.  Payloads are binary
artifacts (executables, scripts, configuration files) that can be
deployed to sensors via D&R response actions or tasking commands.

The --name is the identifier used to reference the payload in D&R
rules or tasking.  The --file is the local file to upload.

Examples:
  limacharlie payload upload --name my-script --file ./script.sh
  limacharlie payload upload --name collector.exe --file /opt/tools/collector.exe
"""

_EXPLAIN_DOWNLOAD = """\
Download a payload by name.  Returns the payload data or metadata
from the organization.

If --output-path is specified, the payload is saved to that file.
Otherwise, the payload data/URL is printed to stdout.

Examples:
  limacharlie payload download --name my-script
  limacharlie payload download --name my-script --output-path ./script.sh
"""

register_explain("payload.list", _EXPLAIN_LIST)
register_explain("payload.delete", _EXPLAIN_DELETE)
register_explain("payload.upload", _EXPLAIN_UPLOAD)
register_explain("payload.download", _EXPLAIN_DOWNLOAD)


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

@click.group("payload")
def group() -> None:
    """Manage payloads.

    Payloads are binary artifacts that can be deployed to sensors
    via D&R response actions or tasking commands.
    """


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

@group.command("list")
@pass_context
def list_payloads(ctx) -> None:
    """List payloads.

    Example:
        limacharlie payload list
    """
    org = _get_org(ctx)
    payloads = Payloads(org)
    data = payloads.list()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

@group.command()
@click.option("--name", required=True, help="Payload name to delete.")
@click.option("--confirm", is_flag=True, default=False, help="Confirm deletion (required).")
@pass_context
def delete(ctx, name, confirm) -> None:
    """Delete a payload.

    This is a destructive operation.  Pass --confirm to proceed.

    Example:
        limacharlie payload delete --name my-payload --confirm
    """
    if not confirm:
        click.echo(
            "Error: Destructive operation requires --confirm flag.\n"
            "Suggestion: Re-run with --confirm to delete the payload.",
            err=True,
        )
        ctx.exit(4)
        return

    org = _get_org(ctx)
    payloads = Payloads(org)
    data = payloads.delete(name)
    if not ctx.obj.quiet:
        click.echo(f"Payload '{name}' deleted.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# upload
# ---------------------------------------------------------------------------

@group.command()
@click.option("--name", required=True, help="Payload name (identifier for D&R rules and tasking).")
@click.option("--file", "file_path", required=True, type=click.Path(exists=True), help="Path to the file to upload.")
@pass_context
def upload(ctx, name, file_path) -> None:
    """Upload a payload.

    Examples:
        limacharlie payload upload --name my-script --file ./script.sh
        limacharlie payload upload --name collector.exe --file /opt/tools/collector.exe
    """
    org = _get_org(ctx)
    payloads = Payloads(org)
    data = payloads.upload(name, file_path=file_path)
    if not ctx.obj.quiet:
        click.echo(f"Payload '{name}' uploaded.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# download
# ---------------------------------------------------------------------------

@group.command()
@click.option("--name", required=True, help="Payload name to download.")
@click.option("--output-path", default=None, type=click.Path(), help="Local path to save the payload to.")
@pass_context
def download(ctx, name, output_path) -> None:
    """Download a payload.

    If --output-path is given, saves to that file.  Otherwise prints
    the payload data/URL.

    Examples:
        limacharlie payload download --name my-script
        limacharlie payload download --name my-script --output-path ./script.sh
    """
    org = _get_org(ctx)
    payloads = Payloads(org)
    data = payloads.download(name)

    if data is None:
        click.echo(f"Error: Payload '{name}' not found.", err=True)
        ctx.exit(1)
        return

    if output_path is not None:
        with open(output_path, "wb") as f:
            f.write(data)
        if not ctx.obj.quiet:
            click.echo(f"Payload '{name}' saved to '{output_path}'.")
    else:
        # Write raw bytes to stdout
        import sys
        sys.stdout.buffer.write(data)
