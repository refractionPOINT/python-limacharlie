"""Organization commands for LimaCharlie CLI v2.

Commands for viewing and managing organization settings, configuration,
errors, usage statistics, and MITRE ATT&CK coverage.
"""

from __future__ import annotations

from typing import Any

import click

from ..cli import pass_context
from ..client import Client
from ..config import load_config, save_config
from ..sdk.organization import Organization
from ..output import format_output, detect_output_format
from ..discovery import register_explain


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _output(ctx: click.Context, data: Any) -> None:
    fmt = ctx.obj.output_format or detect_output_format()
    if not ctx.obj.quiet:
        click.echo(format_output(data, fmt))


def _get_client(ctx: click.Context) -> Client:
    return Client(oid=ctx.obj.oid, environment=ctx.obj.environment, print_debug_fn=ctx.obj.debug_fn, debug_full_response=ctx.obj.debug_full, debug_curl=ctx.obj.debug_curl, debug_verbose=ctx.obj.debug_verbose)


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

_EXPLAIN_INFO = """\
Display organization details including the organization name, sensor count,
current sensor version, quotas, and creation date.  This is useful for
quickly verifying you are connected to the correct organization and
checking the overall health of the deployment.
"""
register_explain("org.info", _EXPLAIN_INFO)


@group.command()
@pass_context
def info(ctx: click.Context) -> None:
    org = _get_org(ctx)
    data = org.get_info()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

_EXPLAIN_LIST = """\
List all organizations that the current credentials have access to.  For
user-scoped API keys or OAuth credentials this may return many
organizations.  For org-scoped API keys this typically returns only the
one organization the key belongs to.

Results include the OID and human-readable name of each organization.
Use --filter to search for organizations by name substring.
"""
register_explain("org.list", _EXPLAIN_LIST)


@group.command("list")
@click.option("--filter", "filter_text", default=None, help="Case-insensitive name filter.")
@click.option("--limit", default=None, type=int, help="Maximum number of results.")
@click.option("--offset", default=None, type=int, help="Pagination offset.")
@pass_context
def list_orgs(ctx: click.Context, filter_text: str | None, limit: int | None, offset: int | None) -> None:
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

_EXPLAIN_CONFIG_GET = """\
Retrieve an organization configuration value by name.  Organization
configuration values control platform behavior such as retention periods,
sensor version pinning, and feature flags.

Use 'limacharlie org config-set' to change a configuration value.
"""
register_explain("org.config-get", _EXPLAIN_CONFIG_GET)


@group.command("config-get")
@click.option("--name", required=True, help="Configuration key name to retrieve.")
@pass_context
def config_get(ctx: click.Context, name: str) -> None:
    org = _get_org(ctx)
    data = org.get_config(name)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# config-set
# ---------------------------------------------------------------------------

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
register_explain("org.config-set", _EXPLAIN_CONFIG_SET)


@group.command("config-set")
@click.option("--name", required=True, help="Configuration key name to set.")
@click.option("--value", required=True, help="Configuration value.")
@pass_context
def config_set(ctx: click.Context, name: str, value: str) -> None:
    org = _get_org(ctx)
    data = org.set_config(name, value)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# errors
# ---------------------------------------------------------------------------

_EXPLAIN_ERRORS = """\
List current organization errors.  LimaCharlie surfaces errors from
outputs, extensions, cloud sensors, and other components when they
encounter issues.  Reviewing errors regularly helps ensure your
integrations are functioning correctly.

Use 'limacharlie org dismiss-error --component <name>' to acknowledge
and dismiss an error after investigating it.
"""
register_explain("org.errors", _EXPLAIN_ERRORS)


@group.command()
@pass_context
def errors(ctx: click.Context) -> None:
    org = _get_org(ctx)
    data = org.get_errors()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# dismiss-error
# ---------------------------------------------------------------------------

_EXPLAIN_DISMISS_ERROR = """\
Dismiss an organization error by component name.  This acknowledges the
error and removes it from the error list.  The error may reappear if
the underlying issue is not resolved.  Use 'limacharlie org errors' to
see current errors and their component names.
"""
register_explain("org.dismiss-error", _EXPLAIN_DISMISS_ERROR)


@group.command("dismiss-error")
@click.option("--component", required=True, help="Error component name to dismiss.")
@pass_context
def dismiss_error(ctx: click.Context, component: str) -> None:
    org = _get_org(ctx)
    data = org.dismiss_error(component)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------

_EXPLAIN_STATS = """\
Display usage statistics for the organization including sensor counts,
event volumes, detection counts, and billing-relevant metrics.  This is
useful for capacity planning, cost monitoring, and verifying that
sensors are sending telemetry as expected.
"""
register_explain("org.stats", _EXPLAIN_STATS)


@group.command()
@pass_context
def stats(ctx: click.Context) -> None:
    org = _get_org(ctx)
    data = org.get_stats()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# mitre
# ---------------------------------------------------------------------------

_EXPLAIN_MITRE = """\
Generate a MITRE ATT&CK coverage report for the organization.  This
analyzes the deployed D&R rules and maps them to MITRE ATT&CK
techniques, showing which techniques are covered and which have gaps.

The report is useful for security posture assessment, compliance
reporting, and identifying areas where additional detection rules
should be created.
"""
register_explain("org.mitre", _EXPLAIN_MITRE)


@group.command()
@pass_context
def mitre(ctx: click.Context) -> None:
    org = _get_org(ctx)
    data = org.get_mitre_report()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# urls
# ---------------------------------------------------------------------------

_EXPLAIN_URLS = """\
Display the service URLs for the organization.  These URLs are used by
sensors and integrations to communicate with the LimaCharlie platform.
This is useful for network configuration, firewall rules, and verifying
that sensors are pointed at the correct endpoints.
"""
register_explain("org.urls", _EXPLAIN_URLS)


@group.command()
@pass_context
def urls(ctx: click.Context) -> None:
    org = _get_org(ctx)
    data = org.get_urls()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------

_EXPLAIN_CREATE = """\
Create a new organization.  You must provide a name and a data center
location.  Optionally supply a template name to bootstrap the
organization with preconfigured rules and outputs.

Available locations: usa, canada, europe, uk, india, australia, auto
Templates bootstrap the org with starter D&R rules and outputs.

The API returns the new organization's OID on success.  After creation,
set it as default with 'limacharlie auth use-org <OID>'.
"""
register_explain("org.create", _EXPLAIN_CREATE)


@group.command()
@click.option("--name", required=True, help="Name for the new organization.")
@click.option("--location", default="auto", help="Data center location (usa, canada, europe, uk, india, australia, auto). Defaults to auto.")
@click.option("--template", default=None, help="Optional template name to bootstrap the organization.")
@click.option("--use", is_flag=True, default=False, help="Set the new organization as the default for subsequent commands.")
@pass_context
def create(ctx: click.Context, name: str, location: str, template: str | None, use: bool) -> None:
    client = Client(oid="-", environment=ctx.obj.environment, print_debug_fn=ctx.obj.debug_fn, debug_full_response=ctx.obj.debug_full, debug_curl=ctx.obj.debug_curl, debug_verbose=ctx.obj.debug_verbose)
    data = Organization.create_org(client, name, location, template)
    _output(ctx, data)

    # Show the web app URL for the new org on success.
    oid = None
    inner = data.get("data") if isinstance(data, dict) else None
    if isinstance(inner, dict):
        oid = inner.get("oid")
    elif isinstance(inner, str):
        try:
            import json
            oid = json.loads(inner).get("oid")
        except (ValueError, AttributeError):
            pass
    if oid and not ctx.obj.quiet:
        click.echo(f"\nOrganization URL: https://app.limacharlie.io/orgs/{oid}")

    if use and oid:
        env_name = ctx.obj.environment or "default"
        config = load_config() or {}
        if env_name == "default":
            config["oid"] = oid
        else:
            config.setdefault("env", {})
            config["env"].setdefault(env_name, {})
            config["env"][env_name]["oid"] = oid
        save_config(config)
        if not ctx.obj.quiet:
            click.echo(f"Default organization set to {oid} (environment '{env_name}').")


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

_EXPLAIN_DELETE = """\
Delete an organization.  This is a two-step process for safety.  First
call without --confirm-token to obtain a confirmation token.  Then call
again with --confirm-token <token> to perform the actual deletion.

WARNING: This action is irreversible.  All sensors, rules, data, and
configuration will be permanently destroyed.
"""
register_explain("org.delete", _EXPLAIN_DELETE)


@group.command()
@click.option("--confirm-token", default=None, help="Confirmation token from initial delete call.")
@pass_context
def delete(ctx: click.Context, confirm_token: str | None) -> None:
    org = _get_org(ctx)
    data = org.delete_org(confirm_token)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# rename
# ---------------------------------------------------------------------------

_EXPLAIN_RENAME = """\
Rename an organization.  The new name must be unique across LimaCharlie.
Use 'limacharlie org check-name' to verify availability before renaming.
"""
register_explain("org.rename", _EXPLAIN_RENAME)


@group.command()
@click.option("--name", required=True, help="New organization name.")
@pass_context
def rename(ctx: click.Context, name: str) -> None:
    org = _get_org(ctx)
    data = org.rename(name)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# quota
# ---------------------------------------------------------------------------

_EXPLAIN_QUOTA = """\
Set the sensor quota for the organization.  The quota limits how many
sensors can be enrolled simultaneously.  Set to 0 to remove the quota
limit (billing still applies).
"""
register_explain("org.quota", _EXPLAIN_QUOTA)


@group.command()
@click.option("--quota", required=True, type=int, help="Sensor quota (0 to remove limit).")
@pass_context
def quota(ctx: click.Context, quota: int) -> None:
    org = _get_org(ctx)
    data = org.set_quota(quota)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# schema
# ---------------------------------------------------------------------------

_EXPLAIN_SCHEMA = """\
Retrieve event schemas for the organization.  Without options, returns
the full schema list.  Use --event-type to get the schema for a single
event type, or --platform to filter schemas by platform.
"""
register_explain("org.schema", _EXPLAIN_SCHEMA)


@group.command()
@click.option("--event-type", default=None, help="Specific event type to retrieve schema for.")
@click.option("--platform", default=None, help="Platform to filter schemas by.")
@pass_context
def schema(ctx: click.Context, event_type: str | None, platform: str | None) -> None:
    org = _get_org(ctx)
    if event_type:
        data = org.get_schema(event_type)
    else:
        data = org.get_schemas(platform)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# runtime-metadata
# ---------------------------------------------------------------------------

_EXPLAIN_RUNTIME_METADATA = """\
Retrieve runtime metadata for the organization.  Runtime metadata
describes the dynamic state of various platform entities such as
services and extensions.  Optionally filter by --entity-type and
--entity-name.
"""
register_explain("org.runtime-metadata", _EXPLAIN_RUNTIME_METADATA)


@group.command("runtime-metadata")
@click.option("--entity-type", default=None, help="Entity type to filter by.")
@click.option("--entity-name", default=None, help="Entity name to filter by.")
@pass_context
def runtime_metadata(ctx: click.Context, entity_type: str | None, entity_name: str | None) -> None:
    org = _get_org(ctx)
    data = org.get_runtime_metadata(entity_type, entity_name)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# check-name
# ---------------------------------------------------------------------------

_EXPLAIN_CHECK_NAME = """\
Check whether an organization name is available.  Returns availability
information for the given name.  Use this before creating or renaming
an organization to avoid name conflicts.
"""
register_explain("org.check-name", _EXPLAIN_CHECK_NAME)


@group.command("check-name")
@click.option("--name", required=True, help="Organization name to check availability for.")
@pass_context
def check_name(ctx: click.Context, name: str) -> None:
    client = _get_client(ctx)
    data = Organization.check_name(client, name)
    _output(ctx, data)
