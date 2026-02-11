"""Organization commands for LimaCharlie CLI v2.

Commands for viewing and managing organization settings, configuration,
errors, usage statistics, and MITRE ATT&CK coverage.
"""

import click

from ..cli import pass_context
from ..config import resolve_credentials
from ..client import Client
from ..sdk.organization import Organization
from ..output import format_output, detect_output_format
from ..discovery import register_explain


# ---------------------------------------------------------------------------
# Explain texts
# ---------------------------------------------------------------------------

_EXPLAIN_INFO = """\
Display organization details including the organization name, sensor count,
current sensor version, quotas, and creation date.  This is useful for
quickly verifying you are connected to the correct organization and
checking the overall health of the deployment.
"""

_EXPLAIN_LIST = """\
List all organizations that the current credentials have access to.  For
user-scoped API keys or OAuth credentials this may return many
organizations.  For org-scoped API keys this typically returns only the
one organization the key belongs to.

Results include the OID and human-readable name of each organization.
Use --filter to search for organizations by name substring.
"""

_EXPLAIN_CONFIG_GET = """\
Retrieve an organization configuration value by name.  Organization
configuration values control platform behavior such as retention periods,
sensor version pinning, and feature flags.

Use 'limacharlie org config-set' to change a configuration value.
"""

_EXPLAIN_CONFIG_SET = """\
Set an organization configuration value.  Configuration values control
platform behavior.  Changes take effect immediately and are audited.

Common configuration keys include vt (VirusTotal integration),
retention (telemetry retention period), and sensor version settings.
Use with caution as incorrect values may affect sensor behavior.
"""

_EXPLAIN_ERRORS = """\
List current organization errors.  LimaCharlie surfaces errors from
outputs, extensions, cloud sensors, and other components when they
encounter issues.  Reviewing errors regularly helps ensure your
integrations are functioning correctly.

Use 'limacharlie org dismiss-error --component <name>' to acknowledge
and dismiss an error after investigating it.
"""

_EXPLAIN_DISMISS_ERROR = """\
Dismiss an organization error by component name.  This acknowledges the
error and removes it from the error list.  The error may reappear if
the underlying issue is not resolved.  Use 'limacharlie org errors' to
see current errors and their component names.
"""

_EXPLAIN_STATS = """\
Display usage statistics for the organization including sensor counts,
event volumes, detection counts, and billing-relevant metrics.  This is
useful for capacity planning, cost monitoring, and verifying that
sensors are sending telemetry as expected.
"""

_EXPLAIN_MITRE = """\
Generate a MITRE ATT&CK coverage report for the organization.  This
analyzes the deployed D&R rules and maps them to MITRE ATT&CK
techniques, showing which techniques are covered and which have gaps.

The report is useful for security posture assessment, compliance
reporting, and identifying areas where additional detection rules
should be created.
"""

register_explain("org.info", _EXPLAIN_INFO)
register_explain("org.list", _EXPLAIN_LIST)
register_explain("org.config-get", _EXPLAIN_CONFIG_GET)
register_explain("org.config-set", _EXPLAIN_CONFIG_SET)
register_explain("org.errors", _EXPLAIN_ERRORS)
register_explain("org.dismiss-error", _EXPLAIN_DISMISS_ERROR)
register_explain("org.stats", _EXPLAIN_STATS)
register_explain("org.mitre", _EXPLAIN_MITRE)


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


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------

@click.group("org")
def group():
    """View and manage organization settings.

    Inspect organization details, configuration values, errors, usage
    statistics, and MITRE ATT&CK coverage.
    """


# ---------------------------------------------------------------------------
# info
# ---------------------------------------------------------------------------

@group.command()
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_INFO),
    help="Show detailed explanation of this command.",
)
@pass_context
def info(ctx):
    """Show organization details (name, sensor count, version, quotas).

    Example:
        limacharlie org info
    """
    org = _get_org(ctx)
    data = org.get_info()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

@group.command("list")
@click.option("--filter", "filter_text", default=None, help="Case-insensitive name filter.")
@click.option("--limit", default=None, type=int, help="Maximum number of results.")
@click.option("--offset", default=None, type=int, help="Pagination offset.")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_LIST),
    help="Show detailed explanation of this command.",
)
@pass_context
def list_orgs(ctx, filter_text, limit, offset):
    """List organizations accessible to the current credentials.

    Example:
        limacharlie org list
        limacharlie org list --filter production
    """
    org = _get_org(ctx)
    data = org.list_accessible_orgs(offset=offset, limit=limit, filter_text=filter_text)

    # Build a user-friendly list
    orgs = data.get("orgs", [])
    names = data.get("names", {})
    result = [{"oid": oid, "name": names.get(oid, "")} for oid in orgs]
    _output(ctx, result)


# ---------------------------------------------------------------------------
# config-get
# ---------------------------------------------------------------------------

@group.command("config-get")
@click.option("--name", required=True, help="Configuration key name to retrieve.")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_CONFIG_GET),
    help="Show detailed explanation of this command.",
)
@pass_context
def config_get(ctx, name):
    """Get an organization configuration value.

    Example:
        limacharlie org config-get --name vt
    """
    org = _get_org(ctx)
    data = org.get_config(name)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# config-set
# ---------------------------------------------------------------------------

@group.command("config-set")
@click.option("--name", required=True, help="Configuration key name to set.")
@click.option("--value", required=True, help="Configuration value.")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_CONFIG_SET),
    help="Show detailed explanation of this command.",
)
@pass_context
def config_set(ctx, name, value):
    """Set an organization configuration value.

    Example:
        limacharlie org config-set --name vt --value <api-key>
    """
    org = _get_org(ctx)
    data = org.set_config(name, value)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# errors
# ---------------------------------------------------------------------------

@group.command()
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_ERRORS),
    help="Show detailed explanation of this command.",
)
@pass_context
def errors(ctx):
    """List current organization errors.

    Example:
        limacharlie org errors
    """
    org = _get_org(ctx)
    data = org.get_errors()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# dismiss-error
# ---------------------------------------------------------------------------

@group.command("dismiss-error")
@click.option("--component", required=True, help="Error component name to dismiss.")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_DISMISS_ERROR),
    help="Show detailed explanation of this command.",
)
@pass_context
def dismiss_error(ctx, component):
    """Dismiss an organization error by component name.

    Example:
        limacharlie org dismiss-error --component syslog-output
    """
    org = _get_org(ctx)
    data = org.dismiss_error(component)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------

@group.command()
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_STATS),
    help="Show detailed explanation of this command.",
)
@pass_context
def stats(ctx):
    """Show usage statistics for the organization.

    Example:
        limacharlie org stats
    """
    org = _get_org(ctx)
    data = org.get_stats()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# mitre
# ---------------------------------------------------------------------------

@group.command()
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_MITRE),
    help="Show detailed explanation of this command.",
)
@pass_context
def mitre(ctx):
    """Get MITRE ATT&CK coverage report.

    Analyzes deployed D&R rules and maps them to MITRE ATT&CK techniques.

    Example:
        limacharlie org mitre
    """
    org = _get_org(ctx)
    data = org.get_mitre_report()
    _output(ctx, data)
