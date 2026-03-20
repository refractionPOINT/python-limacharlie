from __future__ import annotations

"""Main CLI entry point for LimaCharlie v2.

Uses Click for the CLI framework with lazy command loading. Command
modules in ``limacharlie/commands/`` are only imported when actually
invoked (or when listing subcommands for help/completion). This keeps
CLI startup fast - importing this module loads only Click and the CLI
skeleton, not the full SDK or any command-specific dependencies.

Global options (--oid, --output, --debug, etc.) are passed via Click
context to all subcommands and can appear anywhere on the command line.
"""

import importlib
import os
import sys
from dataclasses import dataclass
from typing import Callable

import click

try:
    from ._version import version as __version__
except ImportError:
    __version__ = "0.0.0.dev0"

from .ai_help import inject_ai_help, _add_flag as _add_ai_help_flag


def _make_debug_fn(enabled: bool) -> Callable[[str], None] | None:
    """Return a stderr debug-print callback when *enabled*, else ``None``.

    This is the single source of truth for how ``--debug`` is wired into
    the SDK ``Client``.  Every command helper that creates a ``Client``
    should pass ``print_debug_fn=ctx.obj.debug_fn``.
    """
    if not enabled:
        return None
    return lambda msg: print(msg, file=sys.stderr)


@dataclass
class LimaCharlieContext:
    """Context object passed to all CLI commands via Click context."""

    oid: str | None = None
    output_format: str | None = None
    debug: bool = False
    debug_full: bool = False
    debug_curl: bool = False
    quiet: bool = False
    wide: bool = False
    no_warnings: bool = False
    filter_expr: str | None = None
    profile: str | None = None
    environment: str | None = None

    @property
    def debug_fn(self) -> Callable[[str], None] | None:
        """Return a stderr debug-print callback when any debug flag is active."""
        return _make_debug_fn(self.debug or self.debug_full or self.debug_curl)

    @property
    def debug_verbose(self) -> bool:
        """True when verbose request/response logging is wanted.

        False when only --debug-curl is set (curl-only mode).
        """
        return self.debug or self.debug_full


pass_context = click.pass_context


def _config_no_warnings() -> bool:
    """Check if warnings are suppressed via config file.

    Reads ``no_warnings: true`` from ``~/.limacharlie`` (or the config
    file pointed to by ``LC_CREDS_FILE``). Useful for CI/CD pipelines
    that want to suppress advisory warnings globally.
    """
    try:
        from .config import get_config_value
        val = get_config_value("no_warnings", default=None)
        return str(val).lower() in ("true", "1", "yes")
    except Exception:
        return False


# Static mapping: Click command name -> (module_name, attribute_name).
# This allows resolving any command to its module without importing it,
# enabling truly lazy per-command loading. Generated from the current
# command modules; must be updated when adding/renaming commands.
# The regression test TestModuleMapping verifies this stays in sync.
_COMMAND_MODULE_MAP: dict[str, tuple[str, str]] = {
    "ai": ("ai", "group"),
    "api": ("api_cmd", "cmd"),
    "api-key": ("api_key", "group"),
    "arl": ("arl", "group"),
    "artifact": ("artifact", "group"),
    "audit": ("audit", "group"),
    "auth": ("auth", "group"),
    "billing": ("billing", "group"),
    "case": ("case_cmd", "group"),
    "cloud-adapter": ("cloud_sensor", "group"),
    "completion": ("completion", "cmd"),
    "detection": ("detection", "group"),
    "download": ("download", "group"),
    "dr": ("dr", "group"),
    "endpoint-policy": ("endpoint_policy", "group"),
    "event": ("event", "group"),
    "exfil": ("exfil", "group"),
    "extension": ("extension", "group"),
    "external-adapter": ("adapter", "group"),
    "fp": ("fp", "group"),
    "group": ("group", "group"),
    "help": ("help_cmd", "group"),
    "hive": ("hive", "group"),
    "ingestion-key": ("ingestion_key", "group"),
    "installation-key": ("installation_key", "group"),
    "integrity": ("integrity", "group"),
    "ioc": ("ioc", "group"),
    "job": ("job", "group"),
    "logging": ("logging_cmd", "group"),
    "lookup": ("lookup", "group"),
    "note": ("note", "group"),
    "org": ("org", "group"),
    "output": ("output_cmd", "group"),
    "payload": ("payload", "group"),
    "playbook": ("playbook", "group"),
    "replay": ("replay_cmd", "group"),
    "schema": ("schema", "group"),
    "search": ("search", "group"),
    "secret": ("secret", "group"),
    "sensor": ("sensor", "group"),
    "sop": ("sop", "group"),
    "spotcheck": ("spotcheck", "group"),
    "stream": ("stream", "group"),
    "sync": ("sync", "group"),
    "tag": ("tag", "group"),
    "task": ("task", "group"),
    "user": ("user", "group"),
    "usp": ("usp", "group"),
    "yara": ("yara", "group"),
}


class _LazyCommandGroup(click.Group):
    """Click Group with lazy command loading and global option hoisting.

    Combines two responsibilities:

    1. **Lazy loading**: Command modules in ``limacharlie/commands/`` are
       resolved via a static name map and only imported when a specific
       command is invoked or its help is requested. This cuts CLI startup
       from ~700ms to ~100ms for single-command invocations.

    2. **Global option hoisting**: Group-level options (--oid, --output, etc.)
       can appear anywhere on the command line, not just before the subcommand.
       ``limacharlie org list --output json`` works the same as
       ``limacharlie --output json org list``.

    The ``--ai-help`` flag is injected per-command on first access rather
    than eagerly across the entire command tree.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Track which commands have had --ai-help injected
        self._ai_help_injected: set[str] = set()

    def _import_command(self, cmd_name: str) -> click.BaseCommand | None:
        """Import a single command module and register its command.

        Uses the static _COMMAND_MODULE_MAP to find the right module
        without scanning or importing other modules.
        """
        entry = _COMMAND_MODULE_MAP.get(cmd_name)
        if entry is None:
            return None

        modname, attr_name = entry
        module_path = f"limacharlie.commands.{modname}"

        try:
            mod = importlib.import_module(module_path)
            attr = getattr(mod, attr_name, None)
            if isinstance(attr, click.BaseCommand):
                self.add_command(attr)
                self._inject_ai_help(attr.name, attr)
                return attr
        except Exception as e:
            click.echo(
                f"Warning: failed to load command module '{modname}': {e}",
                err=True,
            )
            if os.environ.get("LC_DEBUG"):
                import traceback
                traceback.print_exc()
        return None

    def _inject_ai_help(self, cmd_name: str, cmd: click.BaseCommand) -> None:
        """Inject --ai-help into a command and its descendants on first access."""
        if cmd_name in self._ai_help_injected:
            return
        self._ai_help_injected.add(cmd_name)
        inject_ai_help(cmd)

    # -- Click Group overrides ------------------------------------------------

    def list_commands(self, ctx: click.Context) -> list[str]:
        """Return all command names.

        Returns the known command names from the static map merged with
        any eagerly-added commands, without importing any modules.
        """
        eager = set(self.commands.keys())
        lazy = set(_COMMAND_MODULE_MAP.keys())
        return sorted(eager | lazy)

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.BaseCommand | None:
        """Resolve a command by name, importing its module on first access."""
        # Already loaded?
        if cmd_name in self.commands:
            cmd = self.commands[cmd_name]
            self._inject_ai_help(cmd_name, cmd)
            return cmd

        # Lazy import
        return self._import_command(cmd_name)

    # -- Global option hoisting -----------------------------------------------

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        """Parse args with global option hoisting.

        Hoists recognized group options to the front of the args list so
        that ``limacharlie org list --output json`` works the same as
        ``limacharlie --output json org list``.
        """
        # Build a map of option strings defined on this group.
        opt_takes_value: dict[str, bool] = {}
        for param in self.params:
            if not isinstance(param, click.Option) or param.is_eager:
                # Skip non-options and eager options (--help, --version) which
                # should remain position-sensitive.
                continue
            takes_value = not getattr(param, "is_flag", False)
            for name in param.opts + param.secondary_opts:
                opt_takes_value[name] = takes_value

        # Don't hoist options that the target subcommand also defines,
        # otherwise e.g. `auth login --oid X` would lose its --oid to the
        # global --oid.
        shadowed = self._find_shadowed_opts(args, opt_takes_value)
        hoistable = {k: v for k, v in opt_takes_value.items() if k not in shadowed}

        global_args: list[str] = []
        remaining: list[str] = []
        i = 0
        while i < len(args):
            arg = args[i]

            # "--" signals end of options; pass everything after it through.
            if arg == "--":
                remaining.extend(args[i:])
                break

            # Handle --option=value form.
            if "=" in arg:
                opt_name = arg.split("=", 1)[0]
                if opt_name in hoistable:
                    global_args.append(arg)
                    i += 1
                    continue

            if arg in hoistable:
                global_args.append(arg)
                if hoistable[arg]:  # consumes the next token as value
                    i += 1
                    if i < len(args):
                        global_args.append(args[i])
            else:
                remaining.append(arg)
            i += 1

        return super().parse_args(ctx, global_args + remaining)

    def _find_shadowed_opts(
        self,
        args: list[str],
        global_opts: dict[str, bool],
    ) -> set[str]:
        """Walk the subcommand tree to find option names that the target
        command also defines, which must not be hoisted."""
        shadowed: set[str] = set()
        cmd: click.BaseCommand = self
        i = 0
        while i < len(args) and isinstance(cmd, click.Group):
            arg = args[i]
            if arg == "--":
                break
            if arg.startswith("-"):
                # Skip over options (and their values).
                clean = arg.split("=", 1)[0] if "=" in arg else arg
                if clean in global_opts and global_opts[clean] and "=" not in arg:
                    i += 2
                else:
                    i += 1
                continue
            # Non-option token - potential subcommand name.
            # Use get_command() to trigger lazy loading for just this command.
            ctx = click.Context(self)
            sub = self.get_command(ctx, arg) if cmd is self else cmd.commands.get(arg)
            if sub is not None:
                cmd = sub
                for p in cmd.params:
                    if isinstance(p, click.Option):
                        for name in p.opts + p.secondary_opts:
                            if name in global_opts:
                                shadowed.add(name)
                i += 1
            else:
                break
        return shadowed


@click.group(cls=_LazyCommandGroup, context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--oid", default=None, help="Organization ID (overrides env/config).")
@click.option(
    "--output", "output_format",
    type=click.Choice(["json", "yaml", "csv", "table", "jsonl"], case_sensitive=False),
    default=None,
    help="Output format. Default: table (TTY) or json (piped).",
)
@click.option("--debug", is_flag=True, default=False, help="Enable debug output (prints request/response details to stderr).")
@click.option("--debug-full", is_flag=True, default=False, help="Like --debug but does not truncate response bodies.")
@click.option("--debug-curl", is_flag=True, default=False, help="Print curl commands for each request (safe to share, secrets use $LC_TOKEN).")
@click.option("--quiet", "-q", is_flag=True, default=False, help="Suppress non-error output.")
@click.option("--wide", "-W", is_flag=True, default=False, help="Disable table value truncation (show full values).")
@click.option("--no-warnings", is_flag=True, default=False, help="Suppress advisory warnings (cost notices, memory hints, checkpoint suggestions).")
@click.option("--filter", "filter_expr", default=None, help="JMESPath expression to filter/transform output (e.g. 'user_perms', 'keys(@)').")
@click.option("--profile", default=None, help="Named credential profile to use.")
@click.option("--env", "environment", default=None, help="Named environment from config file.")
@click.version_option(version=__version__, prog_name="limacharlie")
@click.pass_context
def cli(ctx: click.Context, oid: str | None, output_format: str | None, debug: bool, debug_full: bool, debug_curl: bool, quiet: bool, wide: bool, no_warnings: bool, filter_expr: str | None, profile: str | None, environment: str | None) -> None:
    """LimaCharlie CLI - Endpoint Detection & Response platform.

    Manage sensors, detection rules, hive data, and more from the command line.
    Use --ai-help on any command for AI-oriented contextual help.
    Use 'limacharlie discover' to explore available commands by use-case.
    Use 'limacharlie help <topic>' for concept guides.
    """
    lc_ctx = ctx.ensure_object(LimaCharlieContext)
    lc_ctx.oid = oid
    lc_ctx.output_format = output_format
    lc_ctx.debug = debug
    lc_ctx.debug_full = debug_full
    lc_ctx.debug_curl = debug_curl
    lc_ctx.quiet = quiet
    lc_ctx.wide = wide
    lc_ctx.no_warnings = no_warnings or _config_no_warnings()
    lc_ctx.filter_expr = filter_expr
    lc_ctx.profile = profile
    lc_ctx.environment = environment
    # Lazy import: output pulls in jmespath, tabulate, yaml, csv (~14ms).
    # Deferring to here avoids that cost for fast paths like --help, --version,
    # and --ai-help that never render command output.
    from .output import set_filter_expr, set_wide_mode
    set_wide_mode(wide)
    set_filter_expr(filter_expr)


# Inject --ai-help on the root cli group itself (subcommands get it lazily
# via _LazyCommandGroup._inject_ai_help when first accessed).
_add_ai_help_flag(cli)


def main() -> None:
    """CLI entry point."""
    try:
        rv = cli(standalone_mode=False)
        # With standalone_mode=False, ctx.exit(code) returns the exit
        # code as the return value instead of raising SystemExit.
        if isinstance(rv, int) and rv != 0:
            sys.exit(rv)
    except click.exceptions.Abort:
        sys.exit(1)
    except click.exceptions.Exit as e:
        sys.exit(e.exit_code)
    except Exception as e:
        # Check if it's a LimaCharlie error with an exit code
        from .errors import LimaCharlieError
        if isinstance(e, LimaCharlieError):
            click.echo(f"Error: {e}", err=True)
            sys.exit(e.exit_code)
        click.echo(f"Error: {e}", err=True)
        if os.environ.get("LC_DEBUG") or "--debug" in sys.argv:
            import traceback
            traceback.print_exc()
        sys.exit(1)
