"""Organization commands for LimaCharlie CLI v2.

Commands for viewing and managing organization settings, configuration,
errors, usage statistics, and MITRE ATT&CK coverage.
"""

from __future__ import annotations

from typing import Any

import click

from ..cli import pass_context
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

Common configuration keys:
  vt               - VirusTotal API key for hash lookups
  retention        - Telemetry retention period (days)
  sensor_version   - Target sensor version for the org
  twilio_*         - Twilio integration credentials
  otx_key          - AlienVault OTX API key

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

_EXPLAIN_URLS = """\
Display the service URLs for the organization.  These URLs are used by
sensors and integrations to communicate with the LimaCharlie platform.
This is useful for network configuration, firewall rules, and verifying
that sensors are pointed at the correct endpoints.
"""

_EXPLAIN_CREATE = """\
Create a new organization.  You must provide a name and a data center
location.  Optionally supply a template name to bootstrap the
organization with preconfigured rules and outputs.

Available locations: usa, canada, europe, uk, india, australia, auto
Templates bootstrap the org with starter D&R rules and outputs.

The API returns the new organization's OID on success.  After creation,
set it as default with 'limacharlie auth use-org <OID>'.
"""

_EXPLAIN_DELETE = """\
Delete an organization.  This is a two-step process for safety.  First
call without --confirm-token to obtain a confirmation token.  Then call
again with --confirm-token <token> to perform the actual deletion.

WARNING: This action is irreversible.  All sensors, rules, data, and
configuration will be permanently destroyed.
"""

_EXPLAIN_RENAME = """\
Rename an organization.  The new name must be unique across LimaCharlie.
Use 'limacharlie org check-name' to verify availability before renaming.
"""

_EXPLAIN_QUOTA = """\
Set the sensor quota for the organization.  The quota limits how many
sensors can be enrolled simultaneously.  Set to 0 to remove the quota
limit (billing still applies).
"""

_EXPLAIN_SCHEMA = """\
Retrieve event schemas for the organization.  Without options, returns
the full schema list.  Use --event-type to get the schema for a single
event type, or --platform to filter schemas by platform.
"""

_EXPLAIN_RUNTIME_METADATA = """\
Retrieve runtime metadata for the organization.  Runtime metadata
describes the dynamic state of various platform entities such as
services and extensions.  Optionally filter by --entity-type and
--entity-name.
"""

_EXPLAIN_CHECK_NAME = """\
Check whether an organization name is available.  Returns availability
information for the given name.  Use this before creating or renaming
an organization to avoid name conflicts.
"""

register_explain("org.info", _EXPLAIN_INFO)
register_explain("org.list", _EXPLAIN_LIST)
register_explain("org.config-get", _EXPLAIN_CONFIG_GET)
register_explain("org.config-set", _EXPLAIN_CONFIG_SET)
register_explain("org.errors", _EXPLAIN_ERRORS)
register_explain("org.dismiss-error", _EXPLAIN_DISMISS_ERROR)
register_explain("org.stats", _EXPLAIN_STATS)
register_explain("org.mitre", _EXPLAIN_MITRE)
register_explain("org.urls", _EXPLAIN_URLS)
register_explain("org.create", _EXPLAIN_CREATE)
register_explain("org.delete", _EXPLAIN_DELETE)
register_explain("org.rename", _EXPLAIN_RENAME)
register_explain("org.quota", _EXPLAIN_QUOTA)
register_explain("org.schema", _EXPLAIN_SCHEMA)
register_explain("org.runtime-metadata", _EXPLAIN_RUNTIME_METADATA)
register_explain("org.check-name", _EXPLAIN_CHECK_NAME)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _output(ctx: click.Context, data: Any) -> None:
    fmt = ctx.obj.output_format or detect_output_format()
    if not ctx.obj.quiet:
        click.echo(format_output(data, fmt))


def _get_client(ctx: click.Context) -> Client:
    return Client(oid=ctx.obj.oid, environment=ctx.obj.environment)


def _get_org(ctx: click.Context) -> Organization:
    client = _get_client(ctx)
    return Organization(client)


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------

@click.group("org")
def group() -> None:
    """View and manage organization settings.

    Inspect organization details, configuration values, errors, usage
    statistics, and MITRE ATT&CK coverage.
    """


# ---------------------------------------------------------------------------
# info
# ---------------------------------------------------------------------------

@group.command()
@pass_context
def info(ctx: click.Context) -> None:
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
@pass_context
def list_orgs(ctx: click.Context, filter_text: str | None, limit: int | None, offset: int | None) -> None:
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
@pass_context
def config_get(ctx: click.Context, name: str) -> None:
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
@pass_context
def config_set(ctx: click.Context, name: str, value: str) -> None:
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
@pass_context
def errors(ctx: click.Context) -> None:
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
@pass_context
def dismiss_error(ctx: click.Context, component: str) -> None:
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
@pass_context
def stats(ctx: click.Context) -> None:
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
@pass_context
def mitre(ctx: click.Context) -> None:
    """Get MITRE ATT&CK coverage report.

    Analyzes deployed D&R rules and maps them to MITRE ATT&CK techniques.

    Example:
        limacharlie org mitre
    """
    org = _get_org(ctx)
    data = org.get_mitre_report()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# urls
# ---------------------------------------------------------------------------

@group.command()
@pass_context
def urls(ctx: click.Context) -> None:
    """Show service URLs for the organization.

    Example:
        limacharlie org urls
    """
    org = _get_org(ctx)
    data = org.get_urls()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------

@group.command()
@click.option("--name", required=True, help="Name for the new organization.")
@click.option("--location", required=True, help="Data center location (e.g. usa, canada, europe, uk, india, australia, auto).")
@click.option("--template", default=None, help="Optional template name to bootstrap the organization.")
@pass_context
def create(ctx: click.Context, name: str, location: str, template: str | None) -> None:
    """Create a new organization.

    Example:
        limacharlie org create --name my-org --location usa
        limacharlie org create --name my-org --location europe --template default
    """
    client = _get_client(ctx)
    data = Organization.create_org(client, name, location, template)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

@group.command()
@click.option("--confirm-token", default=None, help="Confirmation token from initial delete call.")
@pass_context
def delete(ctx: click.Context, confirm_token: str | None) -> None:
    """Delete an organization (two-step process).

    First call without --confirm-token to obtain a confirmation token.
    Then call again with --confirm-token <token> to perform the deletion.

    Examples:
        limacharlie org delete
        limacharlie org delete --confirm-token <token>
    """
    org = _get_org(ctx)
    data = org.delete_org(confirm_token)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# rename
# ---------------------------------------------------------------------------

@group.command()
@click.option("--name", required=True, help="New organization name.")
@pass_context
def rename(ctx: click.Context, name: str) -> None:
    """Rename the organization.

    Example:
        limacharlie org rename --name new-org-name
    """
    org = _get_org(ctx)
    data = org.rename(name)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# quota
# ---------------------------------------------------------------------------

@group.command()
@click.option("--quota", required=True, type=int, help="Sensor quota (0 to remove limit).")
@pass_context
def quota(ctx: click.Context, quota: int) -> None:
    """Set the sensor quota for the organization.

    Example:
        limacharlie org quota --quota 1000
        limacharlie org quota --quota 0
    """
    org = _get_org(ctx)
    data = org.set_quota(quota)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# schema
# ---------------------------------------------------------------------------

@group.command()
@click.option("--event-type", default=None, help="Specific event type to retrieve schema for.")
@click.option("--platform", default=None, help="Platform to filter schemas by.")
@pass_context
def schema(ctx: click.Context, event_type: str | None, platform: str | None) -> None:
    """Get event schemas for the organization.

    Without options, returns all schemas.  Use --event-type for a single
    event type or --platform to filter by platform.

    Example:
        limacharlie org schema
        limacharlie org schema --event-type NEW_PROCESS
        limacharlie org schema --platform windows
    """
    org = _get_org(ctx)
    if event_type:
        data = org.get_schema(event_type)
    else:
        data = org.get_schemas(platform)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# runtime-metadata
# ---------------------------------------------------------------------------

@group.command("runtime-metadata")
@click.option("--entity-type", default=None, help="Entity type to filter by.")
@click.option("--entity-name", default=None, help="Entity name to filter by.")
@pass_context
def runtime_metadata(ctx: click.Context, entity_type: str | None, entity_name: str | None) -> None:
    """Get runtime metadata for the organization.

    Example:
        limacharlie org runtime-metadata
        limacharlie org runtime-metadata --entity-type service
        limacharlie org runtime-metadata --entity-type service --entity-name my-svc
    """
    org = _get_org(ctx)
    data = org.get_runtime_metadata(entity_type, entity_name)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# check-name
# ---------------------------------------------------------------------------

@group.command("check-name")
@click.option("--name", required=True, help="Organization name to check availability for.")
@pass_context
def check_name(ctx: click.Context, name: str) -> None:
    """Check if an organization name is available.

    Example:
        limacharlie org check-name --name my-org
    """
    client = _get_client(ctx)
    data = Organization.check_name(client, name)
    _output(ctx, data)
