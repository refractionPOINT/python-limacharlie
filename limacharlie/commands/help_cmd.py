"""Help, discovery, and cheatsheet commands for LimaCharlie CLI v2.

Provides inline help topics, command discovery by use-case profile,
and quick-reference cheatsheets.
"""

from __future__ import annotations

from typing import Callable

import click

from ..cli import pass_context
from ..help_topics import get_help_topic, list_help_topics, get_cheatsheet, list_cheatsheets
from ..discovery import format_discovery, register_explain


# ---------------------------------------------------------------------------
# Explain texts
# ---------------------------------------------------------------------------

_EXPLAIN_TOPIC = """\
Show an inline help topic.  Topics provide concept guides for
LimaCharlie features such as D&R rules, hive data, LCQL queries,
sensors, and more.

Use without arguments to list all available topics.

Examples:
  limacharlie help topic
  limacharlie help topic d&r-rules
  limacharlie help topic lcql
"""

_EXPLAIN_DISCOVER = """\
Discover available CLI commands grouped by use-case profile.
Profiles organize commands by workflow (e.g., sensor management,
detection engineering, live investigation).

Use --profile to filter by a specific profile.

Examples:
  limacharlie help discover
  limacharlie help discover --profile detection_engineering
"""

_EXPLAIN_CHEATSHEET = """\
Show a quick-reference cheatsheet.  Cheatsheets provide common
command examples for frequent workflows.

Use without arguments to list all available cheatsheets.

Examples:
  limacharlie help cheatsheet
  limacharlie help cheatsheet --name getting-started
"""

register_explain("help.topic", _EXPLAIN_TOPIC)
register_explain("help.discover", _EXPLAIN_DISCOVER)
register_explain("help.cheatsheet", _EXPLAIN_CHEATSHEET)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_explain_callback(text: str) -> Callable[[click.Context, click.Parameter, bool], None]:
    def callback(ctx: click.Context, param: click.Parameter, value: bool) -> None:
        if value:
            click.echo(text.strip())
            ctx.exit()
    return callback


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------

@click.group("help", invoke_without_command=True)
@click.pass_context
def group(ctx) -> None:
    """Inline help topics, command discovery, and cheatsheets.

    Use 'limacharlie help topic <name>' for concept guides.
    Use 'limacharlie help discover' to explore commands by use-case.
    Use 'limacharlie help cheatsheet' for quick-reference examples.
    """
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


# ---------------------------------------------------------------------------
# topic
# ---------------------------------------------------------------------------

@group.command()
@click.argument("name", required=False, default=None)
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_TOPIC),
    help="Show detailed explanation of this command.",
)
def topic(name) -> None:
    """Show a help topic (or list all topics).

    Examples:
        limacharlie help topic
        limacharlie help topic d&r-rules
    """
    if name is None:
        topics = list_help_topics()
        if not topics:
            click.echo("No help topics available yet.")
            return
        click.echo("Available help topics:")
        for t in topics:
            click.echo(f"  {t}")
        click.echo("\nUse 'limacharlie help topic <name>' to read a topic.")
        return

    content = get_help_topic(name)
    if content is None:
        topics = list_help_topics()
        click.echo(f"Unknown help topic: {name}", err=True)
        if topics:
            click.echo(f"Available topics: {', '.join(topics)}", err=True)
        raise SystemExit(3)

    click.echo(content)


# ---------------------------------------------------------------------------
# discover
# ---------------------------------------------------------------------------

@group.command()
@click.option("--profile", default=None, help="Filter by use-case profile name.")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_DISCOVER),
    help="Show detailed explanation of this command.",
)
def discover(profile) -> None:
    """Discover commands by use-case profile.

    Examples:
        limacharlie help discover
        limacharlie help discover --profile detection_engineering
    """
    click.echo(format_discovery(profile_name=profile))


# ---------------------------------------------------------------------------
# cheatsheet
# ---------------------------------------------------------------------------

@group.command()
@click.option("--name", default=None, help="Cheatsheet name.")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_CHEATSHEET),
    help="Show detailed explanation of this command.",
)
def cheatsheet(name) -> None:
    """Show a cheatsheet (or list all cheatsheets).

    Examples:
        limacharlie help cheatsheet
        limacharlie help cheatsheet --name getting-started
    """
    if name is None:
        sheets = list_cheatsheets()
        if not sheets:
            click.echo("No cheatsheets available yet.")
            return
        click.echo("Available cheatsheets:")
        for s in sheets:
            click.echo(f"  {s}")
        click.echo("\nUse 'limacharlie help cheatsheet --name <name>' to view one.")
        return

    content = get_cheatsheet(name)
    if content is None:
        sheets = list_cheatsheets()
        click.echo(f"Unknown cheatsheet: {name}", err=True)
        if sheets:
            click.echo(f"Available cheatsheets: {', '.join(sheets)}", err=True)
        raise SystemExit(3)

    click.echo(content)
