"""Spotcheck commands for LimaCharlie CLI v2."""

from __future__ import annotations

from typing import Any

import click

from ..cli import pass_context
from ..client import Client
from ..sdk.organization import Organization
from ..output import format_output, detect_output_format
from ..discovery import register_explain


def _get_org(ctx: click.Context) -> Organization:
    client = Client(oid=ctx.obj.oid, environment=ctx.obj.environment)
    return Organization(client)


def _output(ctx: click.Context, data: Any) -> None:
    fmt = ctx.obj.output_format or detect_output_format()
    if not ctx.obj.quiet:
        click.echo(format_output(data, fmt))


_EXPLAIN_RUN = """\
Run a spotcheck task across sensors.  Spotcheck executes a sensor command
across multiple sensors matching a selector or tag and collects the
aggregated results.  This is useful for ad-hoc fleet-wide queries such
as checking if a specific process is running, a file exists, or a
service is installed across the fleet.

The --task value is any sensor command string (same as 'limacharlie
task send --task').  Common spotcheck tasks:
  os_processes       - List processes on all matching sensors
  os_services        - List services
  os_packages        - List installed packages
  netstat            - List network connections

Use --tag to target sensors with a specific tag, or --selector for
more complex bexpr expressions.

Example:
  limacharlie spotcheck run --task os_processes --tag production
"""

@click.group("spotcheck")
def group() -> None:
    """Run ad-hoc fleet-wide spotcheck queries."""
    pass


@group.command("run")
@click.option("--task", required=True, help="Sensor task command to run (e.g., os_processes).")
@click.option("--tag", default=None, help="Only target sensors with this tag.")
@click.option("--selector", default=None, help="Sensor selector expression.")
@pass_context
def run_cmd(ctx, task, tag, selector) -> None:
    """Run a spotcheck across sensors."""
    org = _get_org(ctx)
    params = {"action": "spotcheck", "task": task}
    if tag:
        params["tag"] = tag
    if selector:
        params["selector"] = selector
    result = org.service_request("spotcheck", params)
    _output(ctx, result)


register_explain("spotcheck.run", _EXPLAIN_RUN)
