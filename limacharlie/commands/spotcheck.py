"""Spotcheck commands for LimaCharlie CLI v2."""

from __future__ import annotations

from typing import Any, Callable

import click

from ..cli import pass_context
from ..config import resolve_credentials
from ..client import Client
from ..sdk.organization import Organization
from ..output import format_output, detect_output_format
from ..discovery import register_explain


def _get_org(ctx: click.Context) -> Organization:
    creds = resolve_credentials(oid=ctx.obj.oid, environment=ctx.obj.environment)
    client = Client(oid=creds["oid"], api_key=creds.get("api_key"), uid=creds.get("uid"))
    return Organization(client)


def _output(ctx: click.Context, data: Any) -> None:
    fmt = ctx.obj.output_format or detect_output_format()
    if not ctx.obj.quiet:
        click.echo(format_output(data, fmt))


_EXPLAIN_RUN = """\
Run a spotcheck task across sensors. Spotcheck executes a sensor command
across multiple sensors matching a selector and collects the results.
This is useful for ad-hoc fleet-wide queries.
"""

def _make_explain_callback(text: str) -> Callable[[click.Context, click.Parameter, bool], None]:
    def callback(ctx: click.Context, param: click.Parameter, value: bool) -> None:
        if value:
            click.echo(text)
            ctx.exit(0)
    return callback


@click.group("spotcheck")
def group() -> None:
    """Run ad-hoc fleet-wide spotcheck queries."""
    pass


@group.command("run")
@click.option("--task", required=True, help="Sensor task command to run (e.g., os_processes).")
@click.option("--tag", default=None, help="Only target sensors with this tag.")
@click.option("--selector", default=None, help="Sensor selector expression.")
@click.option("--explain", is_flag=True, is_eager=True, expose_value=False, callback=_make_explain_callback(_EXPLAIN_RUN))
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
