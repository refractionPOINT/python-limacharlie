"""Shared helpers for listing supported adapter/sensor types.

Both the cloud-adapter and external-adapter command groups expose a
``list-types`` subcommand.  The list of supported types is derived at
runtime from the ``cloud_sensor`` hive's JSON-Schema so it cannot go
stale relative to the backend; a curated fallback is used only if the
schema cannot be fetched or does not advertise the per-type sub-structs.
"""

from __future__ import annotations

from typing import Any

import click

from ..sdk.hive import Hive

# Fields that appear at the top level of an adapter config but are NOT
# adapter type names (they are shared across every adapter type).  These
# are filtered out when deriving the type list from the schema.
_NON_TYPE_FIELDS = {
    "sensor_type",
    "client_options",
    "mapping",
    "mappings",
    "indexing",
}

# Curated fallback list.  IMPORTANT: this is only used when the live
# cloud_sensor schema cannot be fetched or parsed.  It MUST be kept in
# sync with the backend's supported adapter types; prefer the schema-
# derived list, which cannot go stale.
_FALLBACK_ADAPTER_TYPES: dict[str, str] = {
    "1password": "1Password audit events",
    "azure_event_hub": "Azure Event Hub stream",
    "carbon_black": "VMware Carbon Black events",
    "cato": "Cato Networks events",
    "crowdstrike": "CrowdStrike Falcon Data Replicator",
    "duo": "Cisco Duo authentication logs",
    "entraid": "Microsoft Entra ID (Azure AD) logs",
    "file": "Tail a local file",
    "gcs": "Google Cloud Storage objects",
    "github": "GitHub audit log",
    "google_workspace": "Google Workspace activity",
    "guardduty": "AWS GuardDuty findings",
    "imap": "IMAP mailbox ingestion",
    "itglue": "IT Glue records",
    "k8s_pods": "Kubernetes pod logs",
    "mac_unified_logging": "macOS unified logging",
    "mimecast": "Mimecast email security logs",
    "ms_graph": "Microsoft Graph API",
    "office365": "Microsoft Office 365 management activity",
    "okta": "Okta system log",
    "pubsub": "Google Cloud Pub/Sub",
    "s3": "AWS S3 objects",
    "sentinelone": "SentinelOne events",
    "simulation": "Simulated/test events",
    "slack": "Slack audit logs",
    "sophos": "Sophos Central events",
    "sqs": "AWS SQS queue",
    "stdin": "Read events from stdin (external adapter only)",
    "syslog": "Syslog over TCP/UDP",
    "threatlocker": "ThreatLocker unified audit",
    "webhook": "Inbound HTTP webhook",
    "wel": "Windows Event Log (external adapter only)",
    "wiz": "Wiz cloud security findings",
}


def _types_from_schema(schema: Any) -> list[str] | None:
    """Derive adapter type names from a cloud_sensor JSON-Schema.

    The per-adapter config lives in a sibling sub-struct keyed by the
    adapter type name (e.g. ``s3``, ``syslog``), so the type names are
    the object properties (minus the shared/non-type fields).  Returns
    ``None`` if the schema does not expose any usable type names.
    """
    if isinstance(schema, dict) and "schema" in schema and isinstance(schema["schema"], dict):
        schema = schema["schema"]
    if not isinstance(schema, dict):
        return None

    names: set[str] = set()
    props = schema.get("properties")
    if isinstance(props, dict):
        names.update(props.keys())
    defs = schema.get("$defs") or schema.get("definitions")
    if isinstance(defs, dict):
        names.update(defs.keys())

    names -= _NON_TYPE_FIELDS
    cleaned = sorted(n for n in names if n and not n.startswith("_"))
    return cleaned or None


def adapter_types(org: Any) -> list[dict[str, str]]:
    """Return the supported adapter types as name/description rows.

    Prefers the live cloud_sensor hive schema; falls back to the curated
    constant when the schema is unavailable or does not advertise types.
    """
    derived: list[str] | None = None
    try:
        schema = Hive(org, "cloud_sensor").get_schema()
        derived = _types_from_schema(schema)
    except Exception:
        derived = None

    if derived:
        return [
            {"type": name, "description": _FALLBACK_ADAPTER_TYPES.get(name, "")}
            for name in derived
        ]
    return [
        {"type": name, "description": desc}
        for name, desc in sorted(_FALLBACK_ADAPTER_TYPES.items())
    ]


_EXPLAIN_LIST_TYPES = """\
List the supported adapter/sensor type names with a short description.

The list is derived from the live cloud_sensor hive JSON-Schema when
available (so it tracks the backend), with a curated fallback otherwise.
Use a type name as the top-level sensor_type when calling 'set'.

Note: a few types are only meaningful for external (on-prem) adapters
(e.g. stdin, wel) versus cloud adapters; consult the set --ai-help for
the per-type config shape.
"""


def add_list_types(group: click.Group, command_path: str) -> None:
    """Attach a ``list-types`` subcommand to an adapter command group."""
    from ..cli import pass_context
    from ..client import Client
    from ..sdk.organization import Organization
    from ..output import format_output, detect_output_format
    from ..discovery import register_explain

    @group.command("list-types", help="List supported adapter/sensor types.")
    @pass_context
    def list_types_cmd(ctx) -> None:
        client = Client(
            oid=ctx.obj.oid,
            environment=ctx.obj.environment,
            print_debug_fn=ctx.obj.debug_fn,
            debug_full_response=ctx.obj.debug_full,
            debug_curl=ctx.obj.debug_curl,
            debug_verbose=ctx.obj.debug_verbose,
        )
        org = Organization(client)
        data = adapter_types(org)
        if not ctx.obj.quiet:
            fmt = ctx.obj.output_format or detect_output_format()
            click.echo(format_output(data, fmt))

    register_explain(command_path, _EXPLAIN_LIST_TYPES)
