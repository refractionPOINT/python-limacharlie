"""Lint tests for _COMMAND_MODULE_MAP in limacharlie.cli.

Validates that the static command-to-module map used for lazy loading
is complete, correct, and in sync with the actual command modules on
disk. These tests fail immediately when a developer adds, removes, or
renames a command module without updating the map.

This file is intentionally separate from the regression tests so that
the failure message clearly points to the map as the thing to fix.

Run with: pytest tests/unit/test_cli_command_map_lint.py -v
"""

from __future__ import annotations

import importlib
import pkgutil

import click
import pytest

from limacharlie.cli import _COMMAND_MODULE_MAP


def _discover_command_modules() -> set[str]:
    """Return all non-private module names in limacharlie/commands/."""
    commands_mod = importlib.import_module("limacharlie.commands")
    return {
        modname
        for _importer, modname, _ispkg in pkgutil.iter_modules(commands_mod.__path__)
        if not modname.startswith("_")
    }


def _discover_actual_mapping() -> dict[str, tuple[str, str]]:
    """Import every command module and build the ground-truth mapping.

    Returns: {click_command_name: (module_name, attr_name)}
    """
    actual = {}
    commands_mod = importlib.import_module("limacharlie.commands")
    for _importer, modname, _ispkg in pkgutil.iter_modules(commands_mod.__path__):
        if modname.startswith("_"):
            continue
        mod = importlib.import_module(f"limacharlie.commands.{modname}")
        for attr_name in ("group", "cmd"):
            attr = getattr(mod, attr_name, None)
            if isinstance(attr, click.BaseCommand):
                actual[attr.name] = (modname, attr_name)
                break
    return actual


class TestCommandModuleMapCompleteness:
    """Verify _COMMAND_MODULE_MAP covers every command module on disk.

    If a new module is added to limacharlie/commands/ without a
    corresponding entry in _COMMAND_MODULE_MAP, these tests fail with
    a clear message telling the developer exactly what to add.
    """

    def test_no_missing_modules(self):
        """Every command module on disk must have an entry in the map.

        This is the most important check - it catches the case where
        a developer adds a new command module but forgets to update
        _COMMAND_MODULE_MAP.
        """
        on_disk = _discover_command_modules()
        in_map = {modname for modname, _attr in _COMMAND_MODULE_MAP.values()}

        missing = on_disk - in_map
        if missing:
            # Import the missing modules to give a helpful error message
            hints = []
            for modname in sorted(missing):
                mod = importlib.import_module(f"limacharlie.commands.{modname}")
                for attr_name in ("group", "cmd"):
                    attr = getattr(mod, attr_name, None)
                    if isinstance(attr, click.BaseCommand):
                        hints.append(
                            f'    "{attr.name}": ("{modname}", "{attr_name}"),'
                        )
                        break
                else:
                    hints.append(
                        f"    # {modname}: no 'group' or 'cmd' attribute found"
                    )

            pytest.fail(
                f"Command modules on disk but missing from _COMMAND_MODULE_MAP "
                f"in limacharlie/cli.py:\n\n"
                f"  Missing modules: {sorted(missing)}\n\n"
                f"  Add these entries to _COMMAND_MODULE_MAP:\n"
                + "\n".join(hints)
            )

    def test_no_stale_map_entries(self):
        """Every entry in the map must correspond to a module on disk.

        Catches the case where a command module is deleted but its
        map entry is left behind.
        """
        on_disk = _discover_command_modules()
        in_map = {modname for modname, _attr in _COMMAND_MODULE_MAP.values()}

        stale = in_map - on_disk
        if stale:
            # Find which map keys reference the stale modules
            stale_keys = [
                cmd_name
                for cmd_name, (modname, _) in _COMMAND_MODULE_MAP.items()
                if modname in stale
            ]
            pytest.fail(
                f"Stale entries in _COMMAND_MODULE_MAP reference modules "
                f"that no longer exist on disk:\n\n"
                f"  Stale modules: {sorted(stale)}\n"
                f"  Remove these map entries: {sorted(stale_keys)}"
            )


class TestCommandModuleMapCorrectness:
    """Verify every entry in _COMMAND_MODULE_MAP is correct."""

    @pytest.mark.parametrize(
        "cmd_name",
        sorted(_COMMAND_MODULE_MAP.keys()),
    )
    def test_map_entry_importable_and_correct(self, cmd_name: str):
        """Each map entry must point to an importable module that exports
        a Click command with the expected name.

        This catches:
        - Typos in module names
        - Wrong attribute name (group vs cmd)
        - Command name mismatch after rename
        """
        modname, attr_name = _COMMAND_MODULE_MAP[cmd_name]
        module_path = f"limacharlie.commands.{modname}"

        # Must be importable
        try:
            mod = importlib.import_module(module_path)
        except ImportError as e:
            pytest.fail(
                f"_COMMAND_MODULE_MAP[{cmd_name!r}] references "
                f"module {module_path!r} which cannot be imported: {e}"
            )

        # Must have the expected attribute
        attr = getattr(mod, attr_name, None)
        assert attr is not None, (
            f"_COMMAND_MODULE_MAP[{cmd_name!r}] references "
            f"{module_path}.{attr_name} which does not exist. "
            f"Available attributes: {[a for a in dir(mod) if not a.startswith('_')]}"
        )

        # Must be a Click command
        assert isinstance(attr, click.BaseCommand), (
            f"_COMMAND_MODULE_MAP[{cmd_name!r}] -> {module_path}.{attr_name} "
            f"is {type(attr).__name__}, not a Click command"
        )

        # Command name must match
        assert attr.name == cmd_name, (
            f"_COMMAND_MODULE_MAP[{cmd_name!r}] -> {module_path}.{attr_name} "
            f"has name {attr.name!r}, expected {cmd_name!r}. "
            f"Update the map key or the Click command name."
        )


class TestCommandModuleMapMatchesRuntime:
    """Verify the static map exactly matches what auto-discovery would find.

    This is the ultimate consistency check: import every module (like
    the old eager loading did) and verify the result is identical to
    what the static map declares.
    """

    def test_map_matches_auto_discovery(self):
        """The static map must produce the same result as importing
        every module and inspecting its exports."""
        actual = _discover_actual_mapping()

        # Check both directions
        map_names = set(_COMMAND_MODULE_MAP.keys())
        actual_names = set(actual.keys())

        missing_from_map = actual_names - map_names
        extra_in_map = map_names - actual_names

        errors = []
        if missing_from_map:
            for name in sorted(missing_from_map):
                modname, attr_name = actual[name]
                errors.append(
                    f"  Missing: \"{name}\": (\"{modname}\", \"{attr_name}\"),"
                )
        if extra_in_map:
            for name in sorted(extra_in_map):
                errors.append(f"  Extra (remove): \"{name}\"")

        # Also check that matching entries agree on module/attr
        for name in map_names & actual_names:
            if _COMMAND_MODULE_MAP[name] != actual[name]:
                errors.append(
                    f"  Mismatch for {name!r}: "
                    f"map has {_COMMAND_MODULE_MAP[name]}, "
                    f"actual is {actual[name]}"
                )

        if errors:
            pytest.fail(
                "_COMMAND_MODULE_MAP does not match auto-discovered commands.\n"
                "Update _COMMAND_MODULE_MAP in limacharlie/cli.py:\n\n"
                + "\n".join(errors)
            )
