"""Configuration sync (Infrastructure-as-Code) commands for LimaCharlie CLI v2.

Commands for pulling and pushing organization configuration to/from
the cloud.  This enables Infrastructure-as-Code workflows where
the entire org configuration is stored in version-controlled YAML files.
"""

from __future__ import annotations

from typing import Any, Callable

import click
import yaml

from ..cli import pass_context
from ..config import resolve_credentials
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.configs import Configs
from ..output import format_output, detect_output_format
from ..discovery import register_explain


# ---------------------------------------------------------------------------
# Explain texts
# ---------------------------------------------------------------------------

_EXPLAIN_PULL = """\
Fetch the current organization configuration from the cloud and
save it to a local YAML file.  Use --all to fetch everything, or
use specific flags to fetch only certain resource types.

Resource type flags:
  --rules              D&R rules
  --fps                False positive rules
  --outputs            Output configurations
  --integrity          Integrity monitoring rules
  --exfil              Exfil prevention rules
  --artifact           Artifact/logging rules
  --resources          Resource subscriptions
  --extensions         Extension subscriptions
  --org-values         Organization config values
  --installation-keys  Installation keys
  --yara               YARA rules and sources

Examples:
  limacharlie sync pull --config-file org.yaml --all
  limacharlie sync pull --config-file rules.yaml --rules --fps
"""

_EXPLAIN_PUSH = """\
Push a local configuration file to the cloud.  Use --all to push
everything in the file, or use specific flags to push only certain
resource types.

Use --dry-run to preview changes without applying them.
Use --force to remove cloud resources not present in the local file.

Examples:
  limacharlie sync push --config-file org.yaml --all
  limacharlie sync push --config-file org.yaml --all --dry-run
  limacharlie sync push --config-file org.yaml --rules --force
"""

register_explain("sync.pull", _EXPLAIN_PULL)
register_explain("sync.push", _EXPLAIN_PUSH)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_explain_callback(text: str) -> Callable[[click.Context, click.Parameter, bool], None]:
    def callback(ctx: click.Context, param: click.Parameter, value: bool) -> None:
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


# Common sync flags used by both pull and push
_SYNC_FLAGS = [
    click.option("--all", "sync_all", is_flag=True, default=False, help="Sync all resource types."),
    click.option("--rules", is_flag=True, default=False, help="Sync D&R rules."),
    click.option("--fps", is_flag=True, default=False, help="Sync false positive rules."),
    click.option("--outputs", is_flag=True, default=False, help="Sync output configurations."),
    click.option("--integrity", is_flag=True, default=False, help="Sync integrity rules."),
    click.option("--exfil", is_flag=True, default=False, help="Sync exfil rules."),
    click.option("--artifact", is_flag=True, default=False, help="Sync artifact/logging rules."),
    click.option("--resources", is_flag=True, default=False, help="Sync resource subscriptions."),
    click.option("--extensions", is_flag=True, default=False, help="Sync extension subscriptions."),
    click.option("--org-values", is_flag=True, default=False, help="Sync org config values."),
    click.option("--installation-keys", is_flag=True, default=False, help="Sync installation keys."),
    click.option("--yara", is_flag=True, default=False, help="Sync YARA rules and sources."),
]


def _add_sync_flags(func: Callable[..., Any]) -> Callable[..., Any]:
    for decorator in reversed(_SYNC_FLAGS):
        func = decorator(func)
    return func


def _resolve_sync_flags(sync_all: bool, rules: bool, fps: bool, outputs: bool,
                         integrity: bool, exfil: bool, artifact: bool,
                         resources: bool, extensions: bool, org_values: bool,
                         installation_keys: bool, yara_flag: bool) -> dict[str, bool]:
    """Resolve sync flags, expanding --all into individual flags."""
    return {
        "sync_rules": sync_all or rules,
        "sync_fps": sync_all or fps,
        "sync_outputs": sync_all or outputs,
        "sync_integrity": sync_all or integrity,
        "sync_exfil": sync_all or exfil,
        "sync_artifact": sync_all or artifact,
        "sync_resources": sync_all or resources,
        "sync_extensions": sync_all or extensions,
        "sync_org_values": sync_all or org_values,
        "sync_installation_keys": sync_all or installation_keys,
        "sync_yara": sync_all or yara_flag,
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
    """


# ---------------------------------------------------------------------------
# pull
# ---------------------------------------------------------------------------

@group.command()
@click.option(
    "--config-file", required=True, type=click.Path(),
    help="Path to save the configuration YAML file.",
)
@_add_sync_flags
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_PULL),
    help="Show detailed explanation of this command.",
)
@pass_context
def pull(ctx, config_file, sync_all, rules, fps, outputs, integrity,
         exfil, artifact, resources, extensions, org_values,
         installation_keys, yara) -> None:
    """Fetch configuration from the cloud.

    Examples:
        limacharlie sync pull --config-file org.yaml --all
        limacharlie sync pull --config-file rules.yaml --rules --fps
    """
    flags = _resolve_sync_flags(
        sync_all, rules, fps, outputs, integrity, exfil,
        artifact, resources, extensions, org_values,
        installation_keys, yara,
    )

    if not any(flags.values()):
        click.echo(
            "Error: Specify --all or at least one resource type flag.\n"
            "Suggestion: Use --all to fetch everything, or specific flags like --rules.",
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

@group.command()
@click.option(
    "--config-file", required=True, type=click.Path(exists=True),
    help="Path to the configuration YAML file to push.",
)
@click.option("--force", is_flag=True, default=False, help="Remove cloud resources not in local file.")
@click.option("--dry-run", is_flag=True, default=False, help="Preview changes without applying.")
@_add_sync_flags
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_PUSH),
    help="Show detailed explanation of this command.",
)
@pass_context
def push(ctx, config_file, force, dry_run, sync_all, rules, fps, outputs,
         integrity, exfil, artifact, resources, extensions, org_values,
         installation_keys, yara) -> None:
    """Push configuration to the cloud.

    Examples:
        limacharlie sync push --config-file org.yaml --all
        limacharlie sync push --config-file org.yaml --all --dry-run
        limacharlie sync push --config-file org.yaml --rules --force
    """
    flags = _resolve_sync_flags(
        sync_all, rules, fps, outputs, integrity, exfil,
        artifact, resources, extensions, org_values,
        installation_keys, yara,
    )

    if not any(flags.values()):
        click.echo(
            "Error: Specify --all or at least one resource type flag.\n"
            "Suggestion: Use --all to push everything, or specific flags like --rules.",
            err=True,
        )
        ctx.exit(4)
        return

    org = _get_org(ctx)
    configs = Configs(org)
    results = configs.push_from_file(
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
        if not results:
            click.echo("  No changes.")
    _output(ctx, [{"op": op, "type": rtype, "name": name} for op, rtype, name in results])
