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


# ---------------------------------------------------------------------------
# Explain texts
# ---------------------------------------------------------------------------

_EXPLAIN_LIST = """\
List artifacts stored in Insight for the organization.  Artifacts are
uploaded log files and binary data associated with sensors or ingested
externally.

Use --sid to filter artifacts for a specific sensor.  Without filters,
all artifacts in the organization are listed.

The output includes artifact IDs, source info, and timestamps.
"""


_EXPLAIN_UPLOAD = """\
Upload an artifact/log file to Insight.  The file is uploaded using
the ingestion endpoint and stored in the organization's Insight data
lake.

The upload requires an ingestion key, provided via the LC_LOGS_TOKEN
environment variable or passed to the SDK.

Optional parameters control the source label, parse hint, retention
period, and original file path metadata.

Examples:
  limacharlie artifact upload --file /var/log/syslog --source my-server
  limacharlie artifact upload --file data.pcap --hint pcap --retention-days 90
"""

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

register_explain("artifact.list", _EXPLAIN_LIST)
register_explain("artifact.upload", _EXPLAIN_UPLOAD)
register_explain("artifact.download", _EXPLAIN_DOWNLOAD)


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

@click.group("artifact")
def group() -> None:
    """Manage artifacts and uploaded logs.

    Artifacts are log files and binary data stored in LimaCharlie
    Insight.  They can be uploaded from sensors or ingested externally.
    """


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

@group.command("list")
@click.option("--sid", default=None, help="Filter by sensor ID.")
@click.option("--type", "artifact_type", default=None, help="Filter by artifact type.")
@click.option("--start", default=None, type=int, help="Start time (unix seconds).")
@click.option("--end", default=None, type=int, help="End time (unix seconds).")
@click.option("--limit", default=None, type=int, help="Maximum number of results.")
@pass_context
def list_artifacts(ctx, sid, artifact_type, start, end, limit) -> None:
    """List artifacts.

    Examples:
        limacharlie artifact list
        limacharlie artifact list --sid <SID>
        limacharlie artifact list --sid <SID> --output json
    """
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

@group.command()
@click.option("--file", "file_path", required=True, type=click.Path(exists=True), help="Path to the file to upload.")
@click.option("--source", default=None, help="Source identifier label.")
@click.option("--hint", default=None, help="Parse hint (e.g., pcap, json, wel, prefetch, txt).")
@click.option("--retention-days", default=None, type=int, help="Retention period in days (default: 30).")
@click.option("--original-path", default=None, help="Original file path on the source system.")
@pass_context
def upload(ctx, file_path, source, hint, retention_days, original_path) -> None:
    """Upload an artifact/log file.

    Requires LC_LOGS_TOKEN environment variable to be set with an
    ingestion key.

    Examples:
        limacharlie artifact upload --file /var/log/syslog --source my-server
        limacharlie artifact upload --file data.pcap --hint pcap --retention-days 90
    """
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

@group.command()
@click.option("--id", "artifact_id", required=True, help="Artifact ID to download.")
@click.option("--output-path", default=None, type=click.Path(), help="Local path to save the artifact to.")
@pass_context
def download(ctx, artifact_id, output_path) -> None:
    """Download an artifact by ID.

    If --output-path is given, saves to that file.  Otherwise prints
    the download URL or inline data.

    Examples:
        limacharlie artifact download --id <ARTIFACT_ID>
        limacharlie artifact download --id <ARTIFACT_ID> --output-path ./artifact.log
    """
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
