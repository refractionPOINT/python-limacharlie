"""Hive commands for LimaCharlie CLI v2.

Commands for listing, reading, writing, and deleting records in
LimaCharlie Hives.  Hives are key-value stores that hold
configuration data such as D&R rules, lookups, secrets, and more.
"""

from __future__ import annotations

import json
import sys
from typing import Any

import click
import yaml

from ..cli import pass_context
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.hive import Hive, HiveRecord
from ..output import format_output, detect_output_format
from ..discovery import register_explain
from ._time_validation import validate_epoch_seconds


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
    """Load record data from a file or stdin."""
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


def _record_from_input(key: str, data: Any) -> HiveRecord:
    """Build a HiveRecord from parsed input data."""
    if not isinstance(data, dict):
        # Treat the whole input as the record data payload.
        return HiveRecord(key, data=data)

    record = HiveRecord(key)
    record.data = data.get("data", data)
    usr = data.get("usr_mtd", {})
    if usr:
        record.expiry = usr.get("expiry")
        record.enabled = usr.get("enabled")
        record.tags = usr.get("tags")
        record.comment = usr.get("comment")
    record.etag = data.get("etag") or data.get("sys_mtd", {}).get("etag")
    return record


# Known hive types supported by LimaCharlie.
_KNOWN_HIVE_TYPES = [
    "dr-general",
    "dr-managed",
    "dr-service",
    "fp",
    "cloud_sensor",
    "extension_config",
    "yara",
    "lookup",
    "secret",
    "query",
    "playbook",
    "ai_agent",
    "ai_skill",
    "ai_memory",
    "external_adapter",
    "sop",
    "org_notes",
    "app",
    "ai_cost_model",
]


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------

@click.group("hive")
def group() -> None:
    """Manage Hive key-value records.

    Hives are key-value stores for LimaCharlie configuration data
    including D&R rules, lookups, secrets, and extension configs.
    """


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

_EXPLAIN_LIST = """\
List all records in a specific hive.  Hives are key-value stores that
hold configuration data.  Common hive names include:

  dr-general       - D&R rules (general namespace)
  dr-managed       - D&R rules (managed namespace)
  dr-service       - D&R rules (service namespace)
  fp               - False positive rules
  secret           - Secrets (data format: {secret: "value"})
  lookup           - Lookup tables
  yara             - YARA rule sources (data format: {rule: "yara content"})
  extension_config - Extension configurations
  external_adapter - External adapter configs (syslog, file, cloud connectors)
  cloud_sensor     - Cloud sensor configurations
  query            - Saved LCQL queries
  playbook         - Playbooks
  sop              - Standard operating procedures
  org_notes        - Organization notes
  ai_agent         - AI agent configurations
  ai_skill         - Claude Code skill definitions
  ai_memory        - AI agent memories (partial-merge updates)
  ai_cost_model    - Per-org AI cost/savings economic model
  app              - AI-generated iframe web apps

Each record returned contains:
  data     - The record payload (structure varies by hive type)
  usr_mtd  - User metadata: enabled (bool), expiry (epoch int, 0=never),
             tags (list of strings), comment (string)
  sys_mtd  - System metadata: etag (concurrency token), guid, created/updated
             timestamps, author

Use --output json to get the full record data for export or backup.
"""
register_explain("hive.list", _EXPLAIN_LIST)


@group.command("list")
@click.option("--hive-name", required=True, help="Hive name (e.g., dr-general, lookup, secret).")
@pass_context
def list_records(ctx, hive_name) -> None:
    org = _get_org(ctx)
    hive = Hive(org, hive_name)
    records = hive.list()
    data = {name: rec.to_dict() for name, rec in records.items()}
    _output(ctx, data)


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------

_EXPLAIN_GET = """\
Get a single record from a hive by its key.  Returns the full record
including:

  data     - The record payload (structure varies by hive type)
  usr_mtd  - User-controlled metadata:
               enabled: true/false
               expiry: unix epoch (0 = never expires)
               tags: [list, of, strings]
               comment: "free-text description"
  sys_mtd  - System metadata:
               etag: concurrency token for optimistic locking
               guid: globally unique record ID
               created_at / updated_at: timestamps
               created_by / updated_by: author identity

Use the etag value in a subsequent "set" call to do compare-and-swap
updates, preventing concurrent modification conflicts.
"""
register_explain("hive.get", _EXPLAIN_GET)


@group.command()
@click.option("--hive-name", required=True, help="Hive name.")
@click.option("--key", required=True, help="Record key.")
@pass_context
def get(ctx, hive_name, key) -> None:
    org = _get_org(ctx)
    hive = Hive(org, hive_name)
    record = hive.get(key)
    _output(ctx, record.to_dict())


# ---------------------------------------------------------------------------
# set
# ---------------------------------------------------------------------------

_EXPLAIN_SET = """\
Create or update a record in a hive.  The record data is read from
--input-file or from stdin if no file is specified.  The input should
be a JSON or YAML document.

New hive records are created DISABLED by default.  Pass --enabled to
create-and-enable in one shot, or set usr_mtd.enabled in the input.

Full record format (YAML):

    data:
      key: value          # payload varies by hive type
    usr_mtd:
      enabled: true       # optional, default false on new records
      expiry: 0           # optional, unix epoch (0 = never)
      tags:               # optional
        - my-tag
      comment: "note"     # optional
    etag: "abc123"        # optional, for compare-and-swap updates

If the input has no "data" key, the entire input is treated as the
record data payload.

The --enabled/--disabled flag, when given, overrides any value in
the input file's usr_mtd.enabled.

Metadata flags (--tag-add, --tag-rm, --comment, --expiry) can be used
to manage usr_mtd without re-supplying the record data:

  * When NO data is supplied (no --input-file and no piped stdin), a
    metadata-only update is performed: the current metadata is fetched,
    --tag-add/--tag-rm are applied additively (existing tags are kept),
    and --comment/--expiry/--enabled overwrite their fields.
  * When data IS supplied, the same flags are applied as overrides on
    top of the input's usr_mtd.

--tag-add and --tag-rm are repeatable and additive (they never clobber
the existing tag set); applying both, a removal of an added tag wins.

Data payload examples per hive type:
  secret:  {secret: "my-api-key"}
  yara:    {rule: "rule MyRule { ... }"}
  lookup:  {lookup_data: {"1.2.3.4": {info: "bad"}}}
           or {newline_content: "val1\\nval2\\nval3"}

Examples:
  echo '{"data": {"key": "value"}}' | limacharlie hive set \\
      --hive-name lookup --key my-lookup --enabled

  limacharlie hive set --hive-name lookup --key my-lookup \\
      --input-file record.yaml --enabled

  # Metadata-only: add/remove tags and set a comment without touching data.
  limacharlie hive set --hive-name lookup --key my-lookup \\
      --tag-add prod --tag-add reviewed --tag-rm draft --comment "ready"
"""
register_explain("hive.set", _EXPLAIN_SET)


def _merge_tags(existing: list[str] | None, add: tuple[str, ...], rm: tuple[str, ...]) -> list[str]:
    """Additively merge tag changes onto an existing tag list.

    Existing tags are preserved; --tag-add entries are appended (case-
    insensitive dedup), then --tag-rm entries are removed.  A tag both
    added and removed in the same call is removed (removal wins).
    """
    seen: dict[str, str] = {}
    for tag in (existing or []) + list(add):
        key = tag.lower()
        if key not in seen:
            seen[key] = tag
    to_remove = {t.lower() for t in rm}
    return [t for k, t in seen.items() if k not in to_remove]


@group.command("set")
@click.option("--hive-name", required=True, help="Hive name.")
@click.option("--key", required=True, help="Record key.")
@click.option("--input-file", default=None, type=click.Path(exists=True), help="Path to record data (JSON or YAML). Reads stdin if omitted.")
@click.option(
    "--enabled/--disabled", "enabled", default=None,
    help="Set usr_mtd.enabled on the record. Overrides any value in the input file. New records default to disabled if neither this flag nor usr_mtd.enabled is provided.",
)
@click.option("--tag-add", "tag_add", multiple=True, help="Tag to add (repeatable, additive; keeps existing tags).")
@click.option("--tag-rm", "tag_rm", multiple=True, help="Tag to remove (repeatable, additive; keeps other existing tags).")
@click.option("--comment", default=None, help="Set usr_mtd.comment on the record.")
@click.option("--expiry", default=None, type=int, help="Set usr_mtd.expiry (Unix epoch seconds, 0 = never).")
@pass_context
def set_record(ctx, hive_name, key, input_file, enabled, tag_add, tag_rm, comment, expiry) -> None:
    if expiry is not None:
        validate_epoch_seconds(expiry, "expiry")

    data = _load_input(input_file)
    has_metadata_flags = bool(tag_add or tag_rm or comment is not None or expiry is not None or enabled is not None)

    org = _get_org(ctx)
    hive = Hive(org, hive_name)

    if data is None:
        if not has_metadata_flags:
            click.echo(
                "Error: No input data provided.\n"
                "Suggestion: Use --input-file or pipe data to stdin, "
                "or pass metadata flags (--tag-add/--tag-rm/--comment/--expiry/--enabled).",
                err=True,
            )
            ctx.exit(4)
            return
        # Metadata-only update: fetch current metadata so tags/comment/expiry
        # that are not being changed are preserved (the API replaces usr_mtd
        # wholesale), modeled on the enable/disable commands.
        record = hive.get_metadata(key)
        if tag_add or tag_rm:
            record.tags = _merge_tags(record.tags, tag_add, tag_rm)
        if comment is not None:
            record.comment = comment
        if expiry is not None:
            record.expiry = expiry
        if enabled is not None:
            record.enabled = enabled
    else:
        record = _record_from_input(key, data)
        if tag_add or tag_rm:
            record.tags = _merge_tags(record.tags, tag_add, tag_rm)
        if comment is not None:
            record.comment = comment
        if expiry is not None:
            record.expiry = expiry
        if enabled is not None:
            record.enabled = enabled

    result = hive.set(record)
    if not ctx.obj.quiet:
        click.echo(f"Record '{key}' set in hive '{hive_name}'.")
    _output(ctx, result)


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

_EXPLAIN_DELETE = """\
Delete a record from a hive.  This permanently removes the record
and any data or metadata associated with it.  The --confirm flag
is required to prevent accidental deletion.

Any D&R rules, outputs, or extensions that reference this record
(e.g. via hive://secret/my-key) will break after deletion.
"""
register_explain("hive.delete", _EXPLAIN_DELETE)


@group.command()
@click.option("--hive-name", required=True, help="Hive name.")
@click.option("--key", required=True, help="Record key to delete.")
@click.option("--confirm", is_flag=True, default=False, help="Confirm deletion (required).")
@pass_context
def delete(ctx, hive_name, key, confirm) -> None:
    if not confirm:
        click.echo(
            "Error: Destructive operation requires --confirm flag.\n"
            "Suggestion: Re-run with --confirm to delete the record.",
            err=True,
        )
        ctx.exit(4)
        return

    org = _get_org(ctx)
    hive = Hive(org, hive_name)
    result = hive.delete(key)
    if not ctx.obj.quiet:
        click.echo(f"Record '{key}' deleted from hive '{hive_name}'.")
    _output(ctx, result)


# ---------------------------------------------------------------------------
# enable / disable
# ---------------------------------------------------------------------------

_EXPLAIN_ENABLE = """\
Enable a hive record by setting its usr_mtd.enabled flag to true.
Only the enabled flag is changed; all other metadata (tags, expiry,
comment) and record data are preserved.
"""
register_explain("hive.enable", _EXPLAIN_ENABLE)

_EXPLAIN_DISABLE = """\
Disable a hive record by setting its usr_mtd.enabled flag to false.
Only the enabled flag is changed; all other metadata (tags, expiry,
comment) and record data are preserved.
"""
register_explain("hive.disable", _EXPLAIN_DISABLE)


def _set_enabled(ctx: click.Context, hive_name: str, key: str, enabled: bool) -> None:
    """Toggle the enabled flag on a hive record.

    Reads the current metadata first so that tags, expiry, and comment
    are preserved (the API replaces usr_mtd wholesale).
    """
    org = _get_org(ctx)
    hive = Hive(org, hive_name)
    record = hive.get_metadata(key)
    record.enabled = enabled
    result = hive.set(record)
    state = "enabled" if enabled else "disabled"
    if not ctx.obj.quiet:
        click.echo(f"Record '{key}' {state} in hive '{hive_name}'.")
    _output(ctx, result)


@group.command()
@click.option("--hive-name", required=True, help="Hive name.")
@click.option("--key", required=True, help="Record key.")
@pass_context
def enable(ctx, hive_name, key) -> None:
    _set_enabled(ctx, hive_name, key, True)


@group.command()
@click.option("--hive-name", required=True, help="Hive name.")
@click.option("--key", required=True, help="Record key.")
@pass_context
def disable(ctx, hive_name, key) -> None:
    _set_enabled(ctx, hive_name, key, False)


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------

_EXPLAIN_VALIDATE = """\
Validate a record against a hive's schema without saving it.  Useful
for checking whether record data is well-formed before pushing changes.
The data format is the same as for the 'set' command.

On success the command exits 0 and prints "Record is valid." to stderr.
When the API returns an empty/no-content response, the structured
formats (json/yaml) emit {"valid": true} so success is machine-readable.
On failure the command exits non-zero with the validation error.
"""
register_explain("hive.validate", _EXPLAIN_VALIDATE)


@group.command()
@click.option("--hive-name", required=True, help="Hive name.")
@click.option("--key", required=True, help="Record key to validate as.")
@click.option("--input-file", default=None, type=click.Path(exists=True), help="Path to record data (JSON or YAML). Reads stdin if omitted.")
@pass_context
def validate(ctx, hive_name, key, input_file) -> None:
    data = _load_input(input_file)
    if data is None:
        click.echo(
            "Error: No input data provided.\n"
            "Suggestion: Use --input-file or pipe data to stdin.",
            err=True,
        )
        ctx.exit(4)
        return

    org = _get_org(ctx)
    hive = Hive(org, hive_name)
    record = _record_from_input(key, data)
    # A failed validation raises (and exits non-zero) before reaching here,
    # so getting this far is an explicit positive verdict.
    result = hive.validate(record)
    # Keep stdout machine-stable: the human-readable confirmation goes to
    # stderr, and when the API reports nothing we synthesize {"valid": true}
    # so json/yaml consumers still get a definite success signal.
    if not ctx.obj.quiet:
        click.echo(f"Record '{key}' is valid.", err=True)
    if not result:
        result = {"valid": True}
    _output(ctx, result)


# ---------------------------------------------------------------------------
# schema
# ---------------------------------------------------------------------------

_EXPLAIN_SCHEMA = """\
Get the JSON Schema describing the record type for a given hive.  The
schema documents the structure, fields, and types accepted by records
in that hive — useful for tooling, code generation, or validating
records before calling 'set'.

Not all hives expose a typed schema.  Hives without a typed record
format (e.g., dr-general, dr-managed, dr-service, fp,
extension_config) return an error indicating no schema is available.

By default the schema is rendered as a flat field table (name, type,
required, notes) with $ref/$defs resolved, so the accepted fields are
immediately readable.  Use --output json to get the raw JSON Schema
(nothing is lost).

Example:
  limacharlie hive schema --hive-name secret
  limacharlie hive schema --hive-name ai_agent
  limacharlie hive schema --hive-name ai_agent --output json
"""
register_explain("hive.schema", _EXPLAIN_SCHEMA)


def _resolve_ref(ref: str, root: dict[str, Any]) -> dict[str, Any]:
    """Resolve a local JSON-Schema $ref (e.g. '#/$defs/Foo') against root."""
    if not ref.startswith("#/"):
        return {}
    node: Any = root
    for part in ref[2:].split("/"):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return {}
    return node if isinstance(node, dict) else {}


def _schema_type(node: dict[str, Any], root: dict[str, Any]) -> str:
    """Best-effort human type string for a JSON-Schema node."""
    if "$ref" in node:
        ref = node["$ref"]
        name = ref.rsplit("/", 1)[-1]
        return name or "object"
    t = node.get("type")
    if isinstance(t, list):
        return "|".join(str(x) for x in t)
    if t == "array":
        items = node.get("items")
        if isinstance(items, dict):
            return f"array<{_schema_type(items, root)}>"
        return "array"
    if t:
        return str(t)
    if "enum" in node:
        return "enum"
    if "anyOf" in node or "oneOf" in node:
        opts = node.get("anyOf") or node.get("oneOf") or []
        parts = [_schema_type(o, root) for o in opts if isinstance(o, dict)]
        return "|".join(p for p in parts if p) or "any"
    if "properties" in node:
        return "object"
    return "any"


def _flatten_schema(node: dict[str, Any], root: dict[str, Any], required: set[str] | None = None,
                    prefix: str = "", seen: set[int] | None = None) -> list[dict[str, str]]:
    """Flatten a JSON-Schema object into name/type/required/notes rows."""
    if seen is None:
        seen = set()
    if required is None:
        required = set()

    # Resolve a top-level $ref before descending.
    if "$ref" in node:
        node = _resolve_ref(node["$ref"], root)

    if id(node) in seen:
        return []
    seen = seen | {id(node)}

    rows: list[dict[str, str]] = []
    props = node.get("properties")
    if not isinstance(props, dict):
        return rows
    req = set(node.get("required", []))

    for name, sub in props.items():
        if not isinstance(sub, dict):
            continue
        field = f"{prefix}{name}"
        resolved = _resolve_ref(sub["$ref"], root) if "$ref" in sub else sub
        type_str = _schema_type(sub, root)

        notes_parts: list[str] = []
        if "enum" in resolved:
            vals = resolved["enum"]
            shown = ", ".join(str(v) for v in vals[:8])
            if len(vals) > 8:
                shown += ", ..."
            notes_parts.append(f"enum: {shown}")
        desc = resolved.get("description") or sub.get("description")
        if desc:
            notes_parts.append(str(desc).strip().splitlines()[0])

        rows.append({
            "field": field,
            "type": type_str,
            "required": "yes" if name in req else "",
            "notes": "; ".join(notes_parts),
        })

        # Recurse into nested objects (resolved object with properties).
        if isinstance(resolved.get("properties"), dict):
            rows.extend(_flatten_schema(resolved, root, prefix=f"{field}.", seen=seen))

    return rows


def _flatten_hive_schema(data: Any) -> list[dict[str, str]] | None:
    """Turn a hive get_schema() response into flat field rows.

    Returns None when the response has no resolvable object schema (so the
    caller can fall back to printing the raw structure).
    """
    if not isinstance(data, dict):
        return None
    root = data.get("schema", data)
    if not isinstance(root, dict):
        return None
    rows = _flatten_schema(root, root)
    return rows or None


@group.command()
@click.option("--hive-name", required=True, help="Hive name (e.g., secret, lookup, yara).")
@pass_context
def schema(ctx, hive_name) -> None:
    org = _get_org(ctx)
    hive = Hive(org, hive_name)
    data = hive.get_schema()

    fmt = ctx.obj.output_format or detect_output_format()
    # json/jsonl/yaml/toon/csv consumers get the raw JSON Schema untouched.
    # The default human view (table) is a flattened field listing.
    if fmt == "table":
        rows = _flatten_hive_schema(data)
        if rows is not None:
            _output(ctx, rows)
            return
    _output(ctx, data)


# ---------------------------------------------------------------------------
# rename
# ---------------------------------------------------------------------------

_EXPLAIN_RENAME = """\
Rename a record within a hive.  The record data and metadata are
preserved; only the key name changes.
"""
register_explain("hive.rename", _EXPLAIN_RENAME)


@group.command()
@click.option("--hive-name", required=True, help="Hive name.")
@click.option("--key", required=True, help="Current record key.")
@click.option("--new-name", required=True, help="New record key.")
@pass_context
def rename(ctx, hive_name, key, new_name) -> None:
    org = _get_org(ctx)
    hive = Hive(org, hive_name)
    result = hive.rename(key, new_name)
    if not ctx.obj.quiet:
        click.echo(f"Record '{key}' renamed to '{new_name}' in hive '{hive_name}'.")
    _output(ctx, result)


# ---------------------------------------------------------------------------
# list-types
# ---------------------------------------------------------------------------

_EXPLAIN_LIST_TYPES = """\
List all known hive type names that can be used with hive commands.

Hives are key-value stores that hold different types of configuration
data for a LimaCharlie organization.  Each hive type stores a specific
kind of data.  Known types: dr-general, dr-managed, dr-service, fp,
cloud_sensor, extension_config, yara, lookup, secret, query, playbook,
ai_agent, ai_skill, ai_memory, external_adapter, sop, org_notes.

Use these names with --hive-name in other hive commands.  Some hive
types also have dedicated shortcut commands (e.g. "limacharlie lookup",
"limacharlie secret", "limacharlie yara", "limacharlie ai-skill",
"limacharlie ai-memory").
"""
register_explain("hive.list-types", _EXPLAIN_LIST_TYPES)


@group.command("list-types")
@pass_context
def list_types(ctx) -> None:
    _output(ctx, _KNOWN_HIVE_TYPES)


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------

_EXPLAIN_EXPORT = """\
Export all records from a hive as YAML output.  This is useful for
backup, migration, or version control of hive contents.

Each record is exported with its full structure:

    record-name:
      data: { ... }       # record payload
      usr_mtd:
        enabled: true
        expiry: 0
        tags: [tag1]
        comment: ""
      sys_mtd:
        etag: "..."
        guid: "..."

The output can be saved to a file and later imported with
'limacharlie hive import'.  Use --partition-key to export from a
non-default partition.

Related: 'limacharlie hive import' to restore records from a YAML file,
'limacharlie sync pull' for full organization config export.
"""
register_explain("hive.export", _EXPLAIN_EXPORT)


@group.command("export")
@click.option("--hive-name", "name", required=True, help="Hive name (e.g., dr-general, lookup, secret).")
@click.option("--partition-key", default=None, help="Optional partition key (defaults to org OID).")
@pass_context
def export_records(ctx, name, partition_key) -> None:
    org = _get_org(ctx)
    hive = Hive(org, name, partition_key=partition_key)
    records = hive.list()

    # Build a dict with full record data for each key.
    export_data = {}
    for record_name, record in records.items():
        # Fetch full data for each record (list only returns metadata).
        full_record = hive.get(record_name)
        export_data[record_name] = full_record.to_dict()

    _output(ctx, export_data)


# ---------------------------------------------------------------------------
# import
# ---------------------------------------------------------------------------

_EXPLAIN_IMPORT = """\
Import records into a hive from a YAML file.  Each top-level key in
the YAML file is treated as a record name.  Expected format:

    my-record-1:
      data:
        key: value
      usr_mtd:
        enabled: true
        expiry: 0
        tags: [tag1]
        comment: ""
    my-record-2:
      data:
        key: other-value

Only "data" is required; "usr_mtd" is optional.  Use --dry-run to
preview what would be imported without making changes.

The format matches the output of 'limacharlie hive export', so you
can round-trip data between export and import.

Related: 'limacharlie hive export' to export records,
'limacharlie sync push' for full organization config push.
"""
register_explain("hive.import", _EXPLAIN_IMPORT)


@group.command("import")
@click.option("--hive-name", "name", required=True, help="Hive name (e.g., dr-general, lookup, secret).")
@click.option("--input-file", required=True, type=click.Path(exists=True), help="Path to YAML or JSON file to import.")
@click.option("--partition-key", default=None, help="Optional partition key (defaults to org OID).")
@click.option("--dry-run", is_flag=True, default=False, help="Preview changes without applying them.")
@pass_context
def import_records(ctx, name, input_file, partition_key, dry_run) -> None:
    data = _load_file(input_file)
    if not isinstance(data, dict):
        click.echo(
            "Error: Input file must contain a YAML/JSON mapping of record names to record data.",
            err=True,
        )
        ctx.exit(4)
        return

    org = _get_org(ctx)
    hive = Hive(org, name, partition_key=partition_key)

    results = {}
    imported = 0
    errors = []
    for record_name, record_data in data.items():
        record = _record_from_input(record_name, record_data)
        if dry_run:
            results[record_name] = {"action": "would_set", "record": record.to_dict()}
            if not ctx.obj.quiet:
                click.echo(f"[dry-run] Would set record '{record_name}' in hive '{name}'.")
        else:
            try:
                result = hive.set(record)
                results[record_name] = result
                imported += 1
                if not ctx.obj.quiet:
                    click.echo(f"Set record '{record_name}' in hive '{name}'.")
            except Exception as e:
                errors.append(f"  {record_name}: {e}")
                if not ctx.obj.quiet:
                    click.echo(f"Error setting record '{record_name}': {e}", err=True)

    if not dry_run and not ctx.obj.quiet:
        click.echo(f"Imported {imported}/{len(data)} records.")
        if errors:
            click.echo("Errors:", err=True)
            for err in errors:
                click.echo(err, err=True)
    _output(ctx, results)
    if errors:
        ctx.exit(min(len(errors), 125))
