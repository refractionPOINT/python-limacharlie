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


def _resolve_ref(root: dict, ref: str) -> dict | None:
    """Resolve a local JSON-Schema ``$ref`` (e.g. ``#/$defs/CloudSensorRecord``)."""
    if not isinstance(ref, str) or not ref.startswith("#/"):
        return None
    node: Any = root
    for part in ref[2:].split("/"):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node if isinstance(node, dict) else None


def _describe(name: str) -> str:
    """Best-effort human description for a derived type name (blank if unknown)."""
    return (
        _FALLBACK_ADAPTER_TYPES.get(name)
        or _FALLBACK_ADAPTER_TYPES.get(name.replace("_", ""))
        or ""
    )


def _types_from_schema(schema: Any) -> list[str] | None:
    """Derive adapter type names from an adapter hive JSON-Schema.

    The reflected schema is a root that ``$ref``s into ``$defs`` (e.g.
    ``CloudSensorRecord`` / ``ExternalAdapterConfig``); the per-adapter config
    lives in that record as a property keyed by the adapter type name
    (``s3``, ``office365``, ``threatlocker``, …), alongside the ``sensor_type``
    discriminator. The type names are therefore the record's ``properties``
    minus the shared/non-type fields — NOT the bare ``$defs`` keys, which are
    helper structs (``ClientOptions``, ``AckBufferOptions``, …). Returns
    ``None`` if the schema does not expose any usable type names.
    """
    if isinstance(schema, dict) and isinstance(schema.get("schema"), dict):
        schema = schema["schema"]
    if not isinstance(schema, dict):
        return None

    # Follow a top-level $ref into the record definition.
    record = schema
    ref = schema.get("$ref")
    if isinstance(ref, str):
        resolved = _resolve_ref(schema, ref)
        if resolved is not None:
            record = resolved

    props = record.get("properties")
    if not isinstance(props, dict):
        return None

    names = {n for n in props if n and not n.startswith("_")} - _NON_TYPE_FIELDS
    return sorted(names) or None


def adapter_types(org: Any, hive_name: str = "cloud_sensor") -> list[dict[str, str]]:
    """Return the supported adapter types for a hive as name/description rows.

    Prefers the live hive schema (so it tracks the backend); falls back to the
    curated constant when the schema is unavailable or does not advertise types.
    """
    derived: list[str] | None = None
    try:
        schema = Hive(org, hive_name).get_schema()
        derived = _types_from_schema(schema)
    except Exception:
        derived = None

    if derived:
        return [{"type": name, "description": _describe(name)} for name in derived]
    return [
        {"type": name, "description": desc}
        for name, desc in sorted(_FALLBACK_ADAPTER_TYPES.items())
    ]


_EXPLAIN_LIST_TYPES = """\
List the supported adapter/sensor type names with a short description.

The list is derived from the live adapter hive JSON-Schema when
available (so it tracks the backend), with a curated fallback otherwise.
Use a type name as the top-level sensor_type when calling 'set'.

The cloud-adapter and external-adapter type sets differ: cloud adapters
run in LimaCharlie's infrastructure, external (on-prem) adapters add
types like syslog, file, stdin and wel. Consult the set --ai-help for
the per-type config shape.
"""


def add_list_types(group: click.Group, command_path: str, hive_name: str = "cloud_sensor") -> None:
    """Attach a ``list-types`` subcommand to an adapter command group.

    ``hive_name`` selects which adapter hive's schema to enumerate
    (``cloud_sensor`` vs ``external_adapter``) so each group lists its own
    supported types.
    """
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
        data = adapter_types(org, hive_name)
        if not ctx.obj.quiet:
            fmt = ctx.obj.output_format or detect_output_format()
            click.echo(format_output(data, fmt))

    register_explain(command_path, _EXPLAIN_LIST_TYPES)
