"""ARL (Authenticated Resource Locator) commands for LimaCharlie CLI v2.

Commands for resolving Authenticated Resource Locators.  ARLs are
URLs that reference data stored in LimaCharlie's secure storage,
such as payloads, artifacts, or other resources.
"""

from __future__ import annotations

from typing import Any

import click

from ..cli import pass_context
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
referenced data.  ARLs are compact strings that describe how to
fetch a remote resource, optionally with authentication.

ARL format:  [methodName,methodDest,authType,authData]

  methodName - transport: https, http, gcs, github
  methodDest - destination (domain/path, bucket/path, org/repo/path)
  authType   - (optional) basic, bearer, token, gaia, otx
  authData   - (optional) credentials for the auth type

Examples of valid ARLs:

  Public HTTPS (no auth):
    [https,my.corp.com/resource/data]

  HTTPS with basic auth:
    [https,my.corp.com/resource,basic,user:password]

  HTTPS with bearer token:
    [https,my.corp.com/resource,bearer,<token>]

  Public GitHub repo (main branch):
    [github,myOrg/myRepo/path/to/file]

  Private GitHub repo with PAT:
    [github,myOrg/myRepo/path,token,<github-pat>]

  GitHub repo at specific branch:
    [github,myOrg/myRepo/path?ref=my-branch]

  Google Cloud Storage with service account:
    [gcs,my-bucket/blob-prefix,gaia,base64(<service-key-json>)]

ARLs are used by the YARA manager, lookup manager, and other
extensions to fetch external rule/data sources.

Example:
  limacharlie arl get --url "[https,example.com/data.json]"
"""

register_explain("arl.get", _EXPLAIN_GET)


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
