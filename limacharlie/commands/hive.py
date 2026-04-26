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
    "external_adapter",
    "sop",
    "org_notes",
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

Full record format (YAML):

    data:
      key: value          # payload varies by hive type
    usr_mtd:
      enabled: true       # optional, default true
      expiry: 0           # optional, unix epoch (0 = never)
      tags:               # optional
        - my-tag
      comment: "note"     # optional
    etag: "abc123"        # optional, for compare-and-swap updates

If the input has no "data" key, the entire input is treated as the
record data payload.

Data payload examples per hive type:
  secret:  {secret: "my-api-key"}
  yara:    {rule: "rule MyRule { ... }"}
  lookup:  {lookup_data: {"1.2.3.4": {info: "bad"}}}
           or {newline_content: "val1\\nval2\\nval3"}

Examples:
  echo '{"data": {"key": "value"}}' | limacharlie hive set \\
      --hive-name lookup --key my-lookup

  limacharlie hive set --hive-name lookup --key my-lookup \\
      --input-file record.yaml
"""
register_explain("hive.set", _EXPLAIN_SET)


@group.command("set")
@click.option("--hive-name", required=True, help="Hive name.")
@click.option("--key", required=True, help="Record key.")
@click.option("--input-file", default=None, type=click.Path(exists=True), help="Path to record data (JSON or YAML). Reads stdin if omitted.")
@pass_context
def set_record(ctx, hive_name, key, input_file) -> None:
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
    result = hive.validate(record)
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

Example:
  limacharlie hive schema --hive-name secret
  limacharlie hive schema --hive-name lookup
"""
register_explain("hive.schema", _EXPLAIN_SCHEMA)


@group.command()
@click.option("--hive-name", required=True, help="Hive name (e.g., secret, lookup, yara).")
@pass_context
def schema(ctx, hive_name) -> None:
    org = _get_org(ctx)
    hive = Hive(org, hive_name)
    data = hive.get_schema()
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
ai_agent, external_adapter, sop, org_notes.

Use these names with --hive-name in other hive commands.  Some hive
types also have dedicated shortcut commands (e.g. "limacharlie lookup",
"limacharlie secret", "limacharlie yara").
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
