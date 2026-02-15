"""USP (Universal Sensor Protocol) commands for LimaCharlie CLI v2.

Commands for validating USP adapter configurations.  USP adapters
allow ingesting data from third-party sources into LimaCharlie.
"""

from __future__ import annotations

from typing import Any

import json

import click
import yaml

from ..cli import pass_context
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.usp import USP as USPSDK
from ..output import format_output, detect_output_format
from ..discovery import register_explain


# ---------------------------------------------------------------------------
# Explain texts
# ---------------------------------------------------------------------------

_EXPLAIN_VALIDATE = """\
Validate a USP adapter configuration by sending test input data
through the adapter's parsing pipeline.  This verifies that the
adapter correctly parses and maps the input data.

The --input-file should contain a JSON or YAML document with the
adapter configuration, including mapping rules and test input data
(text_input or json_input).

The --platform identifies the adapter platform (e.g., 'text',
'json', 'cef', 'syslog').

Example:
  limacharlie usp validate --platform json --input-file adapter.yaml
"""

register_explain("usp.validate", _EXPLAIN_VALIDATE)


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

@click.group("usp")
def group() -> None:
    """Validate USP adapter configurations.

    USP (Universal Sensor Protocol) adapters allow ingesting data
    from third-party sources into LimaCharlie.  Use validate to
    test adapter parsing before deployment.
    """


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------

@group.command()
@click.option("--platform", required=True, help="Adapter platform (e.g., text, json, cef, syslog).")
@click.option(
    "--input-file", required=True, type=click.Path(exists=True),
    help="Path to adapter config/test file (JSON or YAML).",
)
@pass_context
def validate(ctx, platform, input_file) -> None:
    """Validate a USP adapter configuration.

    Example:
        limacharlie usp validate --platform json --input-file adapter.yaml
    """
    adapter_data = _load_file(input_file)
    if not isinstance(adapter_data, dict):
        click.echo("Error: Input file must be a JSON or YAML object.", err=True)
        ctx.exit(4)
        return

    org = _get_org(ctx)
    sdk = USPSDK(org)
    data = sdk.validate(
        platform=platform,
        mapping=adapter_data.get("mapping"),
        mappings=adapter_data.get("mappings"),
        text_input=adapter_data.get("text_input"),
        json_input=adapter_data.get("json_input"),
        hostname=adapter_data.get("hostname"),
        indexing=adapter_data.get("indexing"),
    )
    _output(ctx, data)
