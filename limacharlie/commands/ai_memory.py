"""AI memory commands for LimaCharlie CLI v2.

Wraps the ``ai_memory`` hive — a per-agent key/value store with a
server-side partial-merge hook. Each Hive record (keyed by an agent
identifier) holds a ``memories`` map of filesystem-style names to
memory contents. Submitting a single memory name updates only that
entry; the rest of the record is preserved by the hook.

Every read/write/delete sub-command requires both ``--key`` (the agent
identifier / hive record key) and ``--memory-name`` (the entry within
that record). Use ``delete-record`` to remove an entire agent record.
"""

from __future__ import annotations

import sys
from typing import Any

import click

from ..cli import pass_context
from ..client import Client
from ..sdk.ai_memory import AiMemory
from ..sdk.organization import Organization
from ..output import format_output, detect_output_format
from ..discovery import register_explain


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_org(ctx: click.Context) -> Organization:
    client = Client(
        oid=ctx.obj.oid,
        environment=ctx.obj.environment,
        print_debug_fn=ctx.obj.debug_fn,
        debug_full_response=ctx.obj.debug_full,
        debug_curl=ctx.obj.debug_curl,
        debug_verbose=ctx.obj.debug_verbose,
    )
    return Organization(client)


def _output(ctx: click.Context, data: Any) -> None:
    fmt = ctx.obj.output_format or detect_output_format()
    if not ctx.obj.quiet:
        click.echo(format_output(data, fmt))


def _read_content(content: str | None, input_file: str | None) -> str:
    """Resolve memory content from --content, --input-file, or stdin."""
    if content is not None:
        return content
    if input_file:
        with open(input_file, "r") as f:
            return f.read()
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise click.UsageError(
        "Provide memory content via --content, --input-file, or stdin."
    )


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------

@click.group("ai-memory")
def group() -> None:
    """Manage AI agent memory entries (partial-merge hive).

    Each agent has one record in the ``ai_memory`` hive, keyed by its
    identifier. Within that record, individual memories are addressed
    by ``--memory-name``. Writes are partial: a Set on one memory name
    leaves the other memories on the same record untouched.
    """


# ---------------------------------------------------------------------------
# list-records
# ---------------------------------------------------------------------------

_EXPLAIN_LIST_RECORDS = """\
List every agent record stored in the ``ai_memory`` hive.  The output
is keyed by agent identifier; the per-agent ``memories`` map (if any)
appears under ``data.memories``.

To list memory entries for a single agent, use ``ai-memory list``
with ``--key <agent>``.
"""
register_explain("ai-memory.list-records", _EXPLAIN_LIST_RECORDS)


@group.command("list-records")
@pass_context
def list_records(ctx) -> None:
    """List every agent record (and their memory maps)."""
    org = _get_org(ctx)
    am = AiMemory(org)
    records = am.list_records()
    _output(ctx, {name: rec.to_dict() for name, rec in records.items()})


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

_EXPLAIN_LIST = """\
List the memory entries stored under one agent record.  Returns a flat
mapping of memory name to memory content for the record identified by
``--key``.

Use ``ai-memory list-records`` to enumerate every agent.
"""
register_explain("ai-memory.list", _EXPLAIN_LIST)


@group.command("list")
@click.option("--key", required=True, help="Agent identifier (hive record key).")
@pass_context
def list_memories(ctx, key) -> None:
    """List memory entries for one agent record."""
    org = _get_org(ctx)
    am = AiMemory(org)
    _output(ctx, am.list_memories(key))


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------

_EXPLAIN_GET = """\
Fetch a single memory entry's content by name.  Returns the raw
content string for the memory ``--memory-name`` within the agent
record ``--key``.

If the memory does not exist on the record, exits non-zero with an
empty result.
"""
register_explain("ai-memory.get", _EXPLAIN_GET)


@group.command("get")
@click.option("--key", required=True, help="Agent identifier (hive record key).")
@click.option("--memory-name", required=True, help="Memory entry name within the agent record.")
@pass_context
def get_memory(ctx, key, memory_name) -> None:
    """Get a single memory entry's content."""
    org = _get_org(ctx)
    am = AiMemory(org)
    content = am.get(key, memory_name)
    if content is None:
        if not ctx.obj.quiet:
            click.echo(
                f"Error: memory '{memory_name}' not found on agent '{key}'.",
                err=True,
            )
        ctx.exit(4)
        return
    fmt = ctx.obj.output_format or detect_output_format()
    if fmt in ("json", "yaml", "toon"):
        _output(ctx, {"key": key, "memory_name": memory_name, "content": content})
    else:
        click.echo(content)


# ---------------------------------------------------------------------------
# set
# ---------------------------------------------------------------------------

_EXPLAIN_SET = """\
Create or replace a single memory entry on an agent record.  Sends
``{"memories": {<memory-name>: <content>}}`` only; the server-side
partial-merge hook leaves every other memory on the record untouched.

Content sources (in priority order):
  1. ``--content`` flag
  2. ``--input-file`` path
  3. stdin (when piped)

Examples:
  limacharlie ai-memory set --key triage-bot --memory-name notes/today \\
      --content "wrote the cli wrapper"

  cat notes.md | limacharlie ai-memory set --key triage-bot \\
      --memory-name notes/today

The ``--memory-name`` follows a filesystem-style naming rule (relative
path, forward slashes only, no traversal above the record root, max
256 chars). The hive enforces these rules server-side.
"""
register_explain("ai-memory.set", _EXPLAIN_SET)


@group.command("set")
@click.option("--key", required=True, help="Agent identifier (hive record key).")
@click.option("--memory-name", required=True, help="Memory entry name within the agent record.")
@click.option("--content", default=None, help="Memory content (string). If omitted, reads --input-file or stdin.")
@click.option("--input-file", type=click.Path(exists=True), default=None, help="Path to a file whose contents become the memory.")
@pass_context
def set_memory(ctx, key, memory_name, content, input_file) -> None:
    """Create or replace one memory entry (partial-merge)."""
    body = _read_content(content, input_file)
    org = _get_org(ctx)
    am = AiMemory(org)
    result = am.set(key, memory_name, body)
    if not ctx.obj.quiet:
        click.echo(
            f"Memory '{memory_name}' set on agent '{key}' "
            f"(other memories on the record are preserved)."
        )
    _output(ctx, result)


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

_EXPLAIN_DELETE = """\
Delete a single memory entry from an agent record.  Sends
``{"memories": {<memory-name>: null}}`` so the partial-merge hook
drops just that one entry; every other memory on the record is
preserved.

Use ``ai-memory delete-record`` to remove the whole agent record.

Requires --confirm.
"""
register_explain("ai-memory.delete", _EXPLAIN_DELETE)


@group.command("delete")
@click.option("--key", required=True, help="Agent identifier (hive record key).")
@click.option("--memory-name", required=True, help="Memory entry name within the agent record.")
@click.option("--confirm", is_flag=True, default=False, help="Confirm deletion (required).")
@pass_context
def delete_memory(ctx, key, memory_name, confirm) -> None:
    """Delete one memory entry (partial-merge)."""
    if not confirm:
        click.echo(
            "Error: Destructive operation requires --confirm flag.\n"
            "Suggestion: Re-run with --confirm to drop the memory entry.",
            err=True,
        )
        ctx.exit(4)
        return
    org = _get_org(ctx)
    am = AiMemory(org)
    result = am.delete(key, memory_name)
    if not ctx.obj.quiet:
        click.echo(f"Memory '{memory_name}' dropped from agent '{key}'.")
    _output(ctx, result)


# ---------------------------------------------------------------------------
# delete-record
# ---------------------------------------------------------------------------

_EXPLAIN_DELETE_RECORD = """\
Delete an entire agent record from the ``ai_memory`` hive.  This drops
every memory entry the agent had stored.  Use ``ai-memory delete``
with --memory-name to drop a single entry instead.

Requires --confirm.
"""
register_explain("ai-memory.delete-record", _EXPLAIN_DELETE_RECORD)


@group.command("delete-record")
@click.option("--key", required=True, help="Agent identifier (hive record key) to delete entirely.")
@click.option("--confirm", is_flag=True, default=False, help="Confirm deletion (required).")
@pass_context
def delete_record(ctx, key, confirm) -> None:
    """Delete an entire agent record (all memories)."""
    if not confirm:
        click.echo(
            "Error: Destructive operation requires --confirm flag.\n"
            "Suggestion: Re-run with --confirm to delete the entire agent record.",
            err=True,
        )
        ctx.exit(4)
        return
    org = _get_org(ctx)
    am = AiMemory(org)
    result = am.delete_record(key)
    if not ctx.obj.quiet:
        click.echo(f"Agent record '{key}' deleted (all memories dropped).")
    _output(ctx, result)
