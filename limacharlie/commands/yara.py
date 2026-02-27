"""YARA commands for LimaCharlie CLI v2.

Commands for YARA scanning, rule management, and source management.
YARA rules can be deployed to sensors for real-time scanning or
used for ad-hoc scans against specific sensors.
"""

from __future__ import annotations

from typing import Any

import click

from ..cli import pass_context
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.yara import Yara as YaraSDK
from ..output import format_output, detect_output_format
from ..discovery import register_explain


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

_EXPLAIN_SCAN = """\
Run an ad-hoc YARA scan on a specific sensor.  Provide the sensor
ID and a file containing YARA rule content.

The rule file should contain standard YARA rule syntax, for example:

    rule SuspiciousString {
        strings:
            $s1 = "malware" nocase
        condition:
            any of them
    }

A single file can contain multiple YARA rules.  The scan is executed
on the target sensor and matching results are returned.

Alternatively, rules stored in the yara hive can be referenced in
D&R rules or sensor commands via hive://yara/<rule-name> without
needing this ad-hoc scan command.

Example:
  limacharlie yara scan --sid <sensor-id> --rule-file rules.yar
"""
register_explain("yara.scan", _EXPLAIN_SCAN)


@group.command()
@click.option("--sid", required=True, help="Sensor ID to scan.")
@click.option(
    "--rule-file", required=True, type=click.Path(exists=True),
    help="Path to YARA rule file.",
)
@pass_context
def scan(ctx, sid, rule_file) -> None:
    with open(rule_file, "r") as f:
        rule_content = f.read()

    org = _get_org(ctx)
    sdk = YaraSDK(org)
    data = sdk.scan(sid, rule_content)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# rules-list
# ---------------------------------------------------------------------------

_EXPLAIN_RULES_LIST = """\
List all deployed YARA rules in the organization.  These are rules
that have been added for continuous or scheduled scanning via the
ext-yara extension.

Each rule has a name and a list of sources (URLs or ARLs) that
the YARA manager syncs every 24 hours.  Rules stored in the yara
hive can be referenced by sensors as hive://yara/<rule-name>.
"""
register_explain("yara.rules-list", _EXPLAIN_RULES_LIST)


@group.command("rules-list")
@pass_context
def rules_list(ctx) -> None:
    org = _get_org(ctx)
    sdk = YaraSDK(org)
    data = sdk.list_rules()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# rule-add
# ---------------------------------------------------------------------------

_EXPLAIN_RULE_ADD = """\
Add a YARA rule for deployment via the ext-yara extension.  The
--sources-file should contain a JSON or YAML list of YARA source
references.  Each source is a URL or ARL pointing to YARA rule
content that will be synced every 24 hours.

Sources file format (YAML):

    - "https://raw.githubusercontent.com/Yara-Rules/rules/master/email/Email_generic_phishing.yar"
    - "[github,Yara-Rules/rules/email]"
    - "[github,my-org/my-repo/path/to/rules,token,<github-pat>]"

Source types:
  Direct URL   - HTTPS link to a single .yar file
  GitHub ARL   - [github,org/repo/path] fetches a file or directory
  Predefined   - LimaCharlie-curated rule sets (via the GUI)

After adding, click "Manual Sync" in the GUI or wait 24h for auto-sync.

Example:
  limacharlie yara rule-add --name my-rule --sources-file sources.yaml
"""
register_explain("yara.rule-add", _EXPLAIN_RULE_ADD)


@group.command("rule-add")
@click.option("--name", required=True, help="Rule name.")
@click.option(
    "--sources-file", required=True, type=click.Path(exists=True),
    help="Path to sources definition file (JSON or YAML).",
)
@pass_context
def rule_add(ctx, name, sources_file) -> None:
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

_EXPLAIN_RULE_DELETE = """\
Delete a deployed YARA rule by name.

Example:
  limacharlie yara rule-delete --name my-rule
"""
register_explain("yara.rule-delete", _EXPLAIN_RULE_DELETE)


@group.command("rule-delete")
@click.option("--name", required=True, help="Rule name to delete.")
@pass_context
def rule_delete(ctx, name) -> None:
    org = _get_org(ctx)
    sdk = YaraSDK(org)
    data = sdk.delete_rule(name)
    if not ctx.obj.quiet:
        click.echo(f"YARA rule '{name}' deleted.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# sources-list
# ---------------------------------------------------------------------------

_EXPLAIN_SOURCES_LIST = """\
List all YARA sources stored in the yara hive.  Sources are named
records whose data payload contains YARA rule content under a "rule"
key:

    data:
      rule: |
        rule MyRule { strings: $s = "test" condition: $s }

Sources can be referenced by sensors for scanning via
hive://yara/<source-name>, or managed by the ext-yara extension.
"""
register_explain("yara.sources-list", _EXPLAIN_SOURCES_LIST)


@group.command("sources-list")
@pass_context
def sources_list(ctx) -> None:
    org = _get_org(ctx)
    sdk = YaraSDK(org)
    data = sdk.list_sources()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# source-get
# ---------------------------------------------------------------------------

_EXPLAIN_SOURCE_GET = """\
Get the content of a specific YARA source by name from the yara
hive.  Returns the record data which contains the YARA rule text
in the "rule" key.

Example:
  limacharlie yara source-get --name my-source
"""
register_explain("yara.source-get", _EXPLAIN_SOURCE_GET)


@group.command("source-get")
@click.option("--name", required=True, help="Source name.")
@pass_context
def source_get(ctx, name) -> None:
    org = _get_org(ctx)
    sdk = YaraSDK(org)
    data = sdk.get_source(name)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# source-add
# ---------------------------------------------------------------------------

_EXPLAIN_SOURCE_ADD = """\
Add or update a YARA source in the yara hive.  The --source-file
should contain valid YARA rule content (one or more rules).  The
content is stored under the "rule" key in the hive record.

A single source file can contain multiple YARA rules.  Once stored,
the source can be referenced for scanning via
hive://yara/<source-name>.

Example:
  limacharlie yara source-add --name my-source --source-file rules.yar
"""
register_explain("yara.source-add", _EXPLAIN_SOURCE_ADD)


@group.command("source-add")
@click.option("--name", required=True, help="Source name.")
@click.option(
    "--source-file", required=True, type=click.Path(exists=True),
    help="Path to YARA rule content file.",
)
@pass_context
def source_add(ctx, name, source_file) -> None:
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

_EXPLAIN_SOURCE_DELETE = """\
Delete a YARA source by name.

Example:
  limacharlie yara source-delete --name my-source
"""
register_explain("yara.source-delete", _EXPLAIN_SOURCE_DELETE)


@group.command("source-delete")
@click.option("--name", required=True, help="Source name to delete.")
@pass_context
def source_delete(ctx, name) -> None:
    org = _get_org(ctx)
    sdk = YaraSDK(org)
    data = sdk.delete_source(name)
    if not ctx.obj.quiet:
        click.echo(f"YARA source '{name}' deleted.")
    _output(ctx, data)
