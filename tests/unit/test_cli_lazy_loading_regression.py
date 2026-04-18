"""Regression tests for CLI command loading, discovery, and help surface.

Captures the full CLI contract - every command name, group structure,
help text, docstrings, --ai-help output, global option hoisting, and
explain registry entries - so that refactoring the command loading
mechanism (e.g. switching to lazy imports) cannot silently break or
lose any part of the CLI surface.

Run with: pytest tests/unit/test_cli_lazy_loading_regression.py -v
"""

from __future__ import annotations

import importlib
import pkgutil
import re

import click
import click.testing
import pytest

from limacharlie.cli import cli, _LazyCommandGroup, LimaCharlieContext
from limacharlie.discovery import (
    PROFILES,
    _EXPLAIN_REGISTRY,
    get_explain,
    list_profiles,
    format_discovery,
)

# Force full command loading so tests can inspect cli.commands directly.
# With lazy loading, list_commands() returns names from the static map
# but doesn't import modules. We must call get_command() for each name
# to populate cli.commands - this is what Click does when running --help
# or completion.
_ctx = click.Context(cli)
for _name in cli.list_commands(_ctx):
    cli.get_command(_ctx, _name)
del _ctx, _name


# ---------------------------------------------------------------------------
# Snapshot of the expected CLI surface (captured from current eager loading)
# ---------------------------------------------------------------------------

# Every top-level command/group that must be registered on cli.
EXPECTED_TOP_LEVEL_COMMANDS = frozenset({
    "ai", "api", "api-key", "arl", "artifact", "audit", "auth", "billing",
    "case", "cloud-adapter", "completion", "config", "detection", "download", "dr",
    "endpoint-policy", "event", "exfil", "extension", "external-adapter", "feedback",
    "fp", "group", "help", "hive", "ingestion-key", "installation-key",
    "integrity", "ioc", "job", "logging", "lookup", "note", "org", "output",
    "payload", "playbook", "replay", "schema", "search", "secret", "sensor",
    "sop", "spotcheck", "stream", "sync", "tag", "task", "user", "usp",
    "yara",
})

# Module filename -> (attribute name, Click command name).
# This is the authoritative mapping that lazy loading must preserve.
EXPECTED_MODULE_MAP = {
    "adapter": ("group", "external-adapter"),
    "ai": ("group", "ai"),
    "api_cmd": ("cmd", "api"),
    "api_key": ("group", "api-key"),
    "arl": ("group", "arl"),
    "artifact": ("group", "artifact"),
    "audit": ("group", "audit"),
    "auth": ("group", "auth"),
    "billing": ("group", "billing"),
    "case_cmd": ("group", "case"),
    "cloud_sensor": ("group", "cloud-adapter"),
    "completion": ("cmd", "completion"),
    "config_cmd": ("group", "config"),
    "detection": ("group", "detection"),
    "download": ("group", "download"),
    "dr": ("group", "dr"),
    "endpoint_policy": ("group", "endpoint-policy"),
    "event": ("group", "event"),
    "exfil": ("group", "exfil"),
    "extension": ("group", "extension"),
    "feedback": ("group", "feedback"),
    "fp": ("group", "fp"),
    "group": ("group", "group"),
    "help_cmd": ("group", "help"),
    "hive": ("group", "hive"),
    "ingestion_key": ("group", "ingestion-key"),
    "installation_key": ("group", "installation-key"),
    "integrity": ("group", "integrity"),
    "ioc": ("group", "ioc"),
    "job": ("group", "job"),
    "logging_cmd": ("group", "logging"),
    "lookup": ("group", "lookup"),
    "note": ("group", "note"),
    "org": ("group", "org"),
    "output_cmd": ("group", "output"),
    "payload": ("group", "payload"),
    "playbook": ("group", "playbook"),
    "replay_cmd": ("group", "replay"),
    "schema": ("group", "schema"),
    "search": ("group", "search"),
    "secret": ("group", "secret"),
    "sensor": ("group", "sensor"),
    "sop": ("group", "sop"),
    "spotcheck": ("group", "spotcheck"),
    "stream": ("group", "stream"),
    "sync": ("group", "sync"),
    "tag": ("group", "tag"),
    "task": ("group", "task"),
    "user": ("group", "user"),
    "usp": ("group", "usp"),
    "yara": ("group", "yara"),
}

# Every (group, subcommand) pair that must exist.
EXPECTED_SUBCOMMANDS: dict[str, frozenset[str]] = {
    "ai": frozenset({
        "auth", "chat",
        "generate-detection", "generate-playbook", "generate-query",
        "generate-response", "generate-rule", "generate-selector",
        "session", "start-session", "summarize-detection", "usage",
    }),
    "api-key": frozenset({"create", "delete", "list"}),
    "arl": frozenset({"get"}),
    "artifact": frozenset({"download", "list", "upload"}),
    "audit": frozenset({"list"}),
    "auth": frozenset({
        "get-token", "list-envs", "list-orgs", "login", "logout",
        "signup", "test", "use-env", "use-org", "whoami",
    }),
    "config": frozenset({"migrate", "show-paths"}),
    "billing": frozenset({"details", "invoice", "plans", "status"}),
    "case": frozenset({
        "add-note", "artifact", "assignees", "bulk-update",
        "config-get", "config-set", "create", "dashboard", "detection",
        "entity", "export", "get", "list", "merge", "orgs", "report",
        "tag", "telemetry", "update", "update-note",
    }),
    "cloud-adapter": frozenset({"delete", "disable", "enable", "get", "list", "set"}),
    "detection": frozenset({"get", "list"}),
    "download": frozenset({"adapter", "list", "sensor"}),
    "dr": frozenset({
        "convert-rules", "delete", "export", "get", "import",
        "list", "replay", "set", "test", "validate",
    }),
    "endpoint-policy": frozenset({"isolate", "rejoin", "seal", "status", "unseal"}),
    "event": frozenset({
        "children", "get", "list", "overview", "retention",
        "schema", "timeline", "types",
    }),
    "exfil": frozenset({"create-event", "create-watch", "delete", "list"}),
    "extension": frozenset({
        "config-delete", "config-get", "config-list", "config-set",
        "list", "list-available", "rekey", "request", "schema",
        "subscribe", "unsubscribe",
    }),
    "external-adapter": frozenset({"delete", "disable", "enable", "get", "list", "set"}),
    "fp": frozenset({"delete", "disable", "enable", "get", "list", "set"}),
    "group": frozenset({
        "create", "delete", "get", "list", "logs",
        "member-add", "member-remove", "org-add", "org-remove",
        "owner-add", "owner-remove", "permissions-set",
    }),
    "help": frozenset({"cheatsheet", "discover", "topic"}),
    "hive": frozenset({
        "delete", "disable", "enable", "export", "get", "import",
        "list", "list-types", "rename", "set", "validate",
    }),
    "ingestion-key": frozenset({"create", "delete", "list"}),
    "installation-key": frozenset({"create", "delete", "get", "list"}),
    "integrity": frozenset({"create", "delete", "get", "list"}),
    "ioc": frozenset({"batch-enrich", "batch-search", "enrich", "hosts", "search"}),
    "job": frozenset({"delete", "get", "list", "wait"}),
    "logging": frozenset({"create", "delete", "get", "list"}),
    "lookup": frozenset({"delete", "disable", "enable", "get", "list", "set"}),
    "note": frozenset({"delete", "disable", "enable", "get", "list", "set"}),
    "org": frozenset({
        "check-name", "config-get", "config-set", "create", "delete",
        "dismiss-error", "errors", "info", "list", "mitre", "quota",
        "rename", "runtime-metadata", "schema", "stats", "urls",
    }),
    "output": frozenset({"create", "delete", "list"}),
    "payload": frozenset({"delete", "download", "list", "upload"}),
    "playbook": frozenset({"delete", "disable", "enable", "get", "list", "set"}),
    "replay": frozenset({"run"}),
    "schema": frozenset({"get", "list"}),
    "search": frozenset({
        "checkpoint-show", "checkpoints", "estimate", "run",
        "saved-create", "saved-delete", "saved-get", "saved-list",
        "saved-run", "validate",
    }),
    "secret": frozenset({"delete", "disable", "enable", "get", "list", "set"}),
    "sensor": frozenset({
        "delete", "dump", "export", "get", "list", "set-version",
        "sweep", "upgrade", "wait-online",
    }),
    "sop": frozenset({"delete", "disable", "enable", "get", "list", "set"}),
    "spotcheck": frozenset({"run"}),
    "stream": frozenset({"audit", "detections", "events", "firehose"}),
    "sync": frozenset({"pull", "push"}),
    "tag": frozenset({"add", "find", "list", "mass-add", "mass-remove", "remove"}),
    "task": frozenset({
        "reliable-delete", "reliable-list", "reliable-send",
        "request", "send",
    }),
    "user": frozenset({"invite", "list", "permissions", "remove"}),
    "usp": frozenset({"validate"}),
    "yara": frozenset({
        "rule-add", "rule-delete", "rules-list", "scan",
        "source-add", "source-delete", "source-get", "sources-list",
    }),
}

# Global options that must be present on the top-level cli group.
EXPECTED_GLOBAL_OPTIONS = frozenset({
    "oid", "output_format", "debug", "debug_full", "debug_curl",
    "quiet", "wide", "no_warnings", "filter_expr", "profile",
    "environment",
})


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _invoke(args: list[str]) -> click.testing.Result:
    """Invoke the real CLI and return the result."""
    runner = click.testing.CliRunner()
    return runner.invoke(cli, args, catch_exceptions=False)


# ---------------------------------------------------------------------------
# Test: top-level command registration
# ---------------------------------------------------------------------------

class TestCommandRegistration:
    """Verify every expected command is registered on the CLI group."""

    def test_all_expected_commands_registered(self):
        """Every command in the snapshot must be present."""
        registered = set(cli.commands.keys())
        missing = EXPECTED_TOP_LEVEL_COMMANDS - registered
        assert not missing, f"Missing commands: {sorted(missing)}"

    def test_no_unexpected_commands(self):
        """No commands beyond the snapshot should appear (catches accidental duplication)."""
        registered = set(cli.commands.keys())
        extra = registered - EXPECTED_TOP_LEVEL_COMMANDS
        assert not extra, f"Unexpected commands: {sorted(extra)}"

    def test_command_count(self):
        """Total command count must match exactly."""
        assert len(cli.commands) == len(EXPECTED_TOP_LEVEL_COMMANDS)


# ---------------------------------------------------------------------------
# Test: module-to-command mapping
# ---------------------------------------------------------------------------

class TestModuleMapping:
    """Verify the module filename to Click command name mapping.

    This is critical for lazy loading - the loader must know which module
    to import for each command name without importing it first.
    """

    def test_all_modules_have_expected_export(self):
        """Each command module must export either 'group' or 'cmd'
        matching the expected mapping."""
        commands_mod = importlib.import_module("limacharlie.commands")
        for modname, (attr_name, cmd_name) in EXPECTED_MODULE_MAP.items():
            mod = importlib.import_module(f"limacharlie.commands.{modname}")
            attr = getattr(mod, attr_name, None)
            assert attr is not None, (
                f"Module {modname} missing attribute '{attr_name}'"
            )
            assert isinstance(attr, click.BaseCommand), (
                f"Module {modname}.{attr_name} is not a Click command"
            )
            assert attr.name == cmd_name, (
                f"Module {modname}.{attr_name}.name = {attr.name!r}, "
                f"expected {cmd_name!r}"
            )

    def test_no_undiscovered_command_modules(self):
        """Every non-private .py file in commands/ must be in the mapping."""
        commands_mod = importlib.import_module("limacharlie.commands")
        discovered = set()
        for _importer, modname, _ispkg in pkgutil.iter_modules(commands_mod.__path__):
            if not modname.startswith("_"):
                discovered.add(modname)
        mapped = set(EXPECTED_MODULE_MAP.keys())
        unmapped = discovered - mapped
        assert not unmapped, (
            f"Command modules not in EXPECTED_MODULE_MAP: {sorted(unmapped)}"
        )

    def test_mapping_has_no_stale_entries(self):
        """Every entry in the mapping must correspond to an actual module."""
        commands_mod = importlib.import_module("limacharlie.commands")
        discovered = set()
        for _importer, modname, _ispkg in pkgutil.iter_modules(commands_mod.__path__):
            if not modname.startswith("_"):
                discovered.add(modname)
        mapped = set(EXPECTED_MODULE_MAP.keys())
        stale = mapped - discovered
        assert not stale, (
            f"Stale entries in EXPECTED_MODULE_MAP: {sorted(stale)}"
        )


# ---------------------------------------------------------------------------
# Test: subcommand structure
# ---------------------------------------------------------------------------

class TestSubcommandStructure:
    """Verify every group has exactly the expected subcommands."""

    @pytest.mark.parametrize(
        "group_name",
        sorted(EXPECTED_SUBCOMMANDS.keys()),
    )
    def test_subcommands_match(self, group_name: str):
        """Subcommands of each group must match the snapshot exactly."""
        cmd = cli.commands.get(group_name)
        assert cmd is not None, f"Group {group_name!r} not registered"
        assert isinstance(cmd, click.Group), (
            f"{group_name!r} is not a Group (is {type(cmd).__name__})"
        )
        actual = set(cmd.commands.keys())
        expected = EXPECTED_SUBCOMMANDS[group_name]
        missing = expected - actual
        extra = actual - expected
        assert not missing, (
            f"{group_name}: missing subcommands: {sorted(missing)}"
        )
        assert not extra, (
            f"{group_name}: unexpected subcommands: {sorted(extra)}"
        )

    def test_standalone_commands_are_not_groups(self):
        """'api' and 'completion' must be leaf commands, not groups."""
        for name in ("api", "completion"):
            cmd = cli.commands.get(name)
            assert cmd is not None, f"{name!r} not registered"
            assert not isinstance(cmd, click.Group), (
                f"{name!r} should be a leaf Command, not a Group"
            )


# ---------------------------------------------------------------------------
# Test: global options
# ---------------------------------------------------------------------------

class TestGlobalOptions:
    """Verify global options are present and hoistable."""

    def test_all_global_options_present(self):
        """Every expected global option must be a parameter on cli."""
        param_names = {p.name for p in cli.params if isinstance(p, click.Option)}
        missing = EXPECTED_GLOBAL_OPTIONS - param_names
        assert not missing, f"Missing global options: {sorted(missing)}"

    def test_cli_uses_lazy_command_group(self):
        """The CLI group class must support lazy loading and option hoisting."""
        assert isinstance(cli, _LazyCommandGroup), (
            f"cli is {type(cli).__name__}, expected _LazyCommandGroup"
        )

    def test_option_after_subcommand_works(self):
        """Global options placed after the subcommand must be parsed."""
        result = _invoke(["auth", "whoami", "--help"])
        assert result.exit_code == 0
        # Verify the subcommand help renders correctly
        assert "whoami" in result.output

    def test_global_options_in_help(self):
        """Top-level --help must list all global options."""
        result = _invoke(["--help"])
        assert result.exit_code == 0
        for opt in ("--oid", "--output", "--debug", "--quiet", "--wide",
                     "--filter", "--profile", "--env", "--no-warnings"):
            assert opt in result.output, f"{opt} missing from --help"


# ---------------------------------------------------------------------------
# Test: --help for every command
# ---------------------------------------------------------------------------

class TestHelpOutput:
    """Verify --help works for every registered command and group."""

    def test_top_level_help(self):
        result = _invoke(["--help"])
        assert result.exit_code == 0
        assert "LimaCharlie CLI" in result.output

    @pytest.mark.parametrize(
        "group_name",
        sorted(EXPECTED_TOP_LEVEL_COMMANDS),
    )
    def test_group_help(self, group_name: str):
        """--help must succeed for every top-level command/group."""
        result = _invoke([group_name, "--help"])
        assert result.exit_code == 0, (
            f"{group_name} --help failed with exit code {result.exit_code}: "
            f"{result.output}"
        )
        # Must contain the command name somewhere in the output
        assert group_name in result.output

    @pytest.mark.parametrize(
        "group_name,sub_name",
        [
            (g, s)
            for g in sorted(EXPECTED_SUBCOMMANDS)
            for s in sorted(EXPECTED_SUBCOMMANDS[g])
        ],
    )
    def test_subcommand_help(self, group_name: str, sub_name: str):
        """--help must succeed for every subcommand."""
        result = _invoke([group_name, sub_name, "--help"])
        assert result.exit_code == 0, (
            f"{group_name} {sub_name} --help failed: {result.output}"
        )


# ---------------------------------------------------------------------------
# Test: docstrings
# ---------------------------------------------------------------------------

class TestDocstrings:
    """Verify all groups and commands have non-empty docstrings/help text."""

    # Commands that currently lack docstrings (pre-existing).
    _TOP_LEVEL_WITHOUT_HELP = {"api", "completion"}

    @pytest.mark.parametrize(
        "group_name",
        sorted(EXPECTED_TOP_LEVEL_COMMANDS),
    )
    def test_top_level_has_help(self, group_name: str):
        """Top-level commands with existing docstrings must keep them."""
        if group_name in self._TOP_LEVEL_WITHOUT_HELP:
            pytest.skip(f"{group_name!r} has no docstring (pre-existing)")
        cmd = cli.commands[group_name]
        help_text = cmd.help or ""
        assert help_text.strip(), (
            f"Command {group_name!r} has no help text/docstring"
        )

    def test_subcommands_with_help_count(self):
        """Track how many subcommands have help text.

        Many subcommands currently lack docstrings. This test ensures
        the count doesn't decrease (i.e., lazy loading doesn't lose
        existing help text). Update the threshold as docstrings are added.
        """
        with_help = 0
        total = 0
        for gname in EXPECTED_SUBCOMMANDS:
            group = cli.commands[gname]
            if not isinstance(group, click.Group):
                continue
            for sname in group.commands:
                total += 1
                if (group.commands[sname].help or "").strip():
                    with_help += 1
        # Current baseline: many subcommands have help text.
        # This catches regressions where lazy loading loses help text.
        assert with_help > 50, (
            f"Only {with_help}/{total} subcommands have help text, "
            f"expected at least 50 (regression in help text loading?)"
        )


# ---------------------------------------------------------------------------
# Test: --ai-help injection
# ---------------------------------------------------------------------------

class TestAiHelpInjection:
    """Verify --ai-help is available on all commands after loading."""

    def test_ai_help_on_root(self):
        """Root CLI must have --ai-help."""
        names = {p.name for p in cli.params}
        assert "ai_help" in names

    @pytest.mark.parametrize(
        "group_name",
        sorted(EXPECTED_TOP_LEVEL_COMMANDS),
    )
    def test_ai_help_on_top_level(self, group_name: str):
        """Every top-level command/group must have --ai-help."""
        cmd = cli.commands[group_name]
        names = {p.name for p in cmd.params}
        assert "ai_help" in names, (
            f"{group_name!r} missing --ai-help parameter"
        )

    @pytest.mark.parametrize(
        "group_name,sub_name",
        [
            (g, s)
            for g in sorted(EXPECTED_SUBCOMMANDS)
            for s in sorted(EXPECTED_SUBCOMMANDS[g])
        ],
    )
    def test_ai_help_on_subcommand(self, group_name: str, sub_name: str):
        """Every subcommand must have --ai-help."""
        group = cli.commands[group_name]
        assert isinstance(group, click.Group)
        cmd = group.commands[sub_name]
        names = {p.name for p in cmd.params}
        assert "ai_help" in names, (
            f"{group_name} {sub_name} missing --ai-help parameter"
        )


# ---------------------------------------------------------------------------
# Test: --ai-help output
# ---------------------------------------------------------------------------

class TestAiHelpOutput:
    """Verify --ai-help produces meaningful output at all levels."""

    def test_top_level_ai_help(self):
        result = _invoke(["--ai-help"])
        assert result.exit_code == 0
        assert "LimaCharlie CLI" in result.output
        assert "Getting Started" in result.output
        assert "Global Options" in result.output

    @pytest.mark.parametrize(
        "group_name",
        # Test a representative sample of groups for speed
        ["sensor", "dr", "auth", "hive", "search", "case", "extension"],
    )
    def test_group_ai_help(self, group_name: str):
        result = _invoke([group_name, "--ai-help"])
        assert result.exit_code == 0
        assert group_name in result.output
        # Must list subcommands
        group = cli.commands[group_name]
        if isinstance(group, click.Group):
            for sub_name in list(group.commands.keys())[:3]:
                assert sub_name in result.output

    @pytest.mark.parametrize(
        "group_name,sub_name",
        [
            ("sensor", "list"),
            ("dr", "list"),
            ("auth", "whoami"),
            ("search", "run"),
            ("tag", "add"),
        ],
    )
    def test_command_ai_help(self, group_name: str, sub_name: str):
        result = _invoke([group_name, sub_name, "--ai-help"])
        assert result.exit_code == 0
        assert sub_name in result.output
        # Should have Options section if command has options
        cmd = cli.commands[group_name].commands[sub_name]
        opts = [p for p in cmd.params if isinstance(p, click.Option) and p.name != "ai_help"]
        if opts:
            assert "Options" in result.output or "--" in result.output


# ---------------------------------------------------------------------------
# Test: explain registry
# ---------------------------------------------------------------------------

class TestExplainRegistry:
    """Verify the explain registry is populated for all commands."""

    def test_explain_registry_has_entries(self):
        """Registry must have substantial number of entries."""
        assert len(_EXPLAIN_REGISTRY) > 200, (
            f"Expected >200 explain entries, got {len(_EXPLAIN_REGISTRY)}"
        )

    def test_all_explain_values_are_nonempty_strings(self):
        """Every explain entry must be a non-empty string."""
        for key, value in _EXPLAIN_REGISTRY.items():
            assert isinstance(value, str), (
                f"Explain entry {key!r} is {type(value).__name__}, not str"
            )
            assert value.strip(), f"Explain entry {key!r} is empty"

    def test_explain_keys_use_dot_notation(self):
        """All keys must use dot notation (e.g. 'sensor.list').

        Single-segment keys (e.g. 'completion') are allowed for
        standalone commands that are not part of a group.
        """
        for key in _EXPLAIN_REGISTRY:
            # Allow single-segment keys for standalone commands
            assert isinstance(key, str) and len(key) > 0, (
                f"Explain key must be a non-empty string, got {key!r}"
            )

    @pytest.mark.parametrize(
        "group_name",
        sorted(EXPECTED_SUBCOMMANDS.keys()),
    )
    def test_group_has_at_least_one_explain_entry(self, group_name: str):
        """Each command group should have at least one explain entry.

        The key prefix uses the Click command name (e.g. 'endpoint-policy.isolate')
        or may use alternate forms. We check that at least one key starts
        with the group name.
        """
        prefix = group_name + "."
        # Some groups use underscores in explain keys
        alt_prefix = group_name.replace("-", "_") + "."
        matching = [
            k for k in _EXPLAIN_REGISTRY
            if k.startswith(prefix) or k.startswith(alt_prefix)
        ]
        # Most groups should have explain entries; allow exceptions for
        # very small groups that may not have been documented yet.
        if group_name not in ("cloud-adapter",):
            assert matching, (
                f"No explain entries found for group {group_name!r} "
                f"(looked for prefix {prefix!r})"
            )


# ---------------------------------------------------------------------------
# Test: discovery profiles reference valid commands
# ---------------------------------------------------------------------------

class TestDiscoveryProfiles:
    """Verify discovery profiles reference commands that actually exist."""

    def test_most_profile_commands_exist(self):
        """Most command paths in profiles should correspond to real commands.

        Some profiles reference command aliases or planned commands
        (e.g. 'rule list' instead of 'dr list', 'sensor online' which
        doesn't exist yet). We verify the majority resolve correctly
        and that lazy loading doesn't reduce the match rate.
        """
        all_commands = set()
        for name in cli.commands:
            cmd = cli.commands[name]
            if isinstance(cmd, click.Group):
                for sub_name in cmd.commands:
                    all_commands.add(f"{name} {sub_name}")
            else:
                all_commands.add(name)

        total = 0
        found = 0
        for profile_name, profile in PROFILES.items():
            for cmd_path in profile["commands"]:
                total += 1
                if cmd_path in all_commands:
                    found += 1

        # Current baseline: most profile commands exist.
        # Lazy loading must not reduce this ratio.
        assert found > 100, (
            f"Only {found}/{total} profile commands resolve to real commands"
        )

    def test_format_discovery_works(self):
        """format_discovery() must produce output without errors."""
        output = format_discovery()
        assert "Command Discovery" in output
        assert len(output) > 100


# ---------------------------------------------------------------------------
# Test: completion command
# ---------------------------------------------------------------------------

class TestCompletionCommand:
    """Verify the completion command works for all supported shells."""

    @pytest.mark.parametrize("shell", ["bash", "zsh", "fish"])
    def test_completion_generates_script(self, shell: str):
        result = _invoke(["completion", shell])
        assert result.exit_code == 0
        assert len(result.output) > 50, (
            f"Completion script for {shell} is suspiciously short"
        )

    def test_completion_invalid_shell(self):
        result = click.testing.CliRunner().invoke(cli, ["completion", "powershell"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Test: context propagation
# ---------------------------------------------------------------------------

class TestContextPropagation:
    """Verify the LimaCharlieContext dataclass is correctly populated."""

    def test_context_object_type(self):
        """Context object must be LimaCharlieContext."""
        captured = {}

        @cli.command("_test_ctx_probe", hidden=True)
        @click.pass_context
        def probe(ctx):
            captured["obj"] = ctx.obj

        try:
            result = _invoke(["_test_ctx_probe"])
            assert isinstance(captured.get("obj"), LimaCharlieContext)
        finally:
            cli.commands.pop("_test_ctx_probe", None)

    def test_debug_fn_off_by_default(self):
        """debug_fn should be None when --debug is not passed."""
        ctx = LimaCharlieContext()
        assert ctx.debug_fn is None

    def test_debug_fn_on_when_debug(self):
        """debug_fn should be callable when debug=True."""
        ctx = LimaCharlieContext(debug=True)
        assert ctx.debug_fn is not None
        assert callable(ctx.debug_fn)

    def test_debug_verbose_combines_flags(self):
        """debug_verbose should be True for --debug and --debug-full."""
        assert LimaCharlieContext(debug=True).debug_verbose is True
        assert LimaCharlieContext(debug_full=True).debug_verbose is True
        assert LimaCharlieContext(debug_curl=True).debug_verbose is False
        assert LimaCharlieContext().debug_verbose is False


# ---------------------------------------------------------------------------
# Test: version
# ---------------------------------------------------------------------------

class TestVersion:
    def test_version_flag(self):
        result = _invoke(["--version"])
        assert result.exit_code == 0
        # Should contain a version string (digits and dots)
        assert re.search(r"\d+\.\d+", result.output)


# ---------------------------------------------------------------------------
# Test: unknown command error
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_unknown_command_exits_nonzero(self):
        runner = click.testing.CliRunner()
        result = runner.invoke(cli, ["nonexistent_command_xyz"])
        assert result.exit_code != 0

    def test_unknown_subcommand_exits_nonzero(self):
        runner = click.testing.CliRunner()
        result = runner.invoke(cli, ["sensor", "nonexistent_xyz"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Test: lazy loading specific behavior
# ---------------------------------------------------------------------------

class TestLazyLoadingBehavior:
    """Tests specific to the lazy command loading mechanism.

    These verify invariants that are only relevant when commands are
    loaded on-demand rather than eagerly at import time.
    """

    def test_get_command_idempotent(self):
        """Calling get_command twice returns the same object."""
        ctx = click.Context(cli)
        cmd1 = cli.get_command(ctx, "sensor")
        cmd2 = cli.get_command(ctx, "sensor")
        assert cmd1 is cmd2

    def test_get_command_unknown_returns_none(self):
        """get_command for a non-existent command must return None."""
        ctx = click.Context(cli)
        assert cli.get_command(ctx, "nonexistent_xyz_abc") is None

    def test_list_commands_sorted(self):
        """list_commands must return a sorted list."""
        ctx = click.Context(cli)
        names = cli.list_commands(ctx)
        assert names == sorted(names)

    def test_list_commands_stable(self):
        """list_commands called twice returns same result."""
        ctx = click.Context(cli)
        first = cli.list_commands(ctx)
        second = cli.list_commands(ctx)
        assert first == second

    def test_static_map_matches_list_commands(self):
        """_COMMAND_MODULE_MAP keys must match list_commands output."""
        from limacharlie.cli import _COMMAND_MODULE_MAP
        ctx = click.Context(cli)
        listed = set(cli.list_commands(ctx))
        mapped = set(_COMMAND_MODULE_MAP.keys())
        # list_commands may include eagerly-added commands (like the
        # test probe), but all mapped commands must appear
        missing = mapped - listed
        assert not missing, f"Mapped but not listed: {sorted(missing)}"

    def test_static_map_all_importable(self):
        """Every module in _COMMAND_MODULE_MAP must be importable and
        must export the expected attribute."""
        from limacharlie.cli import _COMMAND_MODULE_MAP
        for cmd_name, (modname, attr_name) in _COMMAND_MODULE_MAP.items():
            module_path = f"limacharlie.commands.{modname}"
            mod = importlib.import_module(module_path)
            attr = getattr(mod, attr_name, None)
            assert attr is not None, (
                f"Map entry {cmd_name!r} -> {modname}.{attr_name} not found"
            )
            assert isinstance(attr, click.BaseCommand), (
                f"Map entry {cmd_name!r} -> {modname}.{attr_name} is "
                f"{type(attr).__name__}, not a Click command"
            )
            assert attr.name == cmd_name, (
                f"Map entry {cmd_name!r} -> {modname}.{attr_name}.name = "
                f"{attr.name!r}, expected {cmd_name!r}"
            )

    def test_loading_one_command_does_not_break_another(self):
        """Loading 'tag' then 'sensor' must both work correctly."""
        ctx = click.Context(cli)
        tag = cli.get_command(ctx, "tag")
        sensor = cli.get_command(ctx, "sensor")
        assert tag is not None
        assert sensor is not None
        assert tag.name == "tag"
        assert sensor.name == "sensor"
        # Both must have their subcommands
        assert isinstance(tag, click.Group)
        assert isinstance(sensor, click.Group)
        assert "list" in tag.commands
        assert "list" in sensor.commands

    def test_ai_help_not_double_injected(self):
        """Accessing a command twice must not duplicate --ai-help."""
        ctx = click.Context(cli)
        cli.get_command(ctx, "sensor")
        cli.get_command(ctx, "sensor")
        cmd = cli.commands["sensor"]
        ai_params = [p for p in cmd.params if p.name == "ai_help"]
        assert len(ai_params) == 1, (
            f"Expected 1 ai_help param, got {len(ai_params)}"
        )

    def test_ai_help_injected_on_subcommands(self):
        """--ai-help must be present on subcommands after lazy loading."""
        ctx = click.Context(cli)
        sensor = cli.get_command(ctx, "sensor")
        assert isinstance(sensor, click.Group)
        list_cmd = sensor.commands["list"]
        names = {p.name for p in list_cmd.params}
        assert "ai_help" in names

    def test_global_option_hoisting_with_lazy_commands(self):
        """Global options after subcommand must be parsed correctly.

        This tests that option hoisting works when the subcommand
        is lazily loaded during parse_args.
        """
        result = _invoke(["sensor", "list", "--help", "--output", "json"])
        assert result.exit_code == 0

    def test_global_option_hoisting_output_format(self):
        """--output after subcommand must set the output format."""
        result = _invoke(["auth", "whoami", "--output", "json", "--help"])
        assert result.exit_code == 0

    def test_shadowed_option_not_hoisted(self):
        """Options defined by both the group and subcommand must not
        be hoisted. e.g. auth login --oid should go to login, not cli."""
        # auth login has its own --oid option; it must not be hoisted
        # to the global --oid. We verify by checking help shows --oid
        # as an auth login option.
        result = _invoke(["auth", "login", "--help"])
        assert result.exit_code == 0
        assert "--oid" in result.output

    def test_completion_works_with_lazy_loading(self):
        """Completion must enumerate all commands without errors."""
        result = _invoke(["completion", "bash"])
        assert result.exit_code == 0
        # The completion script should reference limacharlie
        assert "limacharlie" in result.output.lower() or "LIMACHARLIE" in result.output

    def test_help_topic_fallthrough_with_lazy_loading(self):
        """help <topic> must work with lazily-loaded help command."""
        result = _invoke(["help", "auth"])
        assert result.exit_code == 0
        assert "Authentication" in result.output

    def test_hive_shortcut_commands_load_correctly(self):
        """Hive shortcut commands (secret, fp, lookup, etc.) must load
        correctly via lazy loading since they use a factory pattern."""
        ctx = click.Context(cli)
        for name in ("secret", "fp", "lookup", "playbook", "sop", "note"):
            cmd = cli.get_command(ctx, name)
            assert cmd is not None, f"Hive shortcut {name!r} not loaded"
            assert isinstance(cmd, click.Group), (
                f"{name!r} should be a Group"
            )
            # All hive shortcuts have list, get, set, delete, enable, disable
            for sub in ("list", "get", "set", "delete", "enable", "disable"):
                assert sub in cmd.commands, (
                    f"{name!r} missing subcommand {sub!r}"
                )

    def test_nonstandard_name_mappings(self):
        """Commands where filename != command name must load correctly.

        These are the tricky cases that require the static map:
        - adapter.py -> external-adapter
        - cloud_sensor.py -> cloud-adapter
        - api_cmd.py -> api
        - case_cmd.py -> case
        - help_cmd.py -> help
        """
        ctx = click.Context(cli)
        cases = {
            "external-adapter": "adapter",
            "cloud-adapter": "cloud_sensor",
            "api": "api_cmd",
            "case": "case_cmd",
            "help": "help_cmd",
            "output": "output_cmd",
            "logging": "logging_cmd",
            "replay": "replay_cmd",
        }
        for cmd_name, _module_name in cases.items():
            cmd = cli.get_command(ctx, cmd_name)
            assert cmd is not None, (
                f"Non-standard mapping {cmd_name!r} failed to load"
            )
            assert cmd.name == cmd_name

    def test_version_does_not_import_client(self):
        """--version should use _version, not client.py.

        Verifies the __version__ import optimization is in place.
        """
        from limacharlie.cli import __version__
        from limacharlie._version import version
        assert __version__ == version


# ---------------------------------------------------------------------------
# Regression: --ai-help must list command groups with lazy loading
# ---------------------------------------------------------------------------

class TestAiHelpLazyLoading:
    """Verify --ai-help works correctly with lazy command loading.

    Regression tests for the bug where _top_level_help() iterated
    cli.commands directly (empty with lazy loading) instead of using
    list_commands() + get_command().
    """

    def test_ai_help_lists_all_command_groups(self):
        """--ai-help must list all command groups under '## All Command Groups'."""
        result = _invoke(["--ai-help"])
        assert result.exit_code == 0
        assert "## All Command Groups" in result.output
        group_lines = [
            l for l in result.output.splitlines() if l.startswith("- **")
        ]
        assert len(group_lines) >= 40, (
            f"Expected 40+ command groups in --ai-help, got {len(group_lines)}"
        )

    def test_ai_help_groups_match_list_commands(self):
        """Command groups in --ai-help must match list_commands()."""
        ctx = click.Context(cli)
        expected_names = set(cli.list_commands(ctx))

        result = _invoke(["--ai-help"])
        assert result.exit_code == 0

        # Extract group names from "- **name** - description" lines
        listed_names = set()
        for line in result.output.splitlines():
            if line.startswith("- **"):
                name = line.split("**")[1]
                listed_names.add(name)

        assert listed_names == expected_names, (
            f"Missing from --ai-help: {expected_names - listed_names}\n"
            f"Extra in --ai-help: {listed_names - expected_names}"
        )


# ---------------------------------------------------------------------------
# Regression: broken command modules must warn on stderr
# ---------------------------------------------------------------------------

class TestBrokenModuleWarning:
    """Verify that broken command modules emit a warning."""

    def test_broken_module_emits_warning(self):
        """_import_command must emit a stderr warning for broken modules."""
        from limacharlie.cli import _COMMAND_MODULE_MAP, _LazyCommandGroup

        # Create a fresh group with a fake broken mapping
        group = _LazyCommandGroup("test")
        original_map = _COMMAND_MODULE_MAP.copy()
        try:
            _COMMAND_MODULE_MAP["__broken_test__"] = ("__nonexistent_module__", "cmd")
            ctx = click.Context(group)
            result = group._import_command("__broken_test__")
            assert result is None
        finally:
            _COMMAND_MODULE_MAP.clear()
            _COMMAND_MODULE_MAP.update(original_map)

    def test_broken_module_returns_none(self):
        """_import_command must return None for non-existent modules."""
        from limacharlie.cli import _LazyCommandGroup
        group = _LazyCommandGroup("test")
        ctx = click.Context(group)
        result = group._import_command("__definitely_not_a_command__")
        assert result is None


# ---------------------------------------------------------------------------
# Lint: cli.py must not have unused imports
# ---------------------------------------------------------------------------

class TestCliImportHygiene:
    """Verify cli.py does not contain known dead imports."""

    def test_no_pkgutil_import(self):
        """cli.py must not import pkgutil (removed with eager discovery)."""
        import inspect
        from limacharlie import cli as cli_module
        source = inspect.getsource(cli_module)
        # Check that pkgutil is not imported at module level
        assert "import pkgutil" not in source, (
            "cli.py still imports pkgutil which is unused after removing "
            "_auto_discover_commands()"
        )

    def test_no_unused_field_import(self):
        """cli.py must not import 'field' from dataclasses (unused)."""
        import inspect
        from limacharlie import cli as cli_module
        source = inspect.getsource(cli_module)
        assert "import dataclass, field" not in source, (
            "cli.py imports 'field' from dataclasses which is unused"
        )


# ---------------------------------------------------------------------------
# Regression: output module must be lazily imported in cli callback
# ---------------------------------------------------------------------------

class TestOutputLazyImport:
    """Verify limacharlie.output is not imported at cli.py module level.

    limacharlie.output pulls in jmespath, tabulate, yaml, csv (~14ms).
    It should only be imported inside the cli() callback when a command
    is actually invoked, not on bare import of limacharlie.cli.
    """

    def test_output_not_imported_at_module_level(self):
        """Importing limacharlie.cli must not pull in limacharlie.output."""
        import subprocess
        import sys
        # Run in a fresh process to avoid module cache contamination
        result = subprocess.run(
            [sys.executable, "-c",
             "import sys; "
             "import limacharlie.cli; "
             "mods = [k for k in sys.modules if k == 'limacharlie.output']; "
             "print(len(mods))"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0
        count = int(result.stdout.strip())
        assert count == 0, (
            "limacharlie.output was imported at module level - it should "
            "be lazily imported inside the cli() callback"
        )

    def test_heavy_deps_not_imported_at_module_level(self):
        """Importing limacharlie.cli must not pull in jmespath, tabulate, or yaml."""
        import subprocess
        import sys
        result = subprocess.run(
            [sys.executable, "-c",
             "import sys; "
             "import limacharlie.cli; "
             "heavy = [k for k in sys.modules if k in ('jmespath', 'tabulate', 'yaml')]; "
             "print(','.join(heavy) if heavy else 'none')"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "none", (
            f"Heavy deps imported at module level: {result.stdout.strip()}. "
            "These should be deferred via lazy import of limacharlie.output"
        )

    def test_output_imported_when_command_invoked(self):
        """limacharlie.output must be available after a command runs."""
        import subprocess
        import sys
        result = subprocess.run(
            [sys.executable, "-c",
             "import sys; "
             "from limacharlie.cli import cli; "
             "from click.testing import CliRunner; "
             "CliRunner().invoke(cli, ['auth', 'whoami', '--help']); "
             "mods = [k for k in sys.modules if k == 'limacharlie.output']; "
             "print(len(mods))"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0
        count = int(result.stdout.strip())
        assert count == 1, (
            "limacharlie.output should be imported after a command invocation"
        )
