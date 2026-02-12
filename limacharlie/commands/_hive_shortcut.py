"""Shared factory for hive-shortcut CLI commands (secret, lookup, playbook, etc.)."""

from __future__ import annotations

import json
import sys
from typing import Any, Callable

import click
import yaml

from ..cli import pass_context
from ..config import resolve_credentials
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.hive import Hive, HiveRecord
from ..output import format_output, detect_output_format
from ..discovery import register_explain


def _get_org(ctx: click.Context) -> Organization:
    creds = resolve_credentials(oid=ctx.obj.oid, environment=ctx.obj.environment)
    client = Client(oid=creds["oid"], api_key=creds.get("api_key"), uid=creds.get("uid"))
    return Organization(client)


def _output(ctx: click.Context, data: Any) -> None:
    fmt = ctx.obj.output_format or detect_output_format()
    if not ctx.obj.quiet:
        click.echo(format_output(data, fmt))


def _make_explain_callback(text: str) -> Callable[[click.Context, click.Parameter, bool], None]:
    def callback(ctx, param, value):
        if value:
            click.echo(text)
            ctx.exit(0)
    return callback


def make_hive_group(group_name: str, hive_name: str, noun_singular: str, noun_plural: str | None = None) -> click.Group:
    """Create a Click group for a specific hive type.

    Args:
        group_name: CLI group name (e.g., "secret").
        hive_name: Hive backend name (e.g., "secret").
        noun_singular: Human-readable singular (e.g., "secret").
        noun_plural: Human-readable plural (defaults to noun_singular + "s").

    Returns:
        click.Group: The configured group with list, get, set, delete commands.
    """
    if noun_plural is None:
        noun_plural = noun_singular + "s"

    explain_list = f"List all {noun_plural} stored in the '{hive_name}' hive."
    explain_get = f"Get a specific {noun_singular} by its key name from the '{hive_name}' hive."
    explain_set = f"Create or update a {noun_singular} in the '{hive_name}' hive. Provide data via --input-file (JSON/YAML) or stdin."
    explain_delete = f"Delete a {noun_singular} from the '{hive_name}' hive. Requires --confirm for safety."

    @click.group(group_name)
    def grp() -> None:
        pass

    grp.help = f"Manage {noun_plural} in the {hive_name} hive."

    @grp.command("list")
    @click.option("--explain", is_flag=True, is_eager=True, expose_value=False, callback=_make_explain_callback(explain_list))
    @pass_context
    def list_cmd(ctx) -> None:
        """List all records."""
        org = _get_org(ctx)
        hive = Hive(org, hive_name)
        records = hive.list()
        data = {name: rec.to_dict() for name, rec in records.items()}
        _output(ctx, data)

    @grp.command("get")
    @click.option("--key", required=True, help="Record key name.")
    @click.option("--explain", is_flag=True, is_eager=True, expose_value=False, callback=_make_explain_callback(explain_get))
    @pass_context
    def get_cmd(ctx, key) -> None:
        """Get a record by key."""
        org = _get_org(ctx)
        hive = Hive(org, hive_name)
        record = hive.get(key)
        _output(ctx, record.to_dict())

    @grp.command("set")
    @click.option("--key", required=True, help="Record key name.")
    @click.option("--input-file", type=click.Path(exists=True), default=None, help="JSON or YAML file with record data.")
    @click.option("--explain", is_flag=True, is_eager=True, expose_value=False, callback=_make_explain_callback(explain_set))
    @pass_context
    def set_cmd(ctx, key, input_file) -> None:
        """Create or update a record."""
        if input_file:
            with open(input_file, "r") as f:
                content = f.read()
        elif not sys.stdin.isatty():
            content = sys.stdin.read()
        else:
            raise click.UsageError("Provide data via --input-file or pipe to stdin.")

        # Parse input as YAML first (YAML is a superset of JSON)
        try:
            data = yaml.safe_load(content)
        except Exception:
            data = json.loads(content)

        # Support the same format as 'hive set': if the input has a
        # "data" key, use it as the record data and extract usr_mtd.
        if isinstance(data, dict) and "data" in data:
            # Build a raw dict matching the API format so HiveRecord
            # picks up usr_mtd and etag correctly.
            raw = {
                "data": data["data"],
                "usr_mtd": data.get("usr_mtd", {}),
                "sys_mtd": {},
            }
            if data.get("etag"):
                raw["sys_mtd"]["etag"] = data["etag"]
            record = HiveRecord.from_raw(key, raw)
        else:
            record = HiveRecord(key, data=data)
        org = _get_org(ctx)
        hive = Hive(org, hive_name)
        result = hive.set(record)
        _output(ctx, result)

    @grp.command("delete")
    @click.option("--key", required=True, help="Record key name.")
    @click.option("--confirm", is_flag=True, default=False, help="Confirm deletion.")
    @click.option("--explain", is_flag=True, is_eager=True, expose_value=False, callback=_make_explain_callback(explain_delete))
    @pass_context
    def delete_cmd(ctx, key, confirm) -> None:
        """Delete a record."""
        if not confirm:
            raise click.UsageError("Destructive operation requires --confirm flag.")
        org = _get_org(ctx)
        hive = Hive(org, hive_name)
        result = hive.delete(key)
        _output(ctx, result)

    # Register explain texts.
    register_explain(f"{group_name}.list", explain_list)
    register_explain(f"{group_name}.get", explain_get)
    register_explain(f"{group_name}.set", explain_set)
    register_explain(f"{group_name}.delete", explain_delete)

    return grp
