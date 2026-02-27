"""IOC search commands for LimaCharlie CLI v2.

Commands for searching Indicators of Compromise (IOCs) against
historical telemetry stored in LimaCharlie Insight.
"""

from __future__ import annotations

from typing import Any

import json
import sys

import click
import yaml

from ..cli import pass_context
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.insight import Insight
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


def _load_file(path: str) -> Any:
    """Load a JSON or YAML file and return parsed content."""
    with open(path, "r") as f:
        content = f.read()
    try:
        return yaml.safe_load(content)
    except Exception:
        pass
    return json.loads(content)


def _load_input(input_file: str | None) -> Any:
    """Load data from a file or stdin."""
    if input_file:
        return _load_file(input_file)
    if not sys.stdin.isatty():
        content = sys.stdin.read()
        try:
            return yaml.safe_load(content)
        except Exception:
            pass
        return json.loads(content)
    return None


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------

@click.group("ioc")
def group() -> None:
    """Search for Indicators of Compromise.

    Query the Insight data lake for IOCs (domains, IPs, file hashes,
    etc.) to determine which sensors have observed them.
    """


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------

_EXPLAIN_SEARCH = """\
Search for an Indicator of Compromise (IOC) across all sensors in the
organization.  This queries the Insight (1-year telemetry) data lake
for any sensor that has observed the specified IOC.

Supported --type values:
  domain       - DNS domain name (e.g. evil.com)
  ip           - IP address, v4 or v6 (e.g. 1.2.3.4)
  file_hash    - File hash, any algorithm (MD5/SHA1/SHA256)
  file_path    - Full file path
  file_name    - File name only (no directory)
  user         - User or account name
  service_name - Service/daemon name
  package_name - Installed package name

The result includes prevalence data showing which sensors observed
the IOC, how many times, and when (first/last seen).

Examples:
  limacharlie ioc search --type domain --value evil.com
  limacharlie ioc search --type ip --value 1.2.3.4
  limacharlie ioc search --type file_hash --value abc123...
"""
register_explain("ioc.search", _EXPLAIN_SEARCH)


@group.command()
@click.option("--type", "ioc_type", required=True, help="IOC type (domain, ip, file_hash, file_path, etc.).")
@click.option("--value", required=True, help="IOC value to search for.")
@pass_context
def search(ctx: click.Context, ioc_type: str, value: str) -> None:
    org = _get_org(ctx)
    insight = Insight(org)
    data = insight.search_ioc(ioc_type, value)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# batch-search
# ---------------------------------------------------------------------------

_EXPLAIN_BATCH_SEARCH = """\
Search for multiple IOCs at once using a JSON or YAML input file.
The file should map IOC types to lists of values:

    domain:
      - evil.com
      - bad.org
    ip:
      - 1.2.3.4
      - 5.6.7.8
    file_hash:
      - abc123def456...

Valid IOC types: domain, ip, file_hash, file_path, file_name, user,
service_name, package_name.

This is more efficient than running individual searches when you have
many IOCs to check.  Data can also be piped via stdin.

Example:
  limacharlie ioc batch-search --input-file iocs.json
  cat iocs.yaml | limacharlie ioc batch-search
"""
register_explain("ioc.batch-search", _EXPLAIN_BATCH_SEARCH)


@group.command("batch-search")
@click.option("--input-file", default=None, type=click.Path(exists=True), help="Path to JSON file with IOCs ({type: [values]}). Reads stdin if omitted.")
@pass_context
def batch_search(ctx: click.Context, input_file: str | None) -> None:
    data = _load_input(input_file)
    if data is None:
        click.echo(
            "Error: No input data provided.\n"
            "Suggestion: Use --input-file or pipe JSON to stdin.",
            err=True,
        )
        ctx.exit(4)
        return

    if not isinstance(data, dict):
        click.echo("Error: Input must be a JSON object mapping IOC types to lists of values.", err=True)
        ctx.exit(4)
        return

    org = _get_org(ctx)
    insight = Insight(org)
    result = insight.batch_search(data)
    _output(ctx, result)


# ---------------------------------------------------------------------------
# hosts
# ---------------------------------------------------------------------------

_EXPLAIN_HOSTS = """\
Find sensors by hostname prefix.  This searches the Insight data lake
for sensors whose hostname starts with the given string.  Useful for
discovering which SIDs correspond to a given machine name.

The search is prefix-based, so "srv-" matches srv-web01, srv-db02, etc.

Example:
  limacharlie ioc hosts --hostname workstation-01
  limacharlie ioc hosts --hostname srv-
"""
register_explain("ioc.hosts", _EXPLAIN_HOSTS)


@group.command()
@click.option("--hostname", required=True, help="Hostname prefix to search for.")
@pass_context
def hosts(ctx: click.Context, hostname: str) -> None:
    org = _get_org(ctx)
    data = org.find_sensors_by_hostname(hostname)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# enrich
# ---------------------------------------------------------------------------

_EXPLAIN_ENRICH = """\
Get enrichment/object information for an indicator.  This queries the
Insight data lake for detailed metadata about an observed object,
including related objects, first/last seen times, and context from
sensor telemetry.

Supported --type values: domain, ip, file_hash, file_path, file_name,
user, service_name, package_name.

Unlike "search" (which returns prevalence per sensor), "enrich" returns
the object's own metadata and relationships.

Examples:
  limacharlie ioc enrich --type domain --value evil.com
  limacharlie ioc enrich --type ip --value 1.2.3.4
  limacharlie ioc enrich --type file_hash --value abc123...
"""
register_explain("ioc.enrich", _EXPLAIN_ENRICH)


@group.command()
@click.option("--type", "obj_type", required=True, help="Indicator type (domain, ip, file_hash, file_path, file_name, user, service_name, package_name).")
@click.option("--value", required=True, help="Indicator value to look up.")
@pass_context
def enrich(ctx: click.Context, obj_type: str, value: str) -> None:
    org = _get_org(ctx)
    insight = Insight(org)
    data = insight.get_object_information(obj_type, value)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# batch-enrich
# ---------------------------------------------------------------------------

_EXPLAIN_BATCH_ENRICH = """\
Batch enrichment lookup from a JSON or YAML input file.  The format
is identical to batch-search -- a mapping of indicator types to lists
of values:

    domain:
      - evil.com
      - bad.org
    ip:
      - 1.2.3.4

Valid types: domain, ip, file_hash, file_path, file_name, user,
service_name, package_name.

Results include object metadata and relationships for each indicator.
Data can also be piped via stdin.

Example:
  limacharlie ioc batch-enrich --input-file indicators.json
  cat indicators.yaml | limacharlie ioc batch-enrich
"""
register_explain("ioc.batch-enrich", _EXPLAIN_BATCH_ENRICH)


@group.command("batch-enrich")
@click.option("--input-file", default=None, type=click.Path(exists=True), help="Path to JSON file with indicators ({type: [values]}). Reads stdin if omitted.")
@pass_context
def batch_enrich(ctx: click.Context, input_file: str | None) -> None:
    data = _load_input(input_file)
    if data is None:
        click.echo(
            "Error: No input data provided.\n"
            "Suggestion: Use --input-file or pipe JSON to stdin.",
            err=True,
        )
        ctx.exit(4)
        return

    if not isinstance(data, dict):
        click.echo("Error: Input must be a JSON object mapping indicator types to lists of values.", err=True)
        ctx.exit(4)
        return

    org = _get_org(ctx)
    insight = Insight(org)
    result = insight.batch_search(data)
    _output(ctx, result)
