"""ARL (Authenticated Resource Locator) commands for LimaCharlie CLI v2.

Commands for resolving Authenticated Resource Locators.  ARLs are
URLs that reference data stored in LimaCharlie's secure storage,
such as payloads, artifacts, or other resources.
"""

from __future__ import annotations

from typing import Any, Callable

import click

from ..cli import pass_context
from ..config import resolve_credentials
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.arl import ARL as ARLSDK
from ..output import format_output, detect_output_format
from ..discovery import register_explain


# ---------------------------------------------------------------------------
# Explain texts
# ---------------------------------------------------------------------------

_EXPLAIN_GET = """\
Resolve an Authenticated Resource Locator (ARL) and return the
referenced data.  ARLs are secure URLs used by LimaCharlie to
reference payloads, artifacts, and other stored resources.

The --url parameter should be a valid ARL string (typically
starting with 'lcr://').

Example:
  limacharlie arl get --url "lcr://my-resource/path"
"""

register_explain("arl.get", _EXPLAIN_GET)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_explain_callback(text: str) -> Callable[[click.Context, click.Parameter, bool], None]:
    def callback(ctx: click.Context, param: click.Parameter, value: bool) -> None:
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


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------

@click.group("arl")
def group() -> None:
    """Resolve Authenticated Resource Locators.

    ARLs are secure URLs used by LimaCharlie to reference payloads,
    artifacts, and other stored resources.
    """


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------

@group.command()
@click.option("--url", required=True, help="ARL URL to resolve.")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_GET),
    help="Show detailed explanation of this command.",
)
@pass_context
def get(ctx, url) -> None:
    """Resolve an ARL and return the data.

    Example:
        limacharlie arl get --url "lcr://my-resource/path"
    """
    org = _get_org(ctx)
    sdk = ARLSDK(org)
    data = sdk.get(url)
    _output(ctx, data)
