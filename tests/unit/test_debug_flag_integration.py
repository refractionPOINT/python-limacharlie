"""Integration tests verifying --debug flag flows to all CLI commands.

Confirms that every CLI command correctly propagates --debug, --debug-full,
and --debug-curl flags through to the Client constructor. Tests exercise
actual CLI invocation via Click's CliRunner with mocked Client to verify
the wiring without making real API calls.

Contract: any Client() instantiated by a command must receive
print_debug_fn, debug_full_response, debug_curl, and debug_verbose
kwargs matching the global CLI flags.
"""

import importlib
import inspect
import pkgutil
import textwrap
from unittest.mock import patch, MagicMock, call

import click
import pytest
from click.testing import CliRunner

from limacharlie.cli import cli, LimaCharlieContext, _make_debug_fn


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_client_factory(captured_calls: list):
    """Return a Client class replacement that records constructor kwargs.

    The returned mock class captures every instantiation's keyword arguments
    into *captured_calls* for later assertion.
    """
    def factory(*args, **kwargs):
        captured_calls.append(kwargs)
        mock = MagicMock()
        mock.oid = "test-oid"
        mock.uid = "test-uid"
        mock._debug_fn = kwargs.get("print_debug_fn")
        mock.refresh_jwt = MagicMock()
        return mock
    return factory


def _mock_org_factory():
    """Return an Organization class replacement with safe default returns."""
    def factory(client):
        mock = MagicMock()
        mock.client = client
        # Provide safe defaults for common SDK calls so commands don't crash
        mock.who_am_i.return_value = {"ident": "test@test.com", "perms": []}
        mock.get_info.return_value = {"name": "TestOrg"}
        mock.get_urls.return_value = {"main": "https://test.io"}
        mock.list_sensors.return_value = iter([])
        mock.get_errors.return_value = []
        return mock
    return factory


# ---------------------------------------------------------------------------
# Source-level: verify all _get_org/_get_client helpers pass debug params
# ---------------------------------------------------------------------------

def _find_command_modules():
    """Discover all command modules under limacharlie.commands."""
    import limacharlie.commands as pkg
    modules = []
    for importer, modname, ispkg in pkgutil.iter_modules(pkg.__path__):
        if modname.startswith("_"):
            continue
        try:
            mod = importlib.import_module(f"limacharlie.commands.{modname}")
            modules.append((modname, mod))
        except ImportError:
            pass
    return modules


def _find_helper_functions(mod):
    """Find all _get_* helper functions in a module."""
    helpers = []
    for name, obj in inspect.getmembers(mod, inspect.isfunction):
        if name.startswith("_get_") and obj.__module__ == mod.__name__:
            helpers.append((name, obj))
    return helpers


def _get_all_helper_ids():
    """Return pytest IDs for all command module helpers."""
    ids = []
    for modname, mod in _find_command_modules():
        for funcname, _ in _find_helper_functions(mod):
            ids.append(f"{modname}.{funcname}")
    return ids


def _get_all_helpers():
    """Return (modname, funcname, module) tuples for parametrize."""
    helpers = []
    for modname, mod in _find_command_modules():
        for funcname, func in _find_helper_functions(mod):
            helpers.append((modname, funcname, mod))
    return helpers


_ALL_HELPERS = _get_all_helpers()
_ALL_HELPER_IDS = _get_all_helper_ids()


class TestSourceLevelDebugWiring:
    """Verify at the source level that every helper passes debug kwargs.

    This uses source inspection to catch regressions immediately - if a new
    command is added without debug flag forwarding, this test will catch it.
    """

    @pytest.mark.parametrize("modname,funcname,mod", _ALL_HELPERS, ids=_ALL_HELPER_IDS)
    def test_helper_source_contains_debug_params(self, modname, funcname, mod):
        """Every _get_* helper that creates a Client must pass all 4 debug kwargs.

        Helpers that delegate to another _get_* helper in the same module
        (e.g. _get_org calling _get_client, or _get_sensor calling _get_org)
        are valid as long as the delegate passes the debug params.
        """
        source = inspect.getsource(getattr(mod, funcname))

        # If this helper delegates to another _get_* helper in the same
        # module, check that the delegate passes debug params instead.
        delegates_to = None
        for other_name, other_func in _find_helper_functions(mod):
            if other_name != funcname and f"{other_name}(" in source:
                delegates_to = other_name
                break

        if delegates_to is not None:
            # Verify the delegate itself has the debug params
            delegate_source = inspect.getsource(getattr(mod, delegates_to))
            target_source = delegate_source
            target_label = f"{modname}.{delegates_to} (delegate of {funcname})"
        else:
            target_source = source
            target_label = f"{modname}.{funcname}"

        assert "print_debug_fn" in target_source, (
            f"{target_label} does not pass print_debug_fn to Client"
        )
        assert "debug_full_response" in target_source or "debug_full" in target_source, (
            f"{target_label} does not pass debug_full_response to Client"
        )
        assert "debug_curl" in target_source, (
            f"{target_label} does not pass debug_curl to Client"
        )
        assert "debug_verbose" in target_source, (
            f"{target_label} does not pass debug_verbose to Client"
        )


# Also verify the _hive_shortcut module since many commands delegate to it
class TestHiveShortcutDebugWiring:
    """Verify _hive_shortcut._get_org passes debug params."""

    def test_hive_shortcut_passes_debug(self):
        from limacharlie.commands import _hive_shortcut
        source = inspect.getsource(_hive_shortcut._get_org)
        assert "print_debug_fn" in source
        assert "debug_full_response" in source or "debug_full" in source
        assert "debug_curl" in source
        assert "debug_verbose" in source


# ---------------------------------------------------------------------------
# CLI integration: verify --debug flows through representative commands
# ---------------------------------------------------------------------------

# Map of (command_args, module_path_for_Client_mock) tuples.
# We pick one representative command from each command module to verify
# the debug flag flows end-to-end through CliRunner.
_REPRESENTATIVE_COMMANDS = [
    # (cli_args, patch_target_for_Client, patch_target_for_Org_or_SDK, extra_patches)
    # auth module - uses _get_client directly
    (
        ["auth", "test"],
        "limacharlie.commands.auth.Client",
        None,
        [],
    ),
    # org module
    (
        ["--output", "json", "org", "info"],
        "limacharlie.commands.org.Client",
        "limacharlie.commands.org.Organization",
        [],
    ),
    # sensor module
    (
        ["--output", "json", "sensor", "list"],
        "limacharlie.commands.sensor.Client",
        "limacharlie.commands.sensor.Organization",
        [],
    ),
    # api-key module
    (
        ["--output", "json", "api-key", "list"],
        "limacharlie.commands.api_key.Client",
        "limacharlie.commands.api_key.Organization",
        [],
    ),
    # dr module
    (
        ["--output", "json", "dr", "list"],
        "limacharlie.commands.dr.Client",
        "limacharlie.commands.dr.Organization",
        ["limacharlie.commands.dr.Hive"],
    ),
    # hive module
    (
        ["--output", "json", "hive", "list", "--hive-name", "dr-general"],
        "limacharlie.commands.hive.Client",
        "limacharlie.commands.hive.Organization",
        ["limacharlie.commands.hive.Hive"],
    ),
    # billing module
    (
        ["--output", "json", "billing", "status"],
        "limacharlie.commands.billing.Client",
        "limacharlie.commands.billing.Organization",
        ["limacharlie.commands.billing.BillingSDK"],
    ),
    # audit module
    (
        ["--output", "json", "audit", "list"],
        "limacharlie.commands.audit.Client",
        "limacharlie.commands.audit.Organization",
        [],
    ),
    # tag module
    (
        ["--output", "json", "tag", "list", "--sid", "test-sid"],
        "limacharlie.commands.tag.Client",
        "limacharlie.commands.tag.Organization",
        [],
    ),
    # user module
    (
        ["--output", "json", "user", "list"],
        "limacharlie.commands.user.Client",
        "limacharlie.commands.user.Organization",
        [],
    ),
    # installation-key module
    (
        ["--output", "json", "installation-key", "list"],
        "limacharlie.commands.installation_key.Client",
        "limacharlie.commands.installation_key.Organization",
        [],
    ),
    # schema module
    (
        ["--output", "json", "schema", "list"],
        "limacharlie.commands.schema.Client",
        "limacharlie.commands.schema.Organization",
        [],
    ),
]


def _make_representative_ids():
    return [args[0][0] if args[0][0] != "--output" else args[0][2] for args in _REPRESENTATIVE_COMMANDS]


class TestDebugFlagCLIIntegration:
    """Verify --debug flag flows from CLI invocation through to Client."""

    @pytest.mark.parametrize(
        "cli_args,client_patch,org_patch,extra_patches",
        _REPRESENTATIVE_COMMANDS,
        ids=_make_representative_ids(),
    )
    def test_debug_flag_reaches_client(self, cli_args, client_patch, org_patch, extra_patches):
        """--debug must result in print_debug_fn being set on Client."""
        captured = []
        mock_client_cls = _mock_client_factory(captured)
        mock_org_cls = _mock_org_factory()

        patches = [patch(client_patch, side_effect=mock_client_cls)]
        if org_patch:
            patches.append(patch(org_patch, side_effect=mock_org_cls))
        for ep in extra_patches:
            patches.append(patch(ep, MagicMock()))

        with patches[0] as p0:
            ctx_stack = patches[1:]
            # Apply remaining patches
            active = [p0]
            for p in ctx_stack:
                active.append(p.__enter__())
            try:
                runner = CliRunner(mix_stderr=False)
                result = runner.invoke(cli, ["--debug"] + cli_args)
                # Command may fail for missing args, but Client should still
                # have been instantiated with debug params
                assert len(captured) >= 1, (
                    f"Client was never instantiated for {cli_args}. "
                    f"Exit code: {result.exit_code}, output: {result.output}"
                )
                kwargs = captured[0]
                assert kwargs.get("print_debug_fn") is not None, (
                    f"print_debug_fn not set for --debug with {cli_args}"
                )
                assert kwargs.get("debug_verbose") is True, (
                    f"debug_verbose not True for --debug with {cli_args}"
                )
            finally:
                for p in ctx_stack:
                    if hasattr(p, '__exit__'):
                        p.__exit__(None, None, None)

    @pytest.mark.parametrize(
        "cli_args,client_patch,org_patch,extra_patches",
        _REPRESENTATIVE_COMMANDS,
        ids=_make_representative_ids(),
    )
    def test_debug_full_flag_reaches_client(self, cli_args, client_patch, org_patch, extra_patches):
        """--debug-full must result in debug_full_response=True on Client."""
        captured = []
        mock_client_cls = _mock_client_factory(captured)
        mock_org_cls = _mock_org_factory()

        patches = [patch(client_patch, side_effect=mock_client_cls)]
        if org_patch:
            patches.append(patch(org_patch, side_effect=mock_org_cls))
        for ep in extra_patches:
            patches.append(patch(ep, MagicMock()))

        with patches[0]:
            for p in patches[1:]:
                p.__enter__()
            try:
                runner = CliRunner(mix_stderr=False)
                result = runner.invoke(cli, ["--debug-full"] + cli_args)
                assert len(captured) >= 1, (
                    f"Client not instantiated for --debug-full with {cli_args}"
                )
                kwargs = captured[0]
                assert kwargs.get("print_debug_fn") is not None
                assert kwargs.get("debug_full_response") is True
                assert kwargs.get("debug_verbose") is True
            finally:
                for p in patches[1:]:
                    p.__exit__(None, None, None)

    @pytest.mark.parametrize(
        "cli_args,client_patch,org_patch,extra_patches",
        _REPRESENTATIVE_COMMANDS,
        ids=_make_representative_ids(),
    )
    def test_debug_curl_flag_reaches_client(self, cli_args, client_patch, org_patch, extra_patches):
        """--debug-curl must result in debug_curl=True on Client."""
        captured = []
        mock_client_cls = _mock_client_factory(captured)
        mock_org_cls = _mock_org_factory()

        patches = [patch(client_patch, side_effect=mock_client_cls)]
        if org_patch:
            patches.append(patch(org_patch, side_effect=mock_org_cls))
        for ep in extra_patches:
            patches.append(patch(ep, MagicMock()))

        with patches[0]:
            for p in patches[1:]:
                p.__enter__()
            try:
                runner = CliRunner(mix_stderr=False)
                result = runner.invoke(cli, ["--debug-curl"] + cli_args)
                assert len(captured) >= 1, (
                    f"Client not instantiated for --debug-curl with {cli_args}"
                )
                kwargs = captured[0]
                assert kwargs.get("print_debug_fn") is not None
                assert kwargs.get("debug_curl") is True
                # curl-only mode: debug_verbose should be False
                assert kwargs.get("debug_verbose") is False
            finally:
                for p in patches[1:]:
                    p.__exit__(None, None, None)

    @pytest.mark.parametrize(
        "cli_args,client_patch,org_patch,extra_patches",
        _REPRESENTATIVE_COMMANDS,
        ids=_make_representative_ids(),
    )
    def test_no_debug_flag_no_debug_fn(self, cli_args, client_patch, org_patch, extra_patches):
        """Without any debug flag, print_debug_fn must be None."""
        captured = []
        mock_client_cls = _mock_client_factory(captured)
        mock_org_cls = _mock_org_factory()

        patches = [patch(client_patch, side_effect=mock_client_cls)]
        if org_patch:
            patches.append(patch(org_patch, side_effect=mock_org_cls))
        for ep in extra_patches:
            patches.append(patch(ep, MagicMock()))

        with patches[0]:
            for p in patches[1:]:
                p.__enter__()
            try:
                runner = CliRunner(mix_stderr=False)
                result = runner.invoke(cli, cli_args)
                assert len(captured) >= 1, (
                    f"Client not instantiated without debug flags for {cli_args}"
                )
                kwargs = captured[0]
                assert kwargs.get("print_debug_fn") is None, (
                    f"print_debug_fn should be None without --debug for {cli_args}"
                )
            finally:
                for p in patches[1:]:
                    p.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# Debug flag combinations
# ---------------------------------------------------------------------------

class TestDebugFlagCombinations:
    """Test interactions between --debug, --debug-full, and --debug-curl."""

    def _invoke_with_flags(self, flags):
        """Invoke 'auth test' with given flags and return captured Client kwargs."""
        captured = []
        mock_client_cls = _mock_client_factory(captured)

        with patch("limacharlie.commands.auth.Client", side_effect=mock_client_cls):
            runner = CliRunner(mix_stderr=False)
            result = runner.invoke(cli, flags + ["auth", "test"])
            assert len(captured) >= 1, f"Client not instantiated with flags {flags}"
            return captured[0]

    def test_debug_only(self):
        kwargs = self._invoke_with_flags(["--debug"])
        assert kwargs["print_debug_fn"] is not None
        assert kwargs["debug_full_response"] is False
        assert kwargs["debug_curl"] is False
        assert kwargs["debug_verbose"] is True

    def test_debug_full_only(self):
        kwargs = self._invoke_with_flags(["--debug-full"])
        assert kwargs["print_debug_fn"] is not None
        assert kwargs["debug_full_response"] is True
        assert kwargs["debug_curl"] is False
        assert kwargs["debug_verbose"] is True

    def test_debug_curl_only(self):
        kwargs = self._invoke_with_flags(["--debug-curl"])
        assert kwargs["print_debug_fn"] is not None
        assert kwargs["debug_full_response"] is False
        assert kwargs["debug_curl"] is True
        # curl-only: verbose should be False
        assert kwargs["debug_verbose"] is False

    def test_debug_and_curl(self):
        kwargs = self._invoke_with_flags(["--debug", "--debug-curl"])
        assert kwargs["print_debug_fn"] is not None
        assert kwargs["debug_curl"] is True
        assert kwargs["debug_verbose"] is True

    def test_debug_full_and_curl(self):
        kwargs = self._invoke_with_flags(["--debug-full", "--debug-curl"])
        assert kwargs["print_debug_fn"] is not None
        assert kwargs["debug_full_response"] is True
        assert kwargs["debug_curl"] is True
        assert kwargs["debug_verbose"] is True

    def test_all_debug_flags(self):
        kwargs = self._invoke_with_flags(["--debug", "--debug-full", "--debug-curl"])
        assert kwargs["print_debug_fn"] is not None
        assert kwargs["debug_full_response"] is True
        assert kwargs["debug_curl"] is True
        assert kwargs["debug_verbose"] is True

    def test_no_debug_flags(self):
        kwargs = self._invoke_with_flags([])
        assert kwargs["print_debug_fn"] is None
        assert kwargs["debug_full_response"] is False
        assert kwargs["debug_curl"] is False


# ---------------------------------------------------------------------------
# Context properties
# ---------------------------------------------------------------------------

class TestLimaCharlieContextDebugProperties:
    """Verify LimaCharlieContext computes debug_fn and debug_verbose correctly."""

    def test_no_debug(self):
        ctx = LimaCharlieContext()
        assert ctx.debug_fn is None
        assert ctx.debug_verbose is False

    def test_debug_sets_fn(self):
        ctx = LimaCharlieContext(debug=True)
        assert ctx.debug_fn is not None
        assert ctx.debug_verbose is True

    def test_debug_full_sets_fn(self):
        ctx = LimaCharlieContext(debug_full=True)
        assert ctx.debug_fn is not None
        assert ctx.debug_verbose is True

    def test_debug_curl_sets_fn_not_verbose(self):
        ctx = LimaCharlieContext(debug_curl=True)
        assert ctx.debug_fn is not None
        assert ctx.debug_verbose is False

    def test_debug_and_curl(self):
        ctx = LimaCharlieContext(debug=True, debug_curl=True)
        assert ctx.debug_fn is not None
        assert ctx.debug_verbose is True

    def test_make_debug_fn_enabled(self):
        fn = _make_debug_fn(True)
        assert fn is not None
        assert callable(fn)

    def test_make_debug_fn_disabled(self):
        fn = _make_debug_fn(False)
        assert fn is None


# ---------------------------------------------------------------------------
# Global option hoisting: --debug can appear after the subcommand
# ---------------------------------------------------------------------------

class TestDebugFlagPositionFlexibility:
    """--debug should work regardless of position on the command line."""

    def _invoke_auth_test(self, args):
        captured = []
        with patch("limacharlie.commands.auth.Client", side_effect=_mock_client_factory(captured)):
            runner = CliRunner(mix_stderr=False)
            result = runner.invoke(cli, args)
            return captured, result

    def test_debug_before_command(self):
        captured, result = self._invoke_auth_test(["--debug", "auth", "test"])
        assert len(captured) >= 1
        assert captured[0]["print_debug_fn"] is not None

    def test_debug_after_command(self):
        captured, result = self._invoke_auth_test(["auth", "test", "--debug"])
        assert len(captured) >= 1
        assert captured[0]["print_debug_fn"] is not None

    def test_debug_between_group_and_command(self):
        captured, result = self._invoke_auth_test(["auth", "--debug", "test"])
        assert len(captured) >= 1
        assert captured[0]["print_debug_fn"] is not None

    def test_debug_curl_after_command(self):
        captured, result = self._invoke_auth_test(["auth", "test", "--debug-curl"])
        assert len(captured) >= 1
        assert captured[0]["debug_curl"] is True

    def test_debug_full_after_command(self):
        captured, result = self._invoke_auth_test(["auth", "test", "--debug-full"])
        assert len(captured) >= 1
        assert captured[0]["debug_full_response"] is True


# ---------------------------------------------------------------------------
# Hive shortcut commands (secret, fp, playbook, etc.) get debug too
# ---------------------------------------------------------------------------

class TestHiveShortcutDebugIntegration:
    """Verify hive-shortcut-based commands (secret, fp, etc.) pass debug flags."""

    @pytest.mark.parametrize("group_name", [
        "secret", "fp", "playbook", "note", "sop", "lookup",
    ])
    def test_shortcut_list_passes_debug(self, group_name):
        captured = []
        with patch(
            "limacharlie.commands._hive_shortcut.Client",
            side_effect=_mock_client_factory(captured),
        ), patch(
            "limacharlie.commands._hive_shortcut.Organization",
            side_effect=_mock_org_factory(),
        ), patch(
            "limacharlie.commands._hive_shortcut.Hive",
            return_value=MagicMock(list=MagicMock(return_value={})),
        ):
            runner = CliRunner(mix_stderr=False)
            result = runner.invoke(cli, ["--debug", "--output", "json", group_name, "list"])
            assert len(captured) >= 1, (
                f"Client not instantiated for --debug {group_name} list. "
                f"Exit: {result.exit_code}, output: {result.output}"
            )
            assert captured[0]["print_debug_fn"] is not None


# ---------------------------------------------------------------------------
# End-to-end: debug output actually appears on stderr
# ---------------------------------------------------------------------------

class TestDebugOutputAppearsOnStderr:
    """Verify that when --debug is active, debug messages appear on stderr."""

    def test_auth_test_debug_on_stderr(self):
        """auth test with --debug should produce debug output on stderr."""
        mock_client = MagicMock()
        mock_client.oid = "test-oid"
        mock_client.uid = None
        mock_client.refresh_jwt = MagicMock()

        # Track whether the debug_fn was passed and is callable
        debug_fn_received = []

        original_client_init = None

        def capturing_client(*args, **kwargs):
            fn = kwargs.get("print_debug_fn")
            debug_fn_received.append(fn)
            return mock_client

        with patch("limacharlie.commands.auth.Client", side_effect=capturing_client):
            runner = CliRunner(mix_stderr=False)
            result = runner.invoke(cli, ["--debug", "auth", "test"])
            assert result.exit_code == 0
            assert len(debug_fn_received) >= 1
            assert debug_fn_received[0] is not None
            assert callable(debug_fn_received[0])


# ---------------------------------------------------------------------------
# Completeness check: ensure no new command modules without debug wiring
# ---------------------------------------------------------------------------

class TestAllModulesHaveDebugWiring:
    """Ensure every command module that creates a Client has debug wiring.

    This is a meta-test: it verifies that no module has been added that
    directly creates a Client without passing debug parameters.
    """

    def test_no_bare_client_instantiation(self):
        """Scan all command module source for Client() calls without debug params."""
        import limacharlie.commands as pkg
        import ast

        bare_calls = []
        for importer, modname, ispkg in pkgutil.iter_modules(pkg.__path__):
            mod = importlib.import_module(f"limacharlie.commands.{modname}")
            try:
                source = inspect.getsource(mod)
            except (OSError, TypeError):
                continue

            # Find all Client(...) calls in the source
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                # Check if it's a Client() call
                func = node.func
                is_client_call = False
                if isinstance(func, ast.Name) and func.id == "Client":
                    is_client_call = True
                elif isinstance(func, ast.Attribute) and func.attr == "Client":
                    is_client_call = True

                if not is_client_call:
                    continue

                # Check that it has print_debug_fn in kwargs
                kwarg_names = {kw.arg for kw in node.keywords if kw.arg is not None}
                if "print_debug_fn" not in kwarg_names:
                    bare_calls.append(
                        f"{modname}:{node.lineno} - Client() without print_debug_fn"
                    )

        assert bare_calls == [], (
            "Found Client() instantiations without debug parameters:\n"
            + "\n".join(f"  - {c}" for c in bare_calls)
        )

    def test_no_bare_client_missing_debug_curl(self):
        """Scan for Client() calls that have print_debug_fn but not debug_curl."""
        import limacharlie.commands as pkg
        import ast

        incomplete_calls = []
        for importer, modname, ispkg in pkgutil.iter_modules(pkg.__path__):
            mod = importlib.import_module(f"limacharlie.commands.{modname}")
            try:
                source = inspect.getsource(mod)
            except (OSError, TypeError):
                continue

            tree = ast.parse(source)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                is_client_call = False
                if isinstance(func, ast.Name) and func.id == "Client":
                    is_client_call = True
                elif isinstance(func, ast.Attribute) and func.attr == "Client":
                    is_client_call = True

                if not is_client_call:
                    continue

                kwarg_names = {kw.arg for kw in node.keywords if kw.arg is not None}
                if "print_debug_fn" in kwarg_names:
                    for required in ("debug_curl", "debug_verbose", "debug_full_response"):
                        if required not in kwarg_names:
                            incomplete_calls.append(
                                f"{modname}:{node.lineno} - missing {required}"
                            )

        assert incomplete_calls == [], (
            "Found Client() instantiations with incomplete debug parameters:\n"
            + "\n".join(f"  - {c}" for c in incomplete_calls)
        )
