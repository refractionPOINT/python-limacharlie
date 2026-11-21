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
from ..yaml_input import load_yaml

from ..cli import pass_context
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.replay import Replay as ReplaySDK
from ..output import format_output, detect_output_format
from ..discovery import register_explain
from ._replay_completeness import warn_if_partial
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


def _load_file(path: str) -> Any:
    """Load a JSON or YAML file and return parsed content."""
    with open(path, "r") as f:
        content = f.read()
    try:
        return load_yaml(content)
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

The --start and --end times are Unix timestamps in seconds.  Use
--sid to limit the replay to one sensor, or --selector for a sensor
selector expression (tags, platform, hostname, etc.).  Scope the replay
to the sensors the rule is meant for: an org-wide replay over a long
window can stop at the server's deadline before it covers everything.

The detection file should contain the detect component:

  event: NEW_PROCESS
  op: ends with
  path: event/FILE_PATH
  value: .scr

The response file should contain the respond component:

  - action: report
    name: suspicious-screensaver

The result includes stats (n_proc events processed, n_eval operator
evaluations, n_matched matches), results (the detections that would
have been generated), did_match, and error.

A replay that stops early still answers with the matches found so far.
When stats.results_partial is true, stats.stop_reason names a stop
(such as request_deadline), stats.skipped_events is not empty, or error
is set, the results cover only part of the window: zero matches then
does not show the rule is clean.  The CLI prints a warning to stderr in
that case.  Re-run with a narrower --sid/--selector or a shorter window.

Note: stateful rules (using 'with child', 'with descendant', or
'with events') are forward-looking only.  The parent event must
be seen before child matches apply during replay.

Examples:
  limacharlie replay run --name my-rule --start 1700000000 --end 1700100000
  limacharlie replay run --detect-file detect.yaml --respond-file respond.yaml --start 1700000000 --end 1700100000
  limacharlie replay run --detect-file detect.yaml --respond-file respond.yaml --start 1700000000 --end 1700100000 --selector 'plat == "linux" and "prod" in tags'
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
@click.option("--sid", default=None, help="Specific sensor ID to replay against.")
@click.option("--selector", default=None, help="Sensor selector expression (bexpr).")
@pass_context
def run(ctx, name, detect_file, respond_file, start, end, sid, selector) -> None:
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
        sid=sid,
        selector=selector,
    )
    _output(ctx, data)
    warn_if_partial(data)
