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
from ._time_validation import validate_epoch_seconds


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

_EXPLAIN_RUN = """\
Replay a D&R rule against historical sensor data.  This allows you
to test detection logic against past events without deploying the
rule live.  Requires Insight to be enabled.  Replay is billed based
on data volume processed.

You can replay an existing deployed rule by --name, or provide
ad-hoc detection and response components from separate files via
--detect-file and --respond-file.

The --start and --end times are Unix timestamps in seconds.

The detection file should contain the detect component:

  event: NEW_PROCESS
  op: ends with
  path: event/FILE_PATH
  value: .scr

The response file should contain the respond component:

  - action: report
    name: suspicious-screensaver

The result includes num_evals (number of operator evaluations),
eval_time (seconds), num_events (events processed), responses
(list of detections that would have been generated), and errors.

Note: stateful rules (using 'with child', 'with descendant', or
'with events') are forward-looking only.  The parent event must
be seen before child matches apply during replay.

Examples:
  limacharlie replay run --name my-rule --start 1700000000 --end 1700100000
  limacharlie replay run --detect-file detect.yaml --respond-file respond.yaml --start 1700000000 --end 1700100000
"""
register_explain("replay.run", _EXPLAIN_RUN)


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
    validate_epoch_seconds(start, "start")
    validate_epoch_seconds(end, "end")
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
