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
from ..errors import PermissionDeniedError


def _get_org(ctx: click.Context) -> Organization:
    client = Client(oid=ctx.obj.oid, environment=ctx.obj.environment, print_debug_fn=ctx.obj.debug_fn, debug_full_response=ctx.obj.debug_full, debug_curl=ctx.obj.debug_curl, debug_verbose=ctx.obj.debug_verbose)
    return Organization(client)


def _output(ctx: click.Context, data: Any) -> None:
    fmt = ctx.obj.output_format or detect_output_format()
    if not ctx.obj.quiet:
        click.echo(format_output(data, fmt))


def input_metadata_block(data: Any) -> dict[str, Any] | None:
    """Return the ``usr_mtd`` block of parsed set input.

    Args:
        data: Parsed JSON/YAML input.

    Returns:
        dict | None: The block, or None when absent or null (a bare
            ``usr_mtd:`` in YAML counts as absent).

    Raises:
        click.UsageError: If the block is not a mapping.
    """
    if not isinstance(data, dict) or data.get("usr_mtd") is None:
        return None
    if not isinstance(data["usr_mtd"], dict):
        raise click.UsageError("usr_mtd must be a mapping of metadata fields.")
    return data["usr_mtd"]


def merge_current_metadata_or_warn(hive: Hive, hive_name: str, record: HiveRecord, enabled_explicit: bool = False) -> None:
    """Start ``record``'s metadata from the stored record, before metadata flags are applied.

    A metadata block replaces the stored metadata wholesale, and one sent
    without ``enabled`` stores the record disabled, so sending only the fields
    being changed would silently disable a live record or drop its tags,
    comment, expiry and ui_actions. This keeps every field the caller is not
    changing. A record that does not exist yet is created with the flags as
    given; when the caller did not choose ``enabled`` that means disabled,
    which is said on stderr so nobody finds out from a rule that never fires.
    Reading metadata takes its own ``<hive>.get.mtd`` permission. When that
    is denied and the caller chose ``enabled``, the flags are sent as given,
    with a warning, as they were before merging existed. Other errors
    propagate.

    Args:
        hive: Hive the record is written to.
        hive_name: Its name, for the warning.
        record: Record about to be written, with the caller's edits not yet applied.
        enabled_explicit: Whether the caller passed --enabled/--disabled.
    """
    try:
        exists = hive.merge_current_metadata(record)
    except PermissionDeniedError:
        if not enabled_explicit:
            raise
        click.echo(
            f"Warning: cannot read the metadata of record '{record.name}' in hive "
            f"'{hive_name}' (permission denied), so the metadata flags replace it: "
            "existing tags, comment and expiry are not kept.",
            err=True,
        )
        return
    if exists or enabled_explicit:
        return
    click.echo(
        f"Warning: record '{record.name}' does not exist in hive '{hive_name}', so the new "
        "record is created DISABLED because metadata was supplied without "
        "--enabled. Pass --enabled to activate it.",
        err=True,
    )
    # What the API stores for a metadata block without "enabled" anyway; sent
    # explicitly so the warning above stays true by construction.
    record.enabled = False


def make_hive_group(group_name: str, hive_name: str, noun_singular: str, noun_plural: str | None = None, value_key: str | None = None, index_keys: tuple[str, ...] | None = None, explain_prefix: str | None = None) -> click.Group:
    """Create a Click group for a specific hive type.

    Args:
        group_name: CLI group name (e.g., "secret").
        hive_name: Hive backend name (e.g., "secret").
        noun_singular: Human-readable singular (e.g., "secret").
        noun_plural: Human-readable plural (defaults to noun_singular + "s").
        value_key: Name of the single scalar field in the record's ``data``
            payload for hives whose value is one scalar (e.g. ``"secret"`` for
            the secret hive, whose data is ``{secret: <value>}``). When set, the
            'set' command gains a ``--value`` convenience flag that wraps the
            value as ``{data: {<value_key>: <value>}}``. Leave None for hives
            whose data is structured (lookup, fp, playbook, …) — they have no
            single value field and do not get ``--value``.
        index_keys: ``data`` fields that summarize a record well enough to
            decide whether it is worth fetching in full (e.g. ``("description",)``
            for the sop hive). When set, 'list' gains a ``--brief`` flag that
            keeps only these fields in each record's ``data``. The listing
            endpoint returns whole records, so for hives whose payload is a
            document this is the difference between an index and every body —
            it matters most when the consumer is an LLM paying for the output
            in context. Set it for hives that carry a body plus a field
            describing it (sop, org_notes, ai_skill); leave None for hives
            whose ``data`` is structured config with no such split, where
            there is no honest subset to call a summary.

            Note that a hive setting this should also mention ``--brief`` in
            its own ``<group>.list`` explain text if it registers one:
            ``register_explain`` is last-write-wins, so a module-level
            override replaces whatever the factory registered.
        explain_prefix: Dotted ``--ai-help`` path the group is mounted at, for
            groups nested under another command (e.g. ``"app-control.policy"``
            for a ``policy`` group inside ``app-control``). Explain texts are
            looked up by the full command path, so a nested group registered
            under its bare ``group_name`` would never be found. Defaults to
            ``group_name`` for top-level groups.

    Returns:
        click.Group: The configured group with list, get, set, delete commands.
    """
    if explain_prefix is None:
        explain_prefix = group_name
    if noun_plural is None:
        noun_plural = noun_singular + "s"

    article = "an" if noun_singular[0].lower() in "aeiou" else "a"

    explain_list = f"List all {noun_plural} stored in the '{hive_name}' hive."
    explain_get = f"Get a specific {noun_singular} by its key name from the '{hive_name}' hive."
    value_hint = (
        f"Or use --value to set the {noun_singular} value directly "
        f"(wrapped as {{data: {{{value_key}: <value>}}}}); --value exposes the value "
        f"on the command line and in shell history, so stdin or --input-file is the "
        f"recommended path for humans. "
        if value_key else ""
    )
    explain_set = (
        f"Create or update {article} {noun_singular} in the '{hive_name}' hive. "
        f"Provide data via --input-file (JSON/YAML) or stdin. "
        f"{value_hint}"
        f"--tag (repeatable) and --comment populate usr_mtd. "
        f"With --tag/--comment/--enabled/--disabled and no usr_mtd in the input, the record's current "
        f"metadata is kept and only the flagged fields change (--tag replaces the tag list). A record that "
        f"does not exist yet is created disabled, with a warning, unless --enabled is passed. "
        f"With no metadata at all, a new record gets the hive's own default (most hives: disabled; "
        f"cloudsec_policy, acl and the app-control hives: enabled). "
        f"Pass --enabled/--disabled, or set usr_mtd.enabled in the input file, to be explicit."
    )
    explain_delete = f"Delete {article} {noun_singular} from the '{hive_name}' hive. Requires --confirm for safety."

    @click.group(group_name)
    def grp() -> None:
        pass

    grp.help = f"Manage {noun_plural}."

    def _brief_option(fn):
        # Only hives that named their index fields expose --brief; for the rest
        # there is no meaningful subset of `data` to keep, so no flag is offered.
        if not index_keys:
            return fn
        return click.option(
            "--brief", is_flag=True, default=False,
            help=f"Keep only {', '.join(index_keys)} in each record's data, dropping the "
                 f"rest of the payload. Metadata is unaffected.",
        )(fn)

    @grp.command("list", help=f"List all {noun_plural}.")
    @_brief_option
    @pass_context
    def list_cmd(ctx, brief: bool = False) -> None:
        org = _get_org(ctx)
        hive = Hive(org, hive_name)
        records = hive.list()
        data = {name: rec.to_dict() for name, rec in records.items()}
        if brief:
            for record in data.values():
                payload = record.get("data")
                if payload is None:
                    # No payload to summarize; "absent" is not the same as
                    # "filtered", so leave it alone.
                    continue
                if not isinstance(payload, dict):
                    # A record whose data is not an object has none of the
                    # index fields. Emitting it whole would quietly hand back
                    # the payload the caller asked us to drop, so fail closed.
                    record["data"] = {}
                    continue
                record["data"] = {k: payload[k] for k in index_keys if k in payload}
        _output(ctx, data)

    @grp.command("get", help=f"Get {article} {noun_singular} by key.")
    @click.option("--key", required=True, help="Record key name.")
    @pass_context
    def get_cmd(ctx, key) -> None:
        org = _get_org(ctx)
        hive = Hive(org, hive_name)
        record = hive.get(key)
        _output(ctx, record.to_dict())

    def _value_option(fn):
        # Only hives with a single scalar value field (value_key set, e.g.
        # the secret hive) expose --value; structured-data hives do not, so
        # there is no misleading flag and no hardcoded data-key assumption.
        if value_key is None:
            return fn
        return click.option(
            "--value", default=None,
            help=f"Set the {noun_singular} value directly (wraps into {{data: {{{value_key}: <value>}}}}). "
                 "WARNING: this exposes the value on the command line and in shell history; "
                 "stdin or --input-file remains the recommended path for humans.",
        )(fn)

    @grp.command("set", help=f"Create or update {article} {noun_singular}.")
    @click.option("--key", required=True, help="Record key name.")
    @click.option("--input-file", type=click.Path(exists=True), default=None, help="JSON or YAML file with record data.")
    @_value_option
    @click.option("--tag", "tags", multiple=True, help="Tag to set in usr_mtd (repeatable).")
    @click.option("--comment", default=None, help="Set usr_mtd.comment on the record.")
    @click.option(
        "--enabled/--disabled", "enabled", default=None,
        help=f"Set usr_mtd.enabled on the {noun_singular}. Overrides any value in the input file. Without metadata, a new record gets the hive's own default (most hives: disabled). With metadata flags and no usr_mtd in the input, an existing record keeps the metadata the flags do not change; a new record without --enabled is created disabled (with a warning).",
    )
    @pass_context
    def set_cmd(ctx, key, input_file, tags, comment, enabled, value=None) -> None:
        input_has_mtd = False
        if value is not None:
            if input_file:
                raise click.UsageError("--value is mutually exclusive with --input-file/stdin.")
            # Convenience wrapper so a single-value record (value_key set) can
            # be set without a file or stdin.  --value is explicit intent, so
            # stdin is ignored in this mode rather than consulted.
            record = HiveRecord(key, data={value_key: value})
        else:
            if input_file:
                with open(input_file, "r") as f:
                    content = f.read()
            elif not sys.stdin.isatty():
                content = sys.stdin.read()
            else:
                hint = "--value, --input-file, or pipe to stdin" if value_key else "--input-file or pipe to stdin"
                raise click.UsageError(f"Provide data via {hint}.")

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
                usr = input_metadata_block(data)
                input_has_mtd = usr is not None
                raw = {
                    "data": data["data"],
                    "usr_mtd": usr or {},
                    "sys_mtd": {},
                }
                if data.get("etag"):
                    raw["sys_mtd"]["etag"] = data["etag"]
                record = HiveRecord.from_raw(key, raw)
                # As in 'hive set': a supplied block is explicit, and the API
                # stores one without "enabled" as disabled, even {}.
                if input_has_mtd and record.enabled is None:
                    record.enabled = False
            else:
                record = HiveRecord(key, data=data)
        org = _get_org(ctx)
        hive = Hive(org, hive_name)
        if (tags or comment is not None or enabled is not None) and not input_has_mtd:
            # The flags are sent as the whole metadata block, so start from the
            # stored one or the record loses its enabled state or other fields.
            merge_current_metadata_or_warn(hive, hive_name, record, enabled is not None)
        if tags:
            record.tags = list(tags)
        if comment is not None:
            record.comment = comment
        if enabled is not None:
            record.enabled = enabled
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
    register_explain(f"{explain_prefix}.list", explain_list)
    register_explain(f"{explain_prefix}.get", explain_get)
    register_explain(f"{explain_prefix}.set", explain_set)
    register_explain(f"{explain_prefix}.delete", explain_delete)
    register_explain(f"{explain_prefix}.enable", f"Enable {article} {noun_singular} by key (sets usr_mtd.enabled to true).")
    register_explain(f"{explain_prefix}.disable", f"Disable {article} {noun_singular} by key (sets usr_mtd.enabled to false).")
    register_explain(f"{explain_prefix}.tag.set", f"Replace all tags on {article} {noun_singular} (fetch metadata, set tags).")
    register_explain(f"{explain_prefix}.tag.add", f"Add tags to {article} {noun_singular}, merged additively with existing tags.")
    register_explain(f"{explain_prefix}.tag.rm", f"Remove tags from {article} {noun_singular}, keeping the rest.")

    return grp
