from __future__ import annotations

"""Main CLI entry point for LimaCharlie v2.

Uses Click for the CLI framework. Global options (--oid, --output, --debug, etc.)
are passed via Click context to all subcommands.
"""

import importlib
import os
import pkgutil
import sys
from dataclasses import dataclass, field
from typing import Callable

import click

from .client import __version__
from .ai_help import inject_ai_help
from .output import set_filter_expr, set_wide_mode


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


class _GlobalOptionsGroup(click.Group):
    """Click Group that allows group-level options to appear anywhere on the command line.

    Normally Click only parses group options that appear before the subcommand
    name.  This subclass hoists recognized group options to the front of the
    args list so that ``limacharlie org list --output json`` works the same as
    ``limacharlie --output json org list``.
    """

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
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
            # Non-option token — potential subcommand name.
            sub = cmd.commands.get(arg)
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


@click.group(cls=_GlobalOptionsGroup, context_settings={"help_option_names": ["-h", "--help"]})
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
    set_wide_mode(wide)
    set_filter_expr(filter_expr)


def _auto_discover_commands() -> None:
    """Auto-discover and register command modules from limacharlie/commands/."""
    commands_package = "limacharlie.commands"
    try:
        commands_mod = importlib.import_module(commands_package)
    except ImportError:
        return

    package_path = getattr(commands_mod, "__path__", None)
    if package_path is None:
        return

    for importer, modname, ispkg in pkgutil.iter_modules(package_path):
        try:
            mod = importlib.import_module(f"{commands_package}.{modname}")
            # Each command module should have a 'group' or 'commands' attribute
            # that is a Click group or list of Click commands
            for attr_name in dir(mod):
                attr = getattr(mod, attr_name)
                if isinstance(attr, click.Command) and attr_name in ("group", "cmd"):
                    cli.add_command(attr)
        except Exception as e:
            if os.environ.get("LC_DEBUG"):
                import traceback
                click.echo(f"Warning: failed to load command module '{modname}': {e}", err=True)
                traceback.print_exc()


# Auto-discover commands on import, then inject --ai-help everywhere.
_auto_discover_commands()
inject_ai_help(cli)


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
