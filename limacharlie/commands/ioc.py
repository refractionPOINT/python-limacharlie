"""IOC search commands for LimaCharlie CLI v2.

Commands for searching Indicators of Compromise (IOCs) against
historical telemetry stored in LimaCharlie Insight.
"""

import json
import sys

import click
import yaml

from ..cli import pass_context
from ..config import resolve_credentials
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.insight import Insight
from ..output import format_output, detect_output_format
from ..discovery import register_explain


# ---------------------------------------------------------------------------
# Explain texts
# ---------------------------------------------------------------------------

_EXPLAIN_SEARCH = """\
Search for an Indicator of Compromise (IOC) across all sensors in the
organization.  This queries the Insight data lake for any sensor that
has observed the specified IOC.

Supported IOC types include:
  domain, ip, file_hash, file_path, file_name, user, service_name,
  package_name, and more.

The result includes prevalence data showing which sensors observed
the IOC and when.

Examples:
  limacharlie ioc search --type domain --value evil.com
  limacharlie ioc search --type ip --value 1.2.3.4
  limacharlie ioc search --type file_hash --value abc123...
"""

_EXPLAIN_BATCH_SEARCH = """\
Search for multiple IOCs at once using a JSON input file.  The file
should be a JSON object mapping IOC types to lists of values:

  {
    "domain": ["evil.com", "bad.org"],
    "ip": ["1.2.3.4", "5.6.7.8"],
    "file_hash": ["abc123..."]
  }

This is more efficient than running individual searches when you have
many IOCs to check.

Example:
  limacharlie ioc batch-search --input-file iocs.json
"""

_EXPLAIN_HOSTS = """\
Find sensors by hostname prefix.  This searches the Insight data lake
for sensors whose hostname matches the given prefix.

This is equivalent to searching for IOC type "hostname".

Example:
  limacharlie ioc hosts --hostname workstation-01
  limacharlie ioc hosts --hostname srv-
"""

_EXPLAIN_ENRICH = """\
Get enrichment/object information for an indicator.  This queries the
Insight data lake for detailed information about an observed object.

Supported types: domain, ip, file_hash, file_path, file_name, user,
service_name, package_name.

Examples:
  limacharlie ioc enrich --type domain --value evil.com
  limacharlie ioc enrich --type ip --value 1.2.3.4
  limacharlie ioc enrich --type file_hash --value abc123...
"""

_EXPLAIN_BATCH_ENRICH = """\
Batch enrichment lookup from a JSON input file.  The file should be a
JSON object mapping indicator types to lists of values, identical to
the format used by batch-search:

  {
    "domain": ["evil.com", "bad.org"],
    "ip": ["1.2.3.4"]
  }

Results include object information for each indicator in the batch.

Example:
  limacharlie ioc batch-enrich --input-file indicators.json
"""

register_explain("ioc.search", _EXPLAIN_SEARCH)
register_explain("ioc.batch-search", _EXPLAIN_BATCH_SEARCH)
register_explain("ioc.hosts", _EXPLAIN_HOSTS)
register_explain("ioc.enrich", _EXPLAIN_ENRICH)
register_explain("ioc.batch-enrich", _EXPLAIN_BATCH_ENRICH)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_explain_callback(text):
    def callback(ctx, param, value):
        if value:
            click.echo(text.strip())
            ctx.exit()
    return callback


def _output(ctx, data):
    fmt = ctx.obj.output_format or detect_output_format()
    if not ctx.obj.quiet:
        click.echo(format_output(data, fmt))


def _get_org(ctx):
    creds = resolve_credentials(oid=ctx.obj.oid, environment=ctx.obj.environment)
    client = Client(oid=creds["oid"], api_key=creds.get("api_key"), uid=creds.get("uid"))
    return Organization(client)


def _load_file(path):
    """Load a JSON or YAML file and return parsed content."""
    with open(path, "r") as f:
        content = f.read()
    try:
        return yaml.safe_load(content)
    except Exception:
        pass
    return json.loads(content)


def _load_input(input_file):
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
def group():
    """Search for Indicators of Compromise.

    Query the Insight data lake for IOCs (domains, IPs, file hashes,
    etc.) to determine which sensors have observed them.
    """


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------

@group.command()
@click.option("--type", "ioc_type", required=True, help="IOC type (domain, ip, file_hash, file_path, etc.).")
@click.option("--value", required=True, help="IOC value to search for.")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_SEARCH),
    help="Show detailed explanation of this command.",
)
@pass_context
def search(ctx, ioc_type, value):
    """Search for an IOC.

    Examples:
        limacharlie ioc search --type domain --value evil.com
        limacharlie ioc search --type ip --value 1.2.3.4
    """
    org = _get_org(ctx)
    insight = Insight(org)
    data = insight.search_ioc(ioc_type, value)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# batch-search
# ---------------------------------------------------------------------------

@group.command("batch-search")
@click.option("--input-file", default=None, type=click.Path(exists=True), help="Path to JSON file with IOCs ({type: [values]}). Reads stdin if omitted.")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_BATCH_SEARCH),
    help="Show detailed explanation of this command.",
)
@pass_context
def batch_search(ctx, input_file):
    """Batch IOC search from a JSON file.

    The input file should map IOC types to lists of values:
      {"domain": ["evil.com"], "ip": ["1.2.3.4"]}

    Example:
        limacharlie ioc batch-search --input-file iocs.json
    """
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

@group.command()
@click.option("--hostname", required=True, help="Hostname prefix to search for.")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_HOSTS),
    help="Show detailed explanation of this command.",
)
@pass_context
def hosts(ctx, hostname):
    """Find sensors by hostname prefix.

    Examples:
        limacharlie ioc hosts --hostname workstation-01
        limacharlie ioc hosts --hostname srv-
    """
    org = _get_org(ctx)
    data = org.find_sensors_by_hostname(hostname)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# enrich
# ---------------------------------------------------------------------------

@group.command()
@click.option("--type", "obj_type", required=True, help="Indicator type (domain, ip, file_hash, file_path, file_name, user, service_name, package_name).")
@click.option("--value", required=True, help="Indicator value to look up.")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_ENRICH),
    help="Show detailed explanation of this command.",
)
@pass_context
def enrich(ctx, obj_type, value):
    """Get enrichment info for an indicator.

    Examples:
        limacharlie ioc enrich --type domain --value evil.com
        limacharlie ioc enrich --type ip --value 1.2.3.4
    """
    org = _get_org(ctx)
    insight = Insight(org)
    data = insight.get_object_information(obj_type, value)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# batch-enrich
# ---------------------------------------------------------------------------

@group.command("batch-enrich")
@click.option("--input-file", default=None, type=click.Path(exists=True), help="Path to JSON file with indicators ({type: [values]}). Reads stdin if omitted.")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_BATCH_ENRICH),
    help="Show detailed explanation of this command.",
)
@pass_context
def batch_enrich(ctx, input_file):
    """Batch enrichment lookup from a JSON file.

    The input file should map indicator types to lists of values:
      {"domain": ["evil.com"], "ip": ["1.2.3.4"]}

    Example:
        limacharlie ioc batch-enrich --input-file indicators.json
    """
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
