"""Artifact commands for LimaCharlie CLI v2.

Commands for listing, retrieving, uploading, and downloading artifacts
(uploaded logs and files) stored in LimaCharlie Insight.
"""

from __future__ import annotations

from typing import Any

import click

from ..cli import pass_context
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.artifacts import Artifacts
from ..output import format_output, detect_output_format
from ..discovery import register_explain
from ._time_validation import validate_epoch_seconds


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

@click.group("artifact")
def group() -> None:
    """Manage artifacts and uploaded logs.

    Artifacts are log files and binary data stored in LimaCharlie
    Insight.  They can be uploaded from sensors or ingested externally.
    """


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

_EXPLAIN_LIST = """\
List artifacts stored in Insight for the organization.  Artifacts are
log files and binary data collected from sensors or ingested externally.

Types of artifacts:
  - Files collected from endpoints via D&R response actions or the
    Artifact extension
  - Windows Event Log (WEL) streams captured via wel:// patterns
  - Mac Unified Log (MUL) streams
  - PCAP network captures (Linux only)
  - Externally uploaded log files (syslog, JSON, pcap, prefetch, etc.)

Use --sid to filter artifacts for a specific sensor.  Use --type to
filter by artifact type.  Use --start/--end to filter by time range
(Unix timestamps in seconds).

The output includes artifact IDs, source info, type, and timestamps.
Use the artifact ID with 'artifact download' to retrieve the data.
"""
register_explain("artifact.list", _EXPLAIN_LIST)


@group.command("list")
@click.option("--sid", default=None, help="Filter by sensor ID.")
@click.option("--type", "artifact_type", default=None, help="Filter by artifact type.")
@click.option("--start", default=None, type=int, help="Start time (unix seconds).")
@click.option("--end", default=None, type=int, help="End time (unix seconds).")
@click.option("--limit", default=None, type=int, help="Maximum number of results.")
@pass_context
def list_artifacts(ctx, sid, artifact_type, start, end, limit) -> None:
    validate_epoch_seconds(start, "start")
    validate_epoch_seconds(end, "end")
    org = _get_org(ctx)
    artifacts = Artifacts(org)
    data = artifacts.list(sid=sid, start=start, end=end)
    # Apply client-side filters for type and limit
    results = data if isinstance(data, list) else data.get("artifacts", data.get("logs", [data]))
    if artifact_type:
        results = [a for a in results if a.get("type") == artifact_type]
    if limit:
        results = results[:limit]
    _output(ctx, results)


# ---------------------------------------------------------------------------
# upload
# ---------------------------------------------------------------------------

_EXPLAIN_UPLOAD = """\
Upload an artifact/log file to Insight.  The file is ingested and
stored in the organization's data lake where it can be searched via
LCQL and viewed in the web UI.

The upload requires an ingestion key, provided via the LC_LOGS_TOKEN
environment variable or passed to the SDK.

Optional parameters:
  --source          Label identifying the source system (e.g. hostname).
  --hint            Parse hint telling Insight how to interpret the file.
                    Supported hints: pcap, json, wel (Windows Event Log),
                    prefetch, txt, evtx, xml, csv, clf (Common Log Format).
  --retention-days  How long to keep the artifact (default: 30 days).
  --original-path   Original file path on the source system (metadata).

Artifacts are parsed according to the hint and become searchable
telemetry.  For example, uploading a pcap with --hint pcap makes
its network connections queryable.

Examples:
  limacharlie artifact upload --file /var/log/syslog --source my-server
  limacharlie artifact upload --file data.pcap --hint pcap --retention-days 90
  limacharlie artifact upload --file security.evtx --hint wel --source dc01
"""
register_explain("artifact.upload", _EXPLAIN_UPLOAD)


@group.command()
@click.option("--file", "file_path", required=True, type=click.Path(exists=True), help="Path to the file to upload.")
@click.option("--source", default=None, help="Source identifier label.")
@click.option("--hint", default=None, help="Parse hint (e.g., pcap, json, wel, prefetch, txt).")
@click.option("--retention-days", default=None, type=int, help="Retention period in days (default: 30).")
@click.option("--original-path", default=None, help="Original file path on the source system.")
@pass_context
def upload(ctx, file_path, source, hint, retention_days, original_path) -> None:
    org = _get_org(ctx)
    artifacts = Artifacts(org)
    data = artifacts.upload(
        file_path,
        source=source,
        hint=hint,
        retention_days=retention_days,
        original_path=original_path,
    )
    if not ctx.obj.quiet:
        click.echo(f"Artifact uploaded from '{file_path}'.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# download
# ---------------------------------------------------------------------------

_EXPLAIN_DOWNLOAD = """\
Download an artifact by its ID.  Retrieves the original artifact data
from Insight.  For small artifacts the data may be returned inline;
for larger ones a signed download URL is returned.

If --output-path is specified, the artifact is saved to that file.
Otherwise, the download URL or inline data is printed to stdout.

Examples:
  limacharlie artifact download --id <ARTIFACT_ID>
  limacharlie artifact download --id <ARTIFACT_ID> --output-path ./artifact.log
"""
register_explain("artifact.download", _EXPLAIN_DOWNLOAD)


@group.command()
@click.option("--id", "artifact_id", required=True, help="Artifact ID to download.")
@click.option("--output-path", default=None, type=click.Path(), help="Local path to save the artifact to.")
@pass_context
def download(ctx, artifact_id, output_path) -> None:
    org = _get_org(ctx)
    artifacts = Artifacts(org)
    data = artifacts.get_url(artifact_id)

    if output_path is not None:
        # If the response has inline payload, write it directly.
        if "payload" in data:
            import base64
            payload = data["payload"]
            if isinstance(payload, str):
                raw = base64.b64decode(payload)
            else:
                raw = payload
            with open(output_path, "wb") as f:
                f.write(raw)
            if not ctx.obj.quiet:
                click.echo(f"Artifact saved to '{output_path}'.")
        elif "export" in data:
            # Download from the signed URL.
            from urllib.request import urlopen
            url = data["export"]
            with urlopen(url) as resp:
                with open(output_path, "wb") as f:
                    while True:
                        chunk = resp.read(1024 * 1024 * 5)
                        if not chunk:
                            break
                        f.write(chunk)
            if not ctx.obj.quiet:
                click.echo(f"Artifact saved to '{output_path}'.")
        else:
            _output(ctx, data)
    else:
        _output(ctx, data)
