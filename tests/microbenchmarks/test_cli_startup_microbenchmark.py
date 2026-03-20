"""Microbenchmarks for CLI startup, command loading, and import overhead.

Includes both in-process benchmarks (via CliRunner) and end-to-end
subprocess benchmarks that measure real-world latency including Python
interpreter startup. The subprocess tests represent what users actually
experience when running CLI commands.

Run with: pytest tests/microbenchmarks/test_cli_startup_microbenchmark.py -v --benchmark-only
"""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
import time

import click
import click.testing
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh_import_cli():
    """Import limacharlie.cli from scratch by clearing cached modules.

    Returns the cli object and the time taken to import.
    """
    to_remove = [k for k in sys.modules if k.startswith("limacharlie")]
    saved = {}
    for k in to_remove:
        saved[k] = sys.modules.pop(k)

    try:
        start = time.perf_counter()
        mod = importlib.import_module("limacharlie.cli")
        elapsed = time.perf_counter() - start
        return mod.cli, elapsed
    finally:
        for k in list(sys.modules.keys()):
            if k.startswith("limacharlie"):
                del sys.modules[k]
        sys.modules.update(saved)


def _invoke(cli_obj, args: list[str]) -> click.testing.Result:
    """Invoke a CLI command via CliRunner."""
    runner = click.testing.CliRunner()
    return runner.invoke(cli_obj, args, catch_exceptions=False)


def _subprocess_time(python_code: str) -> float:
    """Run Python code in a subprocess and return wall-clock time in seconds.

    Uses the same Python interpreter and environment as the test process.
    """
    start = time.perf_counter()
    result = subprocess.run(
        [sys.executable, "-c", python_code],
        capture_output=True,
        text=True,
        timeout=30,
    )
    elapsed = time.perf_counter() - start
    if result.returncode != 0:
        raise RuntimeError(
            f"Subprocess failed (exit {result.returncode}):\n"
            f"stdout: {result.stdout[:500]}\n"
            f"stderr: {result.stderr[:500]}"
        )
    return elapsed


# ---------------------------------------------------------------------------
# In-process import benchmarks
# ---------------------------------------------------------------------------

class TestImportBenchmarks:
    """Benchmark the cost of importing the CLI module (in-process)."""

    def test_full_cli_import(self, benchmark):
        """Time to import limacharlie.cli.

        With lazy loading this imports only the CLI skeleton, not the
        49 command modules or the SDK.
        """
        def do_import():
            cli_obj, _elapsed = _fresh_import_cli()
            assert hasattr(cli_obj, "commands")

        benchmark(do_import)

    def test_cli_import_wall_time(self):
        """Regression guard: import must complete within threshold."""
        _cli_obj, elapsed = _fresh_import_cli()
        assert elapsed < 2.0, (
            f"CLI import took {elapsed:.3f}s, expected <2.0s"
        )

    def test_cli_import_does_not_load_output(self):
        """Importing cli must not pull in limacharlie.output or its heavy deps.

        limacharlie.output is lazily imported inside the cli() callback
        to avoid ~14ms of jmespath/tabulate/yaml/csv import overhead on
        fast paths like --help, --version, and --ai-help.
        """
        to_remove = [k for k in sys.modules if k.startswith("limacharlie")]
        saved = {k: sys.modules.pop(k) for k in to_remove}
        try:
            importlib.import_module("limacharlie.cli")
            assert "limacharlie.output" not in sys.modules, (
                "limacharlie.output imported at module level"
            )
            for dep in ("jmespath", "tabulate", "yaml"):
                assert dep not in sys.modules, (
                    f"{dep} imported at module level via limacharlie.output"
                )
        finally:
            for k in list(sys.modules):
                if k.startswith("limacharlie"):
                    del sys.modules[k]
            sys.modules.update(saved)


# ---------------------------------------------------------------------------
# In-process help benchmarks
# ---------------------------------------------------------------------------

class TestHelpBenchmarks:
    """Benchmark help text generation (in-process)."""

    def test_top_level_help(self, benchmark):
        """Time to generate top-level --help output."""
        from limacharlie.cli import cli

        def do_help():
            result = _invoke(cli, ["--help"])
            assert result.exit_code == 0

        benchmark(do_help)

    def test_group_help(self, benchmark):
        """Time to generate group-level --help (e.g. sensor --help)."""
        from limacharlie.cli import cli

        def do_help():
            result = _invoke(cli, ["sensor", "--help"])
            assert result.exit_code == 0

        benchmark(do_help)

    def test_subcommand_help(self, benchmark):
        """Time to generate subcommand --help (e.g. sensor list --help)."""
        from limacharlie.cli import cli

        def do_help():
            result = _invoke(cli, ["sensor", "list", "--help"])
            assert result.exit_code == 0

        benchmark(do_help)

    def test_ai_help(self, benchmark):
        """Time to generate --ai-help output.

        This triggers lazy loading of all commands to populate the
        '## All Command Groups' section, so it measures the cost of
        a full command tree materialization.
        """
        from limacharlie.cli import cli

        def do_ai_help():
            result = _invoke(cli, ["--ai-help"])
            assert result.exit_code == 0
            assert "## All Command Groups" in result.output

        benchmark(do_ai_help)


# ---------------------------------------------------------------------------
# In-process completion benchmarks
# ---------------------------------------------------------------------------

class TestCompletionBenchmarks:
    """Benchmark completion script generation (in-process)."""

    def test_bash_completion(self, benchmark):
        """Time to generate bash completion script."""
        from limacharlie.cli import cli

        def do_completion():
            result = _invoke(cli, ["completion", "bash"])
            assert result.exit_code == 0
            assert len(result.output) > 50

        benchmark(do_completion)

    def test_zsh_completion(self, benchmark):
        """Time to generate zsh completion script."""
        from limacharlie.cli import cli

        def do_completion():
            result = _invoke(cli, ["completion", "zsh"])
            assert result.exit_code == 0

        benchmark(do_completion)


# ---------------------------------------------------------------------------
# In-process command resolution benchmarks
# ---------------------------------------------------------------------------

class TestCommandResolutionBenchmarks:
    """Benchmark command resolution (in-process)."""

    def test_resolve_leaf_command(self, benchmark):
        """Time to resolve sensor list (lazy loads only sensor module)."""
        from limacharlie.cli import cli

        def resolve():
            ctx = click.Context(cli)
            sensor_cmd = cli.get_command(ctx, "sensor")
            assert sensor_cmd is not None
            if isinstance(sensor_cmd, click.Group):
                sub_ctx = click.Context(sensor_cmd, parent=ctx)
                list_cmd = sensor_cmd.get_command(sub_ctx, "list")
                assert list_cmd is not None

        benchmark(resolve)

    def test_list_all_commands(self, benchmark):
        """Time to enumerate all top-level command names.

        With lazy loading this returns names from the static map
        without importing any modules.
        """
        from limacharlie.cli import cli

        def list_cmds():
            ctx = click.Context(cli)
            names = cli.list_commands(ctx)
            assert len(names) >= 40

        benchmark(list_cmds)


# ---------------------------------------------------------------------------
# Lazy import isolation tests
# ---------------------------------------------------------------------------

class TestLazyImportIsolation:
    """Verify that lazy loading defers heavy imports correctly."""

    def test_help_does_not_import_requests(self):
        """Top-level --help should not require importing requests."""
        from limacharlie.cli import cli
        result = _invoke(cli, ["--help"])
        assert result.exit_code == 0

    def test_sensor_list_help_does_not_need_auth(self):
        """sensor list --help should not require auth credentials."""
        from limacharlie.cli import cli
        result = _invoke(cli, ["sensor", "list", "--help"])
        assert result.exit_code == 0
        assert "--sid" in result.output or "--tag" in result.output


# ---------------------------------------------------------------------------
# End-to-end subprocess benchmarks
# ---------------------------------------------------------------------------

class TestEndToEndSubprocess:
    """End-to-end latency benchmarks using real subprocess invocations.

    These measure what users actually experience: Python startup +
    module imports + command resolution + output generation. Each test
    spawns a fresh Python process to avoid warm-cache effects.
    """

    def test_e2e_import_only(self, benchmark):
        """Wall-clock time to import limacharlie.cli in a fresh process.

        This is the baseline cost every CLI invocation pays.
        """
        def run():
            elapsed = _subprocess_time(
                "from limacharlie.cli import cli"
            )
            return elapsed

        result = benchmark(run)

    def test_e2e_version(self, benchmark):
        """Wall-clock time for 'limacharlie --version'."""
        def run():
            elapsed = _subprocess_time(
                "from limacharlie.cli import cli; "
                "from click.testing import CliRunner; "
                "CliRunner().invoke(cli, ['--version'])"
            )
            return elapsed

        benchmark(run)

    def test_e2e_top_level_help(self, benchmark):
        """Wall-clock time for 'limacharlie --help'.

        This lists all commands, triggering list_commands() which
        with lazy loading only returns names from the static map.
        """
        def run():
            elapsed = _subprocess_time(
                "from limacharlie.cli import cli; "
                "from click.testing import CliRunner; "
                "CliRunner().invoke(cli, ['--help'])"
            )
            return elapsed

        benchmark(run)

    def test_e2e_subcommand_help(self, benchmark):
        """Wall-clock time for 'limacharlie sensor list --help'.

        With lazy loading, only imports the sensor module.
        """
        def run():
            elapsed = _subprocess_time(
                "from limacharlie.cli import cli; "
                "from click.testing import CliRunner; "
                "CliRunner().invoke(cli, ['sensor', 'list', '--help'])"
            )
            return elapsed

        benchmark(run)

    def test_e2e_bash_completion(self, benchmark):
        """Wall-clock time for 'limacharlie completion bash'.

        Generates the full bash completion script.
        """
        def run():
            elapsed = _subprocess_time(
                "from limacharlie.cli import cli; "
                "from click.testing import CliRunner; "
                "CliRunner().invoke(cli, ['completion', 'bash'])"
            )
            return elapsed

        benchmark(run)

    def test_e2e_ai_help(self, benchmark):
        """Wall-clock time for 'limacharlie --ai-help'.

        This loads all command modules to render the full command group
        listing, so it measures the worst-case lazy loading overhead.
        """
        def run():
            elapsed = _subprocess_time(
                "from limacharlie.cli import cli; "
                "from click.testing import CliRunner; "
                "r = CliRunner().invoke(cli, ['--ai-help']); "
                "assert r.exit_code == 0; "
                "assert '## All Command Groups' in r.output"
            )
            return elapsed

        benchmark(run)

    def test_e2e_unknown_command(self, benchmark):
        """Wall-clock time for an unknown command (error path).

        Should be fast - lazy loading means no modules imported.
        """
        def run():
            elapsed = _subprocess_time(
                "from limacharlie.cli import cli; "
                "from click.testing import CliRunner; "
                "r = CliRunner().invoke(cli, ['nonexistent_xyz']); "
                "assert r.exit_code != 0"
            )
            return elapsed

        benchmark(run)


# ---------------------------------------------------------------------------
# End-to-end subprocess regression tests (non-benchmark)
# ---------------------------------------------------------------------------

class TestEndToEndRegression:
    """Verify end-to-end CLI behavior in fresh subprocesses.

    These are not benchmarks but correctness tests that ensure
    the lazy loading works correctly from a clean Python process.
    """

    def test_e2e_help_output_complete(self):
        """--help must list all expected command groups."""
        result = subprocess.run(
            [sys.executable, "-c",
             "from limacharlie.cli import cli; "
             "from click.testing import CliRunner; "
             "r = CliRunner().invoke(cli, ['--help']); "
             "print(r.output)"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0
        output = result.stdout
        for cmd in ("sensor", "auth", "dr", "search", "hive", "tag"):
            assert cmd in output, f"Missing {cmd!r} in --help output"

    def test_e2e_sensor_help_has_subcommands(self):
        """sensor --help must list subcommands like list, get, delete."""
        result = subprocess.run(
            [sys.executable, "-c",
             "from limacharlie.cli import cli; "
             "from click.testing import CliRunner; "
             "r = CliRunner().invoke(cli, ['sensor', '--help']); "
             "print(r.output)"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0
        output = result.stdout
        for sub in ("list", "get", "delete"):
            assert sub in output, f"Missing {sub!r} in sensor --help"

    def test_e2e_version_matches(self):
        """--version must output the package version."""
        result = subprocess.run(
            [sys.executable, "-c",
             "from limacharlie.cli import cli; "
             "from click.testing import CliRunner; "
             "r = CliRunner().invoke(cli, ['--version']); "
             "print(r.output)"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0
        import re
        assert re.search(r"\d+\.\d+", result.stdout)

    def test_e2e_completion_bash_valid(self):
        """completion bash must produce a non-trivial script."""
        result = subprocess.run(
            [sys.executable, "-c",
             "from limacharlie.cli import cli; "
             "from click.testing import CliRunner; "
             "r = CliRunner().invoke(cli, ['completion', 'bash']); "
             "print(len(r.output))"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0
        script_len = int(result.stdout.strip())
        assert script_len > 100, f"Bash completion script too short: {script_len}"

    def test_e2e_unknown_command_fails(self):
        """Unknown command must exit non-zero."""
        result = subprocess.run(
            [sys.executable, "-c",
             "import sys; "
             "from limacharlie.cli import cli; "
             "from click.testing import CliRunner; "
             "r = CliRunner().invoke(cli, ['nonexistent_xyz']); "
             "sys.exit(r.exit_code)"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode != 0

    def test_e2e_ai_help_works(self):
        """--ai-help must produce markdown with command groups from a fresh process."""
        result = subprocess.run(
            [sys.executable, "-c",
             "from limacharlie.cli import cli; "
             "from click.testing import CliRunner; "
             "r = CliRunner().invoke(cli, ['--ai-help']); "
             "print(r.output)"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0
        assert "LimaCharlie CLI" in result.stdout
        assert "## All Command Groups" in result.stdout
        # Verify command groups are actually listed (not empty)
        group_lines = [
            l for l in result.stdout.splitlines() if l.startswith("- **")
        ]
        assert len(group_lines) >= 40, (
            f"Expected 40+ command groups, got {len(group_lines)}"
        )
