"""YARA commands for LimaCharlie CLI v2.

Commands for YARA scanning, rule management, and source management.
YARA rules can be deployed to sensors for real-time scanning or
used for ad-hoc scans against specific sensors.
"""

from __future__ import annotations

from typing import Any, Callable

import click

from ..cli import pass_context
from ..config import resolve_credentials
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.yara import Yara as YaraSDK
from ..output import format_output, detect_output_format
from ..discovery import register_explain


# ---------------------------------------------------------------------------
# Explain texts
# ---------------------------------------------------------------------------

_EXPLAIN_SCAN = """\
Run an ad-hoc YARA scan on a specific sensor.  Provide the sensor
ID and a file containing YARA rule content.

The rule file should contain valid YARA rule syntax.  The scan is
executed on the sensor and results are returned.

Example:
  limacharlie yara scan --sid <sensor-id> --rule-file rules.yar
"""

_EXPLAIN_RULES_LIST = """\
List all deployed YARA rules in the organization.  These are rules
that have been added for continuous or scheduled scanning.
"""

_EXPLAIN_RULE_ADD = """\
Add a YARA rule for deployment.  The --sources-file should contain
a JSON or YAML list of YARA source references.

Example:
  limacharlie yara rule-add --name my-rule --sources-file sources.yaml
"""

_EXPLAIN_RULE_DELETE = """\
Delete a deployed YARA rule by name.

Example:
  limacharlie yara rule-delete --name my-rule
"""

_EXPLAIN_SOURCES_LIST = """\
List all YARA sources.  Sources are named collections of YARA rule
content that can be referenced by deployed rules.
"""

_EXPLAIN_SOURCE_GET = """\
Get the content of a specific YARA source by name.

Example:
  limacharlie yara source-get --name my-source
"""

_EXPLAIN_SOURCE_ADD = """\
Add or update a YARA source.  The --source-file should contain
valid YARA rule content.

Example:
  limacharlie yara source-add --name my-source --source-file rules.yar
"""

_EXPLAIN_SOURCE_DELETE = """\
Delete a YARA source by name.

Example:
  limacharlie yara source-delete --name my-source
"""

register_explain("yara.scan", _EXPLAIN_SCAN)
register_explain("yara.rules-list", _EXPLAIN_RULES_LIST)
register_explain("yara.rule-add", _EXPLAIN_RULE_ADD)
register_explain("yara.rule-delete", _EXPLAIN_RULE_DELETE)
register_explain("yara.sources-list", _EXPLAIN_SOURCES_LIST)
register_explain("yara.source-get", _EXPLAIN_SOURCE_GET)
register_explain("yara.source-add", _EXPLAIN_SOURCE_ADD)
register_explain("yara.source-delete", _EXPLAIN_SOURCE_DELETE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_explain_callback(text: str) -> Callable[[click.Context, click.Parameter, bool], None]:
    def callback(ctx, param, value):
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

@click.group("yara")
def group() -> None:
    """Manage YARA scanning, rules, and sources.

    YARA rules can be deployed for continuous scanning or used
    for ad-hoc scans on specific sensors.  Sources are named
    collections of YARA rule content referenced by deployed rules.
    """


# ---------------------------------------------------------------------------
# scan
# ---------------------------------------------------------------------------

@group.command()
@click.option("--sid", required=True, help="Sensor ID to scan.")
@click.option(
    "--rule-file", required=True, type=click.Path(exists=True),
    help="Path to YARA rule file.",
)
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_SCAN),
    help="Show detailed explanation of this command.",
)
@pass_context
def scan(ctx, sid, rule_file) -> None:
    """Run an ad-hoc YARA scan on a sensor.

    Example:
        limacharlie yara scan --sid <sensor-id> --rule-file rules.yar
    """
    with open(rule_file, "r") as f:
        rule_content = f.read()

    org = _get_org(ctx)
    sdk = YaraSDK(org)
    data = sdk.scan(sid, rule_content)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# rules-list
# ---------------------------------------------------------------------------

@group.command("rules-list")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_RULES_LIST),
    help="Show detailed explanation of this command.",
)
@pass_context
def rules_list(ctx) -> None:
    """List deployed YARA rules.

    Example:
        limacharlie yara rules-list
    """
    org = _get_org(ctx)
    sdk = YaraSDK(org)
    data = sdk.list_rules()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# rule-add
# ---------------------------------------------------------------------------

@group.command("rule-add")
@click.option("--name", required=True, help="Rule name.")
@click.option(
    "--sources-file", required=True, type=click.Path(exists=True),
    help="Path to sources definition file (JSON or YAML).",
)
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_RULE_ADD),
    help="Show detailed explanation of this command.",
)
@pass_context
def rule_add(ctx, name, sources_file) -> None:
    """Add a YARA rule for deployment.

    Example:
        limacharlie yara rule-add --name my-rule --sources-file sources.yaml
    """
    import json
    import yaml

    with open(sources_file, "r") as f:
        content = f.read()
    try:
        sources = yaml.safe_load(content)
    except Exception:
        sources = json.loads(content)

    org = _get_org(ctx)
    sdk = YaraSDK(org)
    data = sdk.add_rule(name, sources)
    if not ctx.obj.quiet:
        click.echo(f"YARA rule '{name}' added.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# rule-delete
# ---------------------------------------------------------------------------

@group.command("rule-delete")
@click.option("--name", required=True, help="Rule name to delete.")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_RULE_DELETE),
    help="Show detailed explanation of this command.",
)
@pass_context
def rule_delete(ctx, name) -> None:
    """Delete a deployed YARA rule.

    Example:
        limacharlie yara rule-delete --name my-rule
    """
    org = _get_org(ctx)
    sdk = YaraSDK(org)
    data = sdk.delete_rule(name)
    if not ctx.obj.quiet:
        click.echo(f"YARA rule '{name}' deleted.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# sources-list
# ---------------------------------------------------------------------------

@group.command("sources-list")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_SOURCES_LIST),
    help="Show detailed explanation of this command.",
)
@pass_context
def sources_list(ctx) -> None:
    """List YARA sources.

    Example:
        limacharlie yara sources-list
    """
    org = _get_org(ctx)
    sdk = YaraSDK(org)
    data = sdk.list_sources()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# source-get
# ---------------------------------------------------------------------------

@group.command("source-get")
@click.option("--name", required=True, help="Source name.")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_SOURCE_GET),
    help="Show detailed explanation of this command.",
)
@pass_context
def source_get(ctx, name) -> None:
    """Get a YARA source by name.

    Example:
        limacharlie yara source-get --name my-source
    """
    org = _get_org(ctx)
    sdk = YaraSDK(org)
    data = sdk.get_source(name)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# source-add
# ---------------------------------------------------------------------------

@group.command("source-add")
@click.option("--name", required=True, help="Source name.")
@click.option(
    "--source-file", required=True, type=click.Path(exists=True),
    help="Path to YARA rule content file.",
)
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_SOURCE_ADD),
    help="Show detailed explanation of this command.",
)
@pass_context
def source_add(ctx, name, source_file) -> None:
    """Add or update a YARA source.

    Example:
        limacharlie yara source-add --name my-source --source-file rules.yar
    """
    with open(source_file, "r") as f:
        source_content = f.read()

    org = _get_org(ctx)
    sdk = YaraSDK(org)
    data = sdk.add_source(name, source_content)
    if not ctx.obj.quiet:
        click.echo(f"YARA source '{name}' added.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# source-delete
# ---------------------------------------------------------------------------

@group.command("source-delete")
@click.option("--name", required=True, help="Source name to delete.")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_SOURCE_DELETE),
    help="Show detailed explanation of this command.",
)
@pass_context
def source_delete(ctx, name) -> None:
    """Delete a YARA source.

    Example:
        limacharlie yara source-delete --name my-source
    """
    org = _get_org(ctx)
    sdk = YaraSDK(org)
    data = sdk.delete_source(name)
    if not ctx.obj.quiet:
        click.echo(f"YARA source '{name}' deleted.")
    _output(ctx, data)
