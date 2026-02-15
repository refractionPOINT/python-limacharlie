"""Replay commands for LimaCharlie CLI v2.

Commands for replaying D&R rules against historical sensor data.
Replay lets you test detection logic against past events without
waiting for new telemetry.
"""

from __future__ import annotations

import json
from typing import Any

import click
import yaml

from ..cli import pass_context
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.replay import Replay as ReplaySDK
from ..output import format_output, detect_output_format
from ..discovery import register_explain


# ---------------------------------------------------------------------------
# Explain texts
# ---------------------------------------------------------------------------

_EXPLAIN_RUN = """\
Replay a D&R rule against historical sensor data.  This allows you
to test detection logic against past events without deploying the
rule live.

You can replay an existing rule by name:
  limacharlie replay run --name my-rule --start 1700000000 --end 1700100000

Or provide detection and response components from files:
  limacharlie replay run --detect-file detect.yaml \\
    --respond-file respond.yaml --start 1700000000 --end 1700100000

The --start and --end times are Unix timestamps in seconds.

The results include any detections that would have been generated
and (optionally) a trace of the rule evaluation.
"""

register_explain("replay.run", _EXPLAIN_RUN)


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

@click.group("replay")
def group() -> None:
    """Replay D&R rules against historical data.

    Test detection logic by running rules against past sensor
    events.  This is useful for validating new rules before
    deploying them live.
    """


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

@group.command()
@click.option("--name", default=None, help="Existing rule name to replay.")
@click.option(
    "--detect-file", default=None, type=click.Path(exists=True),
    help="Path to detection component file (JSON or YAML).",
)
@click.option(
    "--respond-file", default=None, type=click.Path(exists=True),
    help="Path to response component file (JSON or YAML).",
)
@click.option("--start", required=True, type=int, help="Start time (Unix seconds).")
@click.option("--end", required=True, type=int, help="End time (Unix seconds).")
@pass_context
def run(ctx, name, detect_file, respond_file, start, end) -> None:
    """Replay a rule against historical data.

    Provide either --name for an existing rule, or --detect-file and
    --respond-file for ad-hoc rule components.

    Examples:
        limacharlie replay run --name my-rule \\
            --start 1700000000 --end 1700100000

        limacharlie replay run --detect-file detect.yaml \\
            --respond-file respond.yaml --start 1700000000 --end 1700100000
    """
    detect = None
    respond = None

    if name is None:
        if detect_file is None or respond_file is None:
            click.echo(
                "Error: Provide --name for an existing rule, or both "
                "--detect-file and --respond-file for ad-hoc replay.",
                err=True,
            )
            ctx.exit(4)
            return
        detect = _load_file(detect_file)
        respond = _load_file(respond_file)

    org = _get_org(ctx)
    replay = ReplaySDK(org)
    data = replay.run(
        rule_name=name,
        detect=detect,
        respond=respond,
        start=start,
        end=end,
    )
    _output(ctx, data)
