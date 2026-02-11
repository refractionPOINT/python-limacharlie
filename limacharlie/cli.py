"""Main CLI entry point for LimaCharlie v2.

Uses Click for the CLI framework. Global options (--oid, --output, --debug, etc.)
are passed via Click context to all subcommands.
"""

import importlib
import os
import pkgutil
import sys

import click

from .client import __version__


class LimaCharlieContext:
    """Context object passed to all CLI commands via Click context."""

    def __init__(self):
        self.oid = None
        self.output_format = None
        self.debug = False
        self.quiet = False
        self.profile = None
        self.environment = None


pass_context = click.make_pass_decorator(LimaCharlieContext, ensure=True)


@click.group()
@click.option("--oid", default=None, help="Organization ID (overrides env/config).")
@click.option(
    "--output", "output_format",
    type=click.Choice(["json", "yaml", "csv", "table", "jsonl"], case_sensitive=False),
    default=None,
    help="Output format. Default: table (TTY) or json (piped).",
)
@click.option("--debug", is_flag=True, default=False, help="Enable debug output (prints request details).")
@click.option("--quiet", "-q", is_flag=True, default=False, help="Suppress non-error output.")
@click.option("--profile", default=None, help="Named credential profile to use.")
@click.option("--env", "environment", default=None, help="Named environment from config file.")
@click.version_option(version=__version__, prog_name="limacharlie")
@click.pass_context
def cli(ctx, oid, output_format, debug, quiet, profile, environment):
    """LimaCharlie CLI - Endpoint Detection & Response platform.

    Manage sensors, detection rules, hive data, and more from the command line.
    Use 'limacharlie discover' to explore available commands by use-case.
    Use 'limacharlie help <topic>' for concept guides.
    """
    lc_ctx = ctx.ensure_object(LimaCharlieContext)
    lc_ctx.oid = oid
    lc_ctx.output_format = output_format
    lc_ctx.debug = debug
    lc_ctx.quiet = quiet
    lc_ctx.profile = profile
    lc_ctx.environment = environment


def _auto_discover_commands():
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
        except Exception:
            pass  # Skip modules that fail to import


# Auto-discover commands on import
_auto_discover_commands()


def main():
    """CLI entry point."""
    try:
        cli(standalone_mode=False)
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
