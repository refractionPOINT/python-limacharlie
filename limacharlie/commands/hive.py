"""Hive commands for LimaCharlie CLI v2.

Commands for listing, reading, writing, and deleting records in
LimaCharlie Hives.  Hives are key-value stores that hold
configuration data such as D&R rules, lookups, secrets, and more.
"""

import json
import sys

import click
import yaml

from ..cli import pass_context
from ..config import resolve_credentials
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.hive import Hive, HiveRecord
from ..output import format_output, detect_output_format
from ..discovery import register_explain


# ---------------------------------------------------------------------------
# Explain texts
# ---------------------------------------------------------------------------

_EXPLAIN_LIST = """\
List all records in a specific hive.  Hives are key-value stores that
hold configuration data.  Common hive names include:

  dr-general   - D&R rules (general namespace).
  dr-managed   - D&R rules (managed namespace).
  secret       - Secrets stored for the organization.
  lookup       - Lookup tables.
  fp           - False positive rules.
  external_adapter - External adapter configurations.

The output includes the record name and metadata.  Use --output json
to get the full record data for export or backup.
"""

_EXPLAIN_GET = """\
Get a single record from a hive by its key.  Returns the full record
data, user metadata (expiry, enabled, tags, comment), and system
metadata (etag, timestamps, author).
"""

_EXPLAIN_SET = """\
Create or update a record in a hive.  The record data is read from
--input-file or from stdin if no file is specified.  The input should
be a JSON or YAML document with at minimum a 'data' key.  Optional
keys include 'usr_mtd' (with 'expiry', 'enabled', 'tags', 'comment')
and 'etag' for optimistic concurrency.

Examples:
  echo '{"data": {"key": "value"}}' | limacharlie hive set \\
      --hive-name lookup --key my-lookup

  limacharlie hive set --hive-name lookup --key my-lookup \\
      --input-file record.yaml
"""

_EXPLAIN_DELETE = """\
Delete a record from a hive.  This permanently removes the record.
The --confirm flag is required to prevent accidental deletion.
"""

_EXPLAIN_VALIDATE = """\
Validate a record against a hive's schema without saving it.  Useful
for checking whether record data is well-formed before pushing changes.
The data format is the same as for the 'set' command.
"""

_EXPLAIN_RENAME = """\
Rename a record within a hive.  The record data and metadata are
preserved; only the key name changes.
"""

_EXPLAIN_LIST_TYPES = """\
List all known hive type names that can be used with hive commands.

Hives are key-value stores that hold different types of configuration
data for a LimaCharlie organization.  Each hive type stores a specific
kind of data (e.g., D&R rules, secrets, lookups, YARA rules).

The output is a static list of known hive type names.  Use these
names with --hive-name in other hive commands.
"""

_EXPLAIN_EXPORT = """\
Export all records from a hive as YAML output.  This is useful for
backup, migration, or version control of hive contents.

Each record is exported with its full data and user metadata
(expiry, enabled, tags, comment).  The output can be saved to a
file and later imported with 'limacharlie hive import'.

Related: 'limacharlie hive import' to restore records from a YAML file,
'limacharlie sync pull' for full organization config export.
"""

_EXPLAIN_IMPORT = """\
Import records into a hive from a YAML file.  Each top-level key in
the YAML file is treated as a record name.  The value should be a
dict with at minimum a 'data' key, and optionally 'usr_mtd' for
user metadata (expiry, enabled, tags, comment).

Use --dry-run to preview what would be imported without making changes.

The YAML format matches the output of 'limacharlie hive export',
so you can round-trip data between export and import.

Related: 'limacharlie hive export' to export records,
'limacharlie sync push' for full organization config push.
"""

register_explain("hive.list", _EXPLAIN_LIST)
register_explain("hive.get", _EXPLAIN_GET)
register_explain("hive.set", _EXPLAIN_SET)
register_explain("hive.delete", _EXPLAIN_DELETE)
register_explain("hive.validate", _EXPLAIN_VALIDATE)
register_explain("hive.rename", _EXPLAIN_RENAME)
register_explain("hive.list-types", _EXPLAIN_LIST_TYPES)
register_explain("hive.export", _EXPLAIN_EXPORT)
register_explain("hive.import", _EXPLAIN_IMPORT)


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


def _load_file(path):
    """Load a JSON or YAML file and return parsed content."""
    with open(path, "r") as f:
        content = f.read()
    try:
        return yaml.safe_load(content)
    except Exception:
        pass
    return json.loads(content)


def _load_input(input_file):
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


def _record_from_input(key, data):
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
    "note",
]


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------

@click.group("hive")
def group():
    """Manage Hive key-value records.

    Hives are key-value stores for LimaCharlie configuration data
    including D&R rules, lookups, secrets, and extension configs.
    """


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

@group.command("list")
@click.option("--hive-name", required=True, help="Hive name (e.g., dr-general, lookup, secret).")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_LIST),
    help="Show detailed explanation of this command.",
)
@pass_context
def list_records(ctx, hive_name):
    """List records in a hive.

    Examples:
        limacharlie hive list --hive-name dr-general
        limacharlie hive list --hive-name lookup --output json
    """
    org = _get_org(ctx)
    hive = Hive(org, hive_name)
    records = hive.list()
    data = {name: rec.to_dict() for name, rec in records.items()}
    _output(ctx, data)


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------

@group.command()
@click.option("--hive-name", required=True, help="Hive name.")
@click.option("--key", required=True, help="Record key.")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_GET),
    help="Show detailed explanation of this command.",
)
@pass_context
def get(ctx, hive_name, key):
    """Get a hive record by key.

    Example:
        limacharlie hive get --hive-name lookup --key my-lookup
    """
    org = _get_org(ctx)
    hive = Hive(org, hive_name)
    record = hive.get(key)
    _output(ctx, record.to_dict())


# ---------------------------------------------------------------------------
# set
# ---------------------------------------------------------------------------

@group.command("set")
@click.option("--hive-name", required=True, help="Hive name.")
@click.option("--key", required=True, help="Record key.")
@click.option("--input-file", default=None, type=click.Path(exists=True), help="Path to record data (JSON or YAML). Reads stdin if omitted.")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_SET),
    help="Show detailed explanation of this command.",
)
@pass_context
def set_record(ctx, hive_name, key, input_file):
    """Set (create or update) a hive record.

    Record data is read from --input-file or stdin.

    Examples:
        limacharlie hive set --hive-name lookup --key my-lookup \\
            --input-file record.yaml

        echo '{"data": {"key": "value"}}' | \\
            limacharlie hive set --hive-name lookup --key my-lookup
    """
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

@group.command()
@click.option("--hive-name", required=True, help="Hive name.")
@click.option("--key", required=True, help="Record key to delete.")
@click.option("--confirm", is_flag=True, default=False, help="Confirm deletion (required).")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_DELETE),
    help="Show detailed explanation of this command.",
)
@pass_context
def delete(ctx, hive_name, key, confirm):
    """Delete a hive record.

    This is a destructive operation.  Pass --confirm to proceed.

    Example:
        limacharlie hive delete --hive-name lookup --key my-lookup --confirm
    """
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
# validate
# ---------------------------------------------------------------------------

@group.command()
@click.option("--hive-name", required=True, help="Hive name.")
@click.option("--key", required=True, help="Record key to validate as.")
@click.option("--input-file", default=None, type=click.Path(exists=True), help="Path to record data (JSON or YAML). Reads stdin if omitted.")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_VALIDATE),
    help="Show detailed explanation of this command.",
)
@pass_context
def validate(ctx, hive_name, key, input_file):
    """Validate a hive record without saving.

    Example:
        limacharlie hive validate --hive-name lookup --key my-lookup \\
            --input-file record.yaml
    """
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
# rename
# ---------------------------------------------------------------------------

@group.command()
@click.option("--hive-name", required=True, help="Hive name.")
@click.option("--key", required=True, help="Current record key.")
@click.option("--new-name", required=True, help="New record key.")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_RENAME),
    help="Show detailed explanation of this command.",
)
@pass_context
def rename(ctx, hive_name, key, new_name):
    """Rename a hive record.

    Example:
        limacharlie hive rename --hive-name lookup --key old-name --new-name new-name
    """
    org = _get_org(ctx)
    hive = Hive(org, hive_name)
    result = hive.rename(key, new_name)
    if not ctx.obj.quiet:
        click.echo(f"Record '{key}' renamed to '{new_name}' in hive '{hive_name}'.")
    _output(ctx, result)


# ---------------------------------------------------------------------------
# list-types
# ---------------------------------------------------------------------------

@group.command("list-types")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_LIST_TYPES),
    help="Show detailed explanation of this command.",
)
@pass_context
def list_types(ctx):
    """List known hive type names.

    Outputs a static list of all known hive types that can be used
    with the --hive-name option in other hive commands.

    Example:
        limacharlie hive list-types
    """
    _output(ctx, _KNOWN_HIVE_TYPES)


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------

@group.command("export")
@click.option("--hive-name", "name", required=True, help="Hive name (e.g., dr-general, lookup, secret).")
@click.option("--partition-key", default=None, help="Optional partition key (defaults to org OID).")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_EXPORT),
    help="Show detailed explanation of this command.",
)
@pass_context
def export_records(ctx, name, partition_key):
    """Export all records from a hive as YAML.

    Examples:
        limacharlie hive export --hive-name dr-general
        limacharlie hive export --hive-name lookup --output yaml > lookups.yaml
        limacharlie hive export --hive-name secret --partition-key custom-key
    """
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

@group.command("import")
@click.option("--hive-name", "name", required=True, help="Hive name (e.g., dr-general, lookup, secret).")
@click.option("--input-file", required=True, type=click.Path(exists=True), help="Path to YAML or JSON file to import.")
@click.option("--partition-key", default=None, help="Optional partition key (defaults to org OID).")
@click.option("--dry-run", is_flag=True, default=False, help="Preview changes without applying them.")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_IMPORT),
    help="Show detailed explanation of this command.",
)
@pass_context
def import_records(ctx, name, input_file, partition_key, dry_run):
    """Import records into a hive from a YAML or JSON file.

    Each top-level key in the file is a record name.  The value
    should have at minimum a 'data' key.

    Examples:
        limacharlie hive import --hive-name lookup --input-file lookups.yaml
        limacharlie hive import --hive-name dr-general --input-file rules.yaml --dry-run
    """
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
    for record_name, record_data in data.items():
        record = _record_from_input(record_name, record_data)
        if dry_run:
            results[record_name] = {"action": "would_set", "record": record.to_dict()}
            if not ctx.obj.quiet:
                click.echo(f"[dry-run] Would set record '{record_name}' in hive '{name}'.")
        else:
            result = hive.set(record)
            results[record_name] = result
            if not ctx.obj.quiet:
                click.echo(f"Set record '{record_name}' in hive '{name}'.")

    _output(ctx, results)
