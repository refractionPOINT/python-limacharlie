"""Shared factory for hive-shortcut CLI commands (secret, lookup, playbook, etc.)."""

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


def _get_org(ctx: click.Context) -> Organization:
    client = Client(oid=ctx.obj.oid, environment=ctx.obj.environment, print_debug_fn=ctx.obj.debug_fn, debug_full_response=ctx.obj.debug_full, debug_curl=ctx.obj.debug_curl, debug_verbose=ctx.obj.debug_verbose)
    return Organization(client)


def _output(ctx: click.Context, data: Any) -> None:
    fmt = ctx.obj.output_format or detect_output_format()
    if not ctx.obj.quiet:
        click.echo(format_output(data, fmt))


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

    article = "an" if noun_singular[0].lower() in "aeiou" else "a"

    explain_list = f"List all {noun_plural} stored in the '{hive_name}' hive."
    explain_get = f"Get a specific {noun_singular} by its key name from the '{hive_name}' hive."
    explain_set = (
        f"Create or update {article} {noun_singular} in the '{hive_name}' hive. "
        f"Provide data via --input-file (JSON/YAML) or stdin, or use --value to set "
        f"the secret value directly (wrapped as {{data: {{secret: <value>}}}}). "
        f"WARNING: --value exposes the value on the command line and in shell history; "
        f"stdin or --input-file is the recommended path for humans. "
        f"--tag (repeatable) and --comment populate usr_mtd. "
        f"New hive records default to disabled — pass --enabled to create-and-enable in one shot, "
        f"or include usr_mtd.enabled: true in the input file."
    )
    explain_delete = f"Delete {article} {noun_singular} from the '{hive_name}' hive. Requires --confirm for safety."

    @click.group(group_name)
    def grp() -> None:
        pass

    grp.help = f"Manage {noun_plural}."

    @grp.command("list", help=f"List all {noun_plural}.")
    @pass_context
    def list_cmd(ctx) -> None:
        org = _get_org(ctx)
        hive = Hive(org, hive_name)
        records = hive.list()
        data = {name: rec.to_dict() for name, rec in records.items()}
        _output(ctx, data)

    @grp.command("get", help=f"Get {article} {noun_singular} by key.")
    @click.option("--key", required=True, help="Record key name.")
    @pass_context
    def get_cmd(ctx, key) -> None:
        org = _get_org(ctx)
        hive = Hive(org, hive_name)
        record = hive.get(key)
        _output(ctx, record.to_dict())

    @grp.command("set", help=f"Create or update {article} {noun_singular}.")
    @click.option("--key", required=True, help="Record key name.")
    @click.option("--input-file", type=click.Path(exists=True), default=None, help="JSON or YAML file with record data.")
    @click.option(
        "--value", default=None,
        help="Set the secret value directly (wraps into {data: {secret: <value>}}). "
             "WARNING: this exposes the value on the command line and in shell history; "
             "stdin or --input-file remains the recommended path for humans.",
    )
    @click.option("--tag", "tags", multiple=True, help="Tag to set in usr_mtd (repeatable).")
    @click.option("--comment", default=None, help="Set usr_mtd.comment on the record.")
    @click.option(
        "--enabled/--disabled", "enabled", default=None,
        help=f"Set usr_mtd.enabled on the {noun_singular}. Overrides any value in the input file. Records default to disabled if neither this flag nor usr_mtd.enabled is provided.",
    )
    @pass_context
    def set_cmd(ctx, key, input_file, value, tags, comment, enabled) -> None:
        if value is not None:
            if input_file:
                raise click.UsageError("--value is mutually exclusive with --input-file/stdin.")
            # Convenience wrapper so a secret value can be set without a
            # file or stdin.  --value is explicit intent, so stdin is ignored
            # in this mode rather than consulted.
            record = HiveRecord(key, data={"secret": value})
        else:
            if input_file:
                with open(input_file, "r") as f:
                    content = f.read()
            elif not sys.stdin.isatty():
                content = sys.stdin.read()
            else:
                raise click.UsageError("Provide data via --value, --input-file, or pipe to stdin.")

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
        if tags:
            record.tags = list(tags)
        if comment is not None:
            record.comment = comment
        if enabled is not None:
            record.enabled = enabled
        org = _get_org(ctx)
        hive = Hive(org, hive_name)
        result = hive.set(record)
        _output(ctx, result)

    @grp.command("delete", help=f"Delete {article} {noun_singular}.")
    @click.option("--key", required=True, help="Record key name.")
    @click.option("--confirm", is_flag=True, default=False, help="Confirm deletion.")
    @pass_context
    def delete_cmd(ctx, key, confirm) -> None:
        if not confirm:
            raise click.UsageError("Destructive operation requires --confirm flag.")
        org = _get_org(ctx)
        hive = Hive(org, hive_name)
        result = hive.delete(key)
        _output(ctx, result)

    @grp.command("enable", help=f"Enable {article} {noun_singular}.")
    @click.option("--key", required=True, help="Record key name.")
    @pass_context
    def enable_cmd(ctx, key) -> None:
        org = _get_org(ctx)
        hive = Hive(org, hive_name)
        record = hive.get_metadata(key)
        record.enabled = True
        result = hive.set(record)
        _output(ctx, result)

    @grp.command("disable", help=f"Disable {article} {noun_singular}.")
    @click.option("--key", required=True, help="Record key name.")
    @pass_context
    def disable_cmd(ctx, key) -> None:
        org = _get_org(ctx)
        hive = Hive(org, hive_name)
        record = hive.get_metadata(key)
        record.enabled = False
        result = hive.set(record)
        _output(ctx, result)

    @grp.group("tag", help=f"Manage tags on {noun_plural}.")
    def tag_group() -> None:
        pass

    def _merge_tags(existing: list[str] | None, changes: tuple[str, ...], remove: bool) -> list[str]:
        if remove:
            to_remove = {t.lower() for t in changes}
            return [t for t in (existing or []) if t.lower() not in to_remove]
        seen: dict[str, str] = {}
        for tag in (existing or []) + list(changes):
            k = tag.lower()
            if k not in seen:
                seen[k] = tag
        return list(seen.values())

    @tag_group.command("set", help=f"Replace all tags on {article} {noun_singular}.")
    @click.option("--key", required=True, help="Record key name.")
    @click.option("--tag", "-t", "tags", multiple=True, required=True, help="Tag value (repeatable).")
    @pass_context
    def tag_set_cmd(ctx, key, tags) -> None:
        org = _get_org(ctx)
        hive = Hive(org, hive_name)
        record = hive.get_metadata(key)
        record.tags = list(tags)
        result = hive.set(record)
        _output(ctx, result)

    @tag_group.command("add", help=f"Add tags to {article} {noun_singular} (merged with existing).")
    @click.option("--key", required=True, help="Record key name.")
    @click.option("--tag", "-t", "tags", multiple=True, required=True, help="Tag value to add (repeatable).")
    @pass_context
    def tag_add_cmd(ctx, key, tags) -> None:
        org = _get_org(ctx)
        hive = Hive(org, hive_name)
        record = hive.get_metadata(key)
        record.tags = _merge_tags(record.tags, tags, remove=False)
        result = hive.set(record)
        _output(ctx, result)

    @tag_group.command("rm", help=f"Remove tags from {article} {noun_singular}.")
    @click.option("--key", required=True, help="Record key name.")
    @click.option("--tag", "-t", "tags", multiple=True, required=True, help="Tag value to remove (repeatable).")
    @pass_context
    def tag_rm_cmd(ctx, key, tags) -> None:
        org = _get_org(ctx)
        hive = Hive(org, hive_name)
        record = hive.get_metadata(key)
        record.tags = _merge_tags(record.tags, tags, remove=True)
        result = hive.set(record)
        _output(ctx, result)

    # Register explain texts.
    register_explain(f"{group_name}.list", explain_list)
    register_explain(f"{group_name}.get", explain_get)
    register_explain(f"{group_name}.set", explain_set)
    register_explain(f"{group_name}.delete", explain_delete)
    register_explain(f"{group_name}.enable", f"Enable {article} {noun_singular} by key (sets usr_mtd.enabled to true).")
    register_explain(f"{group_name}.disable", f"Disable {article} {noun_singular} by key (sets usr_mtd.enabled to false).")
    register_explain(f"{group_name}.tag.set", f"Replace all tags on {article} {noun_singular} (fetch metadata, set tags).")
    register_explain(f"{group_name}.tag.add", f"Add tags to {article} {noun_singular}, merged additively with existing tags.")
    register_explain(f"{group_name}.tag.rm", f"Remove tags from {article} {noun_singular}, keeping the rest.")

    return grp
