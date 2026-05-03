"""Configuration sync (Infrastructure-as-Code) commands for LimaCharlie CLI v2.

Commands for pulling and pushing organization configuration to/from
the cloud via the ext-infrastructure extension.  This enables
Infrastructure-as-Code workflows where the entire org configuration
is stored in version-controlled YAML files.

D&R rules and FP rules are synced through their respective hives
(--hive-dr-general, --hive-dr-managed, --hive-dr-service, --hive-fp)
rather than the legacy --rules / --fps flags.
"""

from __future__ import annotations

from typing import Any, Callable

import click
import yaml

from ..cli import pass_context
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.configs import Configs
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
    client = Client(oid=ctx.obj.oid, environment=ctx.obj.environment, print_debug_fn=ctx.obj.debug_fn, debug_full_response=ctx.obj.debug_full, debug_curl=ctx.obj.debug_curl, debug_verbose=ctx.obj.debug_verbose)
    return Organization(client)


# Common sync flags used by both pull and push
_SYNC_FLAGS = [
    click.option("--all", "sync_all", is_flag=True, default=False, help="Sync all resource types."),
    click.option("--outputs", is_flag=True, default=False, help="Sync output configurations."),
    click.option("--integrity", is_flag=True, default=False, help="Sync integrity rules."),
    click.option("--exfil", is_flag=True, default=False, help="Sync exfil rules."),
    click.option("--artifact", is_flag=True, default=False, help="Sync artifact/logging rules."),
    click.option("--resources", is_flag=True, default=False, help="Sync resource subscriptions."),
    click.option("--extensions", is_flag=True, default=False, help="Sync extension subscriptions."),
    click.option("--org-values", is_flag=True, default=False, help="Sync org config values."),
    click.option("--installation-keys", is_flag=True, default=False, help="Sync installation keys."),
    click.option("--yara", is_flag=True, default=False, help="Sync YARA rules and sources."),
    # Hive flags
    click.option("--hive-dr-general", is_flag=True, default=False, help="Sync D&R rules (general hive)."),
    click.option("--hive-dr-managed", is_flag=True, default=False, help="Sync D&R rules (managed hive)."),
    click.option("--hive-dr-service", is_flag=True, default=False, help="Sync D&R rules (service hive)."),
    click.option("--hive-fp", is_flag=True, default=False, help="Sync false positive rules (hive)."),
    click.option("--hive-cloud-sensor", is_flag=True, default=False, help="Sync cloud sensor configs (hive)."),
    click.option("--hive-extension-config", is_flag=True, default=False, help="Sync extension configs (hive)."),
    click.option("--hive-yara", is_flag=True, default=False, help="Sync YARA rules (hive)."),
    click.option("--hive-lookup", is_flag=True, default=False, help="Sync lookups (hive)."),
    click.option("--hive-secret", is_flag=True, default=False, help="Sync secrets (hive)."),
    click.option("--hive-query", is_flag=True, default=False, help="Sync saved queries (hive)."),
    click.option("--hive-playbook", is_flag=True, default=False, help="Sync playbooks (hive)."),
    click.option("--hive-ai-agent", is_flag=True, default=False, help="Sync AI agents (hive)."),
    click.option("--hive-ai-skill", is_flag=True, default=False, help="Sync AI skills (hive)."),
    click.option("--hive-ai-memory", is_flag=True, default=False, help="Sync AI agent memories (hive)."),
    click.option("--hive-external-adapter", is_flag=True, default=False, help="Sync external adapters (hive)."),
]

# Maps CLI flag name -> hive name sent to the backend
_HIVE_FLAG_MAP = {
    "hive_dr_general": "dr-general",
    "hive_dr_managed": "dr-managed",
    "hive_dr_service": "dr-service",
    "hive_fp": "fp",
    "hive_cloud_sensor": "cloud_sensor",
    "hive_extension_config": "extension_config",
    "hive_yara": "yara",
    "hive_lookup": "lookup",
    "hive_secret": "secret",
    "hive_query": "query",
    "hive_playbook": "playbook",
    "hive_ai_agent": "ai_agent",
    "hive_ai_skill": "ai_skill",
    "hive_ai_memory": "ai_memory",
    "hive_external_adapter": "external_adapter",
}


def _add_sync_flags(func: Callable[..., Any]) -> Callable[..., Any]:
    for decorator in reversed(_SYNC_FLAGS):
        func = decorator(func)
    return func


def _resolve_sync_flags(sync_all: bool, outputs: bool,
                         integrity: bool, exfil: bool, artifact: bool,
                         resources: bool, extensions: bool, org_values: bool,
                         installation_keys: bool, yara_flag: bool,
                         **hive_kwargs: bool) -> dict[str, Any]:
    """Resolve sync flags, expanding --all into individual flags.

    Returns a dict suitable for passing to Configs.fetch() / Configs.push().
    """
    sync_hives: dict[str, bool] = {}
    for flag_name, hive_name in _HIVE_FLAG_MAP.items():
        if sync_all or hive_kwargs.get(flag_name, False):
            sync_hives[hive_name] = True

    return {
        "sync_outputs": sync_all or outputs,
        "sync_integrity": sync_all or integrity,
        "sync_exfil": sync_all or exfil,
        "sync_artifact": sync_all or artifact,
        "sync_resources": sync_all or resources,
        "sync_extensions": sync_all or extensions,
        "sync_org_values": sync_all or org_values,
        "sync_installation_keys": sync_all or installation_keys,
        "sync_yara": sync_all or yara_flag,
        "sync_hives": sync_hives,
    }


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------

@click.group("sync")
def group() -> None:
    """Sync organization configuration (Infrastructure-as-Code).

    Pull configuration from the cloud into local YAML files, or
    push local configuration to the cloud.  This enables version-
    controlled management of the entire org configuration.

    Uses the ext-infrastructure extension for all operations.
    D&R rules and FP rules are synced via hives (--hive-dr-general,
    --hive-fp, etc.) rather than the legacy --rules / --fps flags.
    """


# ---------------------------------------------------------------------------
# pull
# ---------------------------------------------------------------------------

_EXPLAIN_PULL = """\
Fetch the current organization configuration from the cloud and
save it to a local YAML file.  This enables Infrastructure-as-Code
workflows where the entire org configuration is version-controlled.

The saved YAML file uses version 3 format with top-level keys for
each resource type:

    version: 3
    outputs:
      my-syslog-output:
        module: syslog
        dest_host: 10.0.0.1
        ...
    integrity:
      my-fim-rule:
        patterns:
          - /etc/passwd
        ...
    hives:
      dr-general:
        my-dr-rule:
          detect:
            ...
          respond:
            ...
      fp:
        my-fp-rule:
          ...
    installation_keys:
      - desc: production linux
        tags:
          - production
          - linux

Resource type flags:
  --outputs              Output configurations
  --integrity            Integrity monitoring rules
  --exfil                Exfil prevention rules
  --artifact             Artifact/logging rules
  --resources            Resource subscriptions (marketplace add-ons)
  --extensions           Extension subscriptions
  --org-values           Organization config values
  --installation-keys    Installation keys
  --yara                 YARA rules and sources

Hive flags (for syncing hive-based resources):
  --hive-dr-general      D&R rules (general namespace)
  --hive-dr-managed      D&R rules (managed namespace)
  --hive-dr-service      D&R rules (service namespace)
  --hive-fp              False positive rules
  --hive-cloud-sensor    Cloud sensor configs
  --hive-extension-config  Extension configs
  --hive-yara            YARA rules (hive)
  --hive-lookup          Lookups
  --hive-secret          Secrets
  --hive-query           Saved queries
  --hive-playbook        Playbooks
  --hive-ai-agent        AI agents
  --hive-ai-skill        AI skills (Claude Code skill definitions)
  --hive-ai-memory       AI agent memories (partial-merge updates)
  --hive-external-adapter  External adapters

Examples:
  limacharlie sync pull --config-file org.yaml --all
  limacharlie sync pull --config-file dr.yaml --hive-dr-general --hive-fp
  limacharlie sync pull --config-file outputs.yaml --outputs
"""
register_explain("sync.pull", _EXPLAIN_PULL)


@group.command()
@click.option(
    "--config-file", required=True, type=click.Path(),
    help="Path to save the configuration YAML file.",
)
@_add_sync_flags
@pass_context
def pull(ctx, config_file, sync_all, outputs, integrity,
         exfil, artifact, resources, extensions, org_values,
         installation_keys, yara,
         hive_dr_general, hive_dr_managed, hive_dr_service,
         hive_fp, hive_cloud_sensor, hive_extension_config,
         hive_yara, hive_lookup, hive_secret, hive_query,
         hive_playbook, hive_ai_agent, hive_ai_skill, hive_ai_memory,
         hive_external_adapter) -> None:
    flags = _resolve_sync_flags(
        sync_all, outputs, integrity, exfil,
        artifact, resources, extensions, org_values,
        installation_keys, yara,
        hive_dr_general=hive_dr_general,
        hive_dr_managed=hive_dr_managed,
        hive_dr_service=hive_dr_service,
        hive_fp=hive_fp,
        hive_cloud_sensor=hive_cloud_sensor,
        hive_extension_config=hive_extension_config,
        hive_yara=hive_yara,
        hive_lookup=hive_lookup,
        hive_secret=hive_secret,
        hive_query=hive_query,
        hive_playbook=hive_playbook,
        hive_ai_agent=hive_ai_agent,
        hive_ai_skill=hive_ai_skill,
        hive_ai_memory=hive_ai_memory,
        hive_external_adapter=hive_external_adapter,
    )

    if not any(flags.values()):
        click.echo(
            "Error: Specify --all or at least one resource type flag.\n"
            "Suggestion: Use --all to fetch everything, or specific flags like --outputs or --hive-dr-general.",
            err=True,
        )
        ctx.exit(4)
        return

    org = _get_org(ctx)
    configs = Configs(org)
    data = configs.fetch_to_file(config_file, **flags)
    if not ctx.obj.quiet:
        click.echo(f"Configuration saved to {config_file}.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# push
# ---------------------------------------------------------------------------

_EXPLAIN_PUSH = """\
Push a local YAML configuration file to the cloud.  Use --all to push
everything in the file, or use specific flags to push only certain
resource types.

The YAML file must use version 3 format (same as produced by pull):

    version: 3
    hives:
      dr-general:
        my-dr-rule:
          detect:
            op: ends with
            event: NEW_PROCESS
            path: event/FILE_PATH
            value: evil.exe
          respond:
            - action: report
              name: evil-process-detected

Use --dry-run to preview changes without applying them.  The output
shows which resources would be added, modified, or removed.

Use --force to remove cloud resources not present in the local file.
Without --force, push only adds or updates; it never removes.

Examples:
  limacharlie sync push --config-file org.yaml --all
  limacharlie sync push --config-file org.yaml --all --dry-run
  limacharlie sync push --config-file org.yaml --hive-dr-general --force
"""
register_explain("sync.push", _EXPLAIN_PUSH)


@group.command()
@click.option(
    "--config-file", required=True, type=click.Path(exists=True),
    help="Path to the configuration YAML file to push.",
)
@click.option("--force", is_flag=True, default=False, help="Remove cloud resources not in local file.")
@click.option("--dry-run", is_flag=True, default=False, help="Preview changes without applying.")
@_add_sync_flags
@pass_context
def push(ctx, config_file, force, dry_run, sync_all, outputs,
         integrity, exfil, artifact, resources, extensions, org_values,
         installation_keys, yara,
         hive_dr_general, hive_dr_managed, hive_dr_service,
         hive_fp, hive_cloud_sensor, hive_extension_config,
         hive_yara, hive_lookup, hive_secret, hive_query,
         hive_playbook, hive_ai_agent, hive_ai_skill, hive_ai_memory,
         hive_external_adapter) -> None:
    flags = _resolve_sync_flags(
        sync_all, outputs, integrity, exfil,
        artifact, resources, extensions, org_values,
        installation_keys, yara,
        hive_dr_general=hive_dr_general,
        hive_dr_managed=hive_dr_managed,
        hive_dr_service=hive_dr_service,
        hive_fp=hive_fp,
        hive_cloud_sensor=hive_cloud_sensor,
        hive_extension_config=hive_extension_config,
        hive_yara=hive_yara,
        hive_lookup=hive_lookup,
        hive_secret=hive_secret,
        hive_query=hive_query,
        hive_playbook=hive_playbook,
        hive_ai_agent=hive_ai_agent,
        hive_ai_skill=hive_ai_skill,
        hive_ai_memory=hive_ai_memory,
        hive_external_adapter=hive_external_adapter,
    )

    if not any(flags.values()):
        click.echo(
            "Error: Specify --all or at least one resource type flag.\n"
            "Suggestion: Use --all to push everything, or specific flags like --outputs or --hive-dr-general.",
            err=True,
        )
        ctx.exit(4)
        return

    org = _get_org(ctx)
    configs = Configs(org)
    results, errors = configs.push_from_file(
        config_file,
        is_force=force,
        is_dry_run=dry_run,
        **flags,
    )

    if not ctx.obj.quiet:
        if dry_run:
            click.echo("Dry run results:")
        for op, rtype, name in results:
            click.echo(f"  {op} {rtype}: {name}")
        if not results and not errors:
            click.echo("  No changes.")
        if errors:
            click.echo("Errors:", err=True)
            for err in errors:
                click.echo(f"  {err}", err=True)
    _output(ctx, [{"op": op, "type": rtype, "name": name} for op, rtype, name in results])
    if errors:
        ctx.exit(min(len(errors), 125))
