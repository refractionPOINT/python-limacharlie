"""AI-oriented help for LimaCharlie CLI.

Generates compact markdown help designed for LLM consumption.
Focuses on context, examples, and discoverability rather than
type signatures.  Activated via ``--ai-help`` on any command or group.
"""

from __future__ import annotations

import click

from .discovery import get_explain, PROFILES


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def show_ai_help(ctx: click.Context) -> None:
    """Generate and display AI-oriented help, then exit."""
    path = _build_path(ctx)
    cmd = ctx.command

    if not path:
        text = _top_level_help(cmd)
    elif isinstance(cmd, click.Group):
        text = _group_help(cmd, path)
    else:
        text = _command_help(cmd, path)

    click.echo(text)
    ctx.exit()


# ---------------------------------------------------------------------------
# Injection — add --ai-help to every command in the tree
# ---------------------------------------------------------------------------

def inject_ai_help(cmd: click.BaseCommand) -> None:
    """Recursively add ``--ai-help`` to *cmd* and all of its descendants."""
    _add_flag(cmd)
    if isinstance(cmd, click.Group):
        for sub in cmd.commands.values():
            inject_ai_help(sub)


def _add_flag(cmd: click.BaseCommand) -> None:
    """Append the ``--ai-help`` option to a single command."""
    # Guard against double-injection.
    if any(getattr(p, "name", None) == "ai_help" for p in cmd.params):
        return

    def _cb(ctx: click.Context, _param: click.Parameter, value: bool) -> None:
        if value:
            show_ai_help(ctx)

    opt = click.Option(
        ["--ai-help"],
        is_flag=True,
        is_eager=True,
        expose_value=False,
        help="Show AI-oriented help for this command.",
        callback=_cb,
    )
    cmd.params.append(opt)


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _build_path(ctx: click.Context) -> list[str]:
    """Walk up the context chain to build the command path (excluding root)."""
    parts: list[str] = []
    c = ctx
    while c.parent is not None:
        parts.append(c.info_name)
        c = c.parent
    parts.reverse()
    return parts


# ---------------------------------------------------------------------------
# Top-level help
# ---------------------------------------------------------------------------

def _top_level_help(cli: click.Group) -> str:
    lines: list[str] = []
    lines.append("# LimaCharlie CLI — AI Help")
    lines.append("")
    lines.append(
        "Command-line interface for the LimaCharlie SecOps Cloud Platform. "
        "Use `--ai-help` on any subcommand to drill down."
    )

    # -- Getting started ---------------------------------------------------
    lines.append("")
    lines.append("## Getting Started")
    lines.append("```")
    lines.append("limacharlie auth login                  # Browser-based OAuth")
    lines.append("limacharlie auth login --api-key KEY --oid OID  # API key auth")
    lines.append("limacharlie auth use-org OID             # Select organization")
    lines.append("limacharlie auth whoami                  # Verify identity & org")
    lines.append("```")

    # -- Command groups (organized by profile) -----------------------------
    lines.append("")
    lines.append("## Commands by Use-Case")

    for profile_name, profile in PROFILES.items():
        heading = profile_name.replace("_", " ").title()
        lines.append("")
        lines.append(f"### {heading}")
        lines.append(profile["description"] + ".")
        lines.append("```")
        for cmd_str in profile["commands"]:
            lines.append(f"limacharlie {cmd_str}")
        lines.append("```")

    # -- All groups alphabetically for reference ---------------------------
    lines.append("")
    lines.append("## All Command Groups")
    lines.append("")

    ctx = click.Context(cli)
    for name in cli.list_commands(ctx):
        sub = cli.get_command(ctx, name)
        if sub is None:
            continue
        short = (sub.get_short_help_str(limit=300) or "").strip()
        lines.append(f"- **{name}** — {short}")

    # -- Global options ----------------------------------------------------
    lines.append("")
    lines.append("## Global Options")
    lines.append("These can appear anywhere on the command line:")
    lines.append("```")
    lines.append("--oid OID          Override organization ID")
    lines.append("--output FORMAT    json | yaml | table | csv | jsonl")
    lines.append("--wide             Don't truncate table columns")
    lines.append("--filter JMESPATH  Filter/transform output")
    lines.append("--fields f1,f2     Select specific output fields")
    lines.append("--quiet            Suppress non-data output")
    lines.append("--debug            Print HTTP request details")
    lines.append("--env NAME         Use a named environment from config")
    lines.append("```")

    # -- Drill-down hint ---------------------------------------------------
    lines.append("")
    lines.append("## Drill Down")
    lines.append("```")
    lines.append("limacharlie sensor --ai-help          # Sensor group overview")
    lines.append("limacharlie sensor list --ai-help     # Specific command detail")
    lines.append("limacharlie help sensors              # Concept guide")
    lines.append("limacharlie cheatsheet common-operations  # Quick examples")
    lines.append("```")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Group-level help
# ---------------------------------------------------------------------------

def _group_help(group: click.Group, path: list[str]) -> str:
    group_name = " ".join(path)
    lines: list[str] = []
    lines.append(f"# limacharlie {group_name} — AI Help")
    lines.append("")

    # Group description
    doc = (group.help or group.short_help or "").strip()
    if doc:
        lines.append(doc)
        lines.append("")

    # Explain text for the group itself (if any)
    explain_key = ".".join(path)
    explain = get_explain(explain_key)
    if explain:
        lines.append(explain.strip())
        lines.append("")

    # Subcommands
    lines.append("## Commands")
    lines.append("")

    for cmd_name in sorted(group.commands):
        sub = group.commands[cmd_name]
        full_name = f"{group_name} {cmd_name}"
        short = (sub.get_short_help_str(limit=300) or "").strip()
        lines.append(f"### {cmd_name}")
        if short:
            lines.append(short)
            lines.append("")

        # Options
        opts = _format_options(sub)
        if opts:
            lines.append("```")
            for opt_line in opts:
                lines.append(opt_line)
            lines.append("```")
            lines.append("")

        # Examples from docstring
        examples = _extract_examples(sub)
        if examples:
            lines.append("```")
            for ex in examples:
                lines.append(ex)
            lines.append("```")
            lines.append("")

        # Explain text
        sub_explain_key = f"{explain_key}.{cmd_name}"
        sub_explain = get_explain(sub_explain_key)
        if sub_explain:
            # Take just the first paragraph as context (not the full essay)
            first_para = sub_explain.strip().split("\n\n")[0]
            lines.append(first_para.strip())
            lines.append("")

    # Related command groups
    related = _find_related_profiles(group_name)
    if related:
        lines.append("## Related")
        for profile_name, profile in related:
            heading = profile_name.replace("_", " ").title()
            lines.append(f"- **{heading}**: {profile['description']}")
        lines.append("")

    # Drill-down hint
    lines.append("## Drill Down")
    lines.append(f"Use `limacharlie {group_name} <command> --ai-help` for detailed help on a specific command.")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Command-level help
# ---------------------------------------------------------------------------

def _command_help(cmd: click.Command, path: list[str]) -> str:
    full_name = " ".join(path)
    lines: list[str] = []
    lines.append(f"# limacharlie {full_name} — AI Help")
    lines.append("")

    # Description
    doc = (cmd.help or cmd.short_help or "").strip()
    if doc:
        lines.append(doc)
        lines.append("")

    # Explain text (full)
    explain_key = ".".join(path)
    explain = get_explain(explain_key)
    if explain:
        lines.append(explain.strip())
        lines.append("")

    # Options
    opts = _format_options(cmd)
    if opts:
        lines.append("## Options")
        lines.append("```")
        for opt_line in opts:
            lines.append(opt_line)
        lines.append("```")
        lines.append("")

    # Examples from docstring
    examples = _extract_examples(cmd)
    if examples:
        lines.append("## Examples")
        lines.append("```")
        for ex in examples:
            lines.append(ex)
        lines.append("```")
        lines.append("")

    # Usage line
    lines.append("## Usage")
    lines.append("```")
    usage_parts = [f"limacharlie {full_name}"]
    for p in cmd.params:
        if isinstance(p, click.Option) and not p.hidden:
            if p.name == "ai_help":
                continue
            flag = p.opts[0] if p.opts else f"--{p.name}"
            if p.is_flag:
                usage_parts.append(f"[{flag}]")
            elif p.required:
                usage_parts.append(f"{flag} <{p.human_readable_name}>")
            else:
                usage_parts.append(f"[{flag} <{p.human_readable_name}>]")
        elif isinstance(p, click.Argument):
            if p.required:
                usage_parts.append(f"<{p.name}>")
            else:
                usage_parts.append(f"[{p.name}]")
    lines.append(" ".join(usage_parts))
    lines.append("```")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_options(cmd: click.BaseCommand) -> list[str]:
    """Return a list of formatted option lines for *cmd*."""
    result: list[str] = []
    for p in cmd.params:
        if not isinstance(p, click.Option):
            continue
        if p.hidden or p.name == "ai_help":
            continue
        flag = ", ".join(p.opts)
        help_text = p.help or ""
        required = " (required)" if p.required else ""
        result.append(f"{flag:30s} {help_text}{required}")
    return result


def _extract_examples(cmd: click.BaseCommand) -> list[str]:
    """Pull ``Example:`` lines from a command's help text."""
    doc = cmd.help or ""
    examples: list[str] = []
    in_example = False
    for raw_line in doc.splitlines():
        line = raw_line.strip()
        if line.lower().startswith("example"):
            in_example = True
            continue
        if in_example:
            if line.startswith("limacharlie ") or line.startswith("$"):
                examples.append(line.lstrip("$ "))
            elif line == "":
                in_example = False
            else:
                # Some examples don't start with 'limacharlie'
                if line and not line.endswith(":"):
                    examples.append(line)
    return examples


def _find_related_profiles(group_name: str) -> list[tuple[str, dict]]:
    """Find discovery profiles that mention commands from *group_name*."""
    results = []
    for pname, pinfo in PROFILES.items():
        for cmd_str in pinfo["commands"]:
            if cmd_str.startswith(group_name + " "):
                results.append((pname, pinfo))
                break
    return results
