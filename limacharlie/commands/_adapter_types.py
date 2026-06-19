"""Shared helpers for listing supported adapter/sensor types.

Both the cloud-adapter and external-adapter command groups expose a
``list-types`` subcommand.  The list of supported types is derived at
runtime from the ``cloud_sensor`` hive's JSON-Schema so it cannot go
stale relative to the backend.
"""

from __future__ import annotations

import re
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


def _types_from_schema(schema: Any) -> dict[str, str] | None:
    """Derive adapter types from an adapter hive JSON-Schema.

    The reflected schema is a root that ``$ref``s into ``$defs`` (e.g.
    ``CloudSensorRecord`` / ``ExternalAdapterConfig``); the per-adapter config
    lives in that record as a property keyed by the adapter type name
    (``s3``, ``office365``, ``threatlocker``, …), alongside the ``sensor_type``
    discriminator. The type names are therefore the record's ``properties``
    minus the shared/non-type fields — NOT the bare ``$defs`` keys, which are
    helper structs (``ClientOptions``, ``AckBufferOptions``, …).

    Returns a ``{type_name: description}`` mapping (description taken from the
    schema property's own ``description``, blank if it has none), or ``None``
    if the schema does not expose any usable type names.
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
    if not names:
        return None
    out: dict[str, str] = {}
    for name in sorted(names):
        node = props[name]
        desc = node.get("description", "") if isinstance(node, dict) else ""
        out[name] = desc if isinstance(desc, str) else ""
    return out


def adapter_types(org: Any, hive_name: str = "cloud_sensor") -> list[dict[str, str]]:
    """Return the supported adapter types for a hive as name/description rows.

    Derived solely from the live hive schema so it always tracks the backend.
    """
    schema = Hive(org, hive_name).get_schema()
    derived = _types_from_schema(schema)
    if not derived:
        raise click.ClickException(
            f"The '{hive_name}' hive schema did not advertise any adapter types."
        )
    return [{"type": name, "description": desc} for name, desc in derived.items()]


_EXPLAIN_LIST_TYPES = """\
List the supported adapter/sensor type names with a short description.

The list is derived from the live adapter hive JSON-Schema (so it
tracks the backend). Use a type name as the top-level sensor_type when
calling 'set'.

The cloud-adapter and external-adapter type sets differ: cloud adapters
run in LimaCharlie's infrastructure, external (on-prem) adapters add
types like syslog, file, stdin and wel. Consult the set --ai-help for
the per-type config shape.
"""


_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def _record_root(schema: Any) -> tuple[dict | None, dict | None]:
    """Return (root_schema, record_node) for an adapter hive schema.

    Unwraps the {"schema": {...}} envelope and follows the root $ref into the
    record definition (CloudSensorRecord / ExternalAdapterConfig).
    """
    if isinstance(schema, dict) and isinstance(schema.get("schema"), dict):
        schema = schema["schema"]
    if not isinstance(schema, dict):
        return None, None
    record = schema
    ref = schema.get("$ref")
    if isinstance(ref, str):
        resolved = _resolve_ref(schema, ref)
        if resolved is not None:
            record = resolved
    return schema, record


def adapter_type_schema(org: Any, hive_name: str, type_name: str) -> tuple[Any, dict | None]:
    """Resolve one adapter type's config sub-schema.

    Returns (root_schema, type_node): type_node is the JSON-Schema node for the
    per-type config (e.g. the threatlocker sub-struct), or None if the type is
    unknown. root_schema is returned so the caller can flatten/render with $ref
    resolution against $defs.
    """
    schema = Hive(org, hive_name).get_schema()
    root, record = _record_root(schema)
    if record is None:
        return schema, None
    props = record.get("properties")
    if not isinstance(props, dict) or type_name not in props:
        return root, None
    return root, props[type_name]


def adapter_sensors(org: Any, hive_name: str, key: str) -> dict[str, Any]:
    """Find the live sensor(s) belonging to an adapter record.

    Reads the adapter record, extracts its installation key (the sensor iid),
    and returns the sensors whose iid matches. Falls back to matching the
    adapter's configured hostname when the installation key isn't a bare iid
    (UUID). The sensors list is empty when the adapter hasn't registered a
    sensor yet (e.g. it has not delivered any events).
    """
    record = Hive(org, hive_name).get(key)
    data = getattr(record, "data", None) or {}
    sensor_type = data.get("sensor_type")
    sub = data.get(sensor_type, {}) if sensor_type else {}
    client_options = sub.get("client_options", {}) if isinstance(sub, dict) else {}
    identity = client_options.get("identity", {}) if isinstance(client_options, dict) else {}
    install_key = identity.get("installation_key")
    hostname = client_options.get("hostname")

    if isinstance(install_key, str) and _UUID_RE.match(install_key):
        match_by, match_val = "iid", install_key
    elif hostname:
        match_by, match_val = "hostname", hostname
    else:
        return {"adapter": key, "match_by": None, "match_value": None, "selector": None, "sensors": [],
                "note": "Adapter record has no resolvable installation_key (iid) or hostname to match on."}

    # Filter server-side with a sensor selector (both iid and hostname are
    # supported selector fields), so this scales to large fleets instead of
    # paging every sensor and filtering client-side.
    selector = f'{match_by} == "{match_val}"'
    sensors = [
        {"sid": s.get("sid"), "hostname": s.get("hostname"), "iid": s.get("iid"),
         "is_online": s.get("is_online"), "last_seen": s.get("alive")}
        for s in org.list_sensors(selector=selector)
    ]
    out = {"adapter": key, "match_by": match_by, "match_value": match_val, "selector": selector, "sensors": sensors}
    if not sensors:
        out["note"] = ("No sensor registered for this adapter yet — it has not delivered any "
                       "events (a cloud adapter materializes a sensor on first event). Normal "
                       "for a freshly-created adapter.")
    return out


_EXPLAIN_SCHEMA = """\
Show the configuration schema for ONE adapter/sensor type as a flat field
listing (field | type | required | notes), resolved from the live adapter hive
JSON-Schema. Use this before 'set' to learn the exact field set and where each
field lives (e.g. that hostname goes under client_options, not at the top
level). Pass --output json for the raw JSON-Schema node.

Run 'list-types' first to see the valid --type values.
"""

_EXPLAIN_SENSORS = """\
List the live sensor(s) this adapter has produced. Reads the adapter record's
installation key (iid) and returns sensors whose iid matches — the reliable way
to get a cloud/external adapter's SID without decoding the installation key.

An empty result means the adapter has not registered a sensor yet (it has not
delivered any events); that is expected for a freshly-created adapter.
"""


def add_schema(group: click.Group, command_path: str, hive_name: str = "cloud_sensor") -> None:
    """Attach a ``schema --type <t>`` subcommand to an adapter command group."""
    from ..cli import pass_context
    from ..client import Client
    from ..sdk.organization import Organization
    from ..output import format_output, detect_output_format
    from ..discovery import register_explain
    from .hive import _flatten_schema

    @group.command("schema", help="Show one adapter type's config schema.")
    @click.option("--type", "type_name", required=True, help="Adapter type (see list-types).")
    @pass_context
    def schema_cmd(ctx, type_name) -> None:
        client = Client(
            oid=ctx.obj.oid, environment=ctx.obj.environment,
            print_debug_fn=ctx.obj.debug_fn, debug_full_response=ctx.obj.debug_full,
            debug_curl=ctx.obj.debug_curl, debug_verbose=ctx.obj.debug_verbose,
        )
        org = Organization(client)
        root, node = adapter_type_schema(org, hive_name, type_name)
        if node is None:
            types = ", ".join(t["type"] for t in adapter_types(org, hive_name))
            raise click.UsageError(f"Unknown adapter type '{type_name}'. Valid types: {types}")
        if ctx.obj.quiet:
            return
        fmt = ctx.obj.output_format or detect_output_format()
        if fmt == "table" and isinstance(root, dict):
            rows = _flatten_schema(node, root)
            if rows:
                click.echo(format_output(rows, fmt))
                return
        # Raw JSON-Schema node for machine formats: resolve a top-level $ref and
        # carry the root $defs so nested $refs in the node stay resolvable.
        resolved = _resolve_ref(root, node["$ref"]) if isinstance(node, dict) and "$ref" in node and isinstance(root, dict) else node
        if isinstance(resolved, dict) and isinstance(root, dict) and isinstance(root.get("$defs"), dict):
            resolved = {**resolved, "$defs": root["$defs"]}
        click.echo(format_output(resolved, fmt))

    register_explain(command_path, _EXPLAIN_SCHEMA)


def add_sensors(group: click.Group, command_path: str, hive_name: str = "cloud_sensor") -> None:
    """Attach a ``sensors --key <adapter>`` subcommand to an adapter command group."""
    from ..cli import pass_context
    from ..client import Client
    from ..sdk.organization import Organization
    from ..output import format_output, detect_output_format
    from ..discovery import register_explain

    @group.command("sensors", help="List the live sensor(s) this adapter produced.")
    @click.option("--key", required=True, help="Adapter record key.")
    @pass_context
    def sensors_cmd(ctx, key) -> None:
        client = Client(
            oid=ctx.obj.oid, environment=ctx.obj.environment,
            print_debug_fn=ctx.obj.debug_fn, debug_full_response=ctx.obj.debug_full,
            debug_curl=ctx.obj.debug_curl, debug_verbose=ctx.obj.debug_verbose,
        )
        org = Organization(client)
        data = adapter_sensors(org, hive_name, key)
        if not ctx.obj.quiet:
            fmt = ctx.obj.output_format or detect_output_format()
            click.echo(format_output(data, fmt))

    register_explain(command_path, _EXPLAIN_SENSORS)


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
