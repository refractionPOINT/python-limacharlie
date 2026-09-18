"""Tests for limacharlie.discovery module."""

import click
import pytest

from limacharlie.discovery import (
    MCP_USE_CASE_PROFILES,
    PROFILES,
    register_explain,
    get_explain,
    get_profile,
    list_profiles,
    format_discovery,
)


class TestProfiles:
    def test_all_profiles_exist(self):
        expected = [
            "core",
            "sensor_management", "detection_engineering", "historical_data",
            "live_investigation", "threat_response", "fleet_management",
            "platform_admin", "ai_powered", "api_access", "cases",
            "investigation_management", "cloud_security", "email_security",
        ]
        for name in expected:
            assert name in PROFILES, f"Missing profile: {name}"

    def test_each_profile_has_description_and_commands(self):
        for name, profile in PROFILES.items():
            assert "description" in profile, f"Profile {name} missing description"
            assert "commands" in profile, f"Profile {name} missing commands"
            assert len(profile["commands"]) > 0, f"Profile {name} has no commands"

    def test_mcp_use_case_profiles_are_available(self):
        """Keep CLI discovery aligned with the MCP server's use-case names."""
        assert MCP_USE_CASE_PROFILES <= PROFILES.keys()

    def test_get_profile(self):
        profile = get_profile("sensor_management")
        assert profile is not None
        assert "sensor list" in profile["commands"]

    def test_get_profile_unknown(self):
        assert get_profile("nonexistent") is None

    def test_list_profiles(self):
        profiles = list_profiles()
        assert len(profiles) == len(PROFILES)
        names = [p[0] for p in profiles]
        assert "sensor_management" in names


def _resolve(path: str) -> str | None:
    """Resolve a profile entry against the live command tree.

    Returns None when the path names a real, runnable command, or a
    human-readable reason when it does not.
    """
    import importlib

    from limacharlie.cli import _COMMAND_MODULE_MAP

    parts = path.split()
    top = parts[0]
    if top not in _COMMAND_MODULE_MAP:
        return f"no top-level command named {top!r}"

    modname, attr = _COMMAND_MODULE_MAP[top]
    cmd = getattr(importlib.import_module(f"limacharlie.commands.{modname}"), attr)

    for i, part in enumerate(parts[1:]):
        parent = " ".join(parts[: i + 1])
        if not isinstance(cmd, click.Group):
            return f"{parent!r} takes no subcommands, so {part!r} cannot exist"
        sub = cmd.commands.get(part)
        if sub is None:
            options = ", ".join(sorted(cmd.commands))
            return f"{parent!r} has no subcommand {part!r} (it has: {options})"
        cmd = sub

    if isinstance(cmd, click.Group):
        return f"{path!r} is a group, not a runnable command"
    return None


def _leaf_paths(cmd: click.BaseCommand, prefix: list[str]) -> list[str]:
    """Every runnable command path under ``cmd``, space-joined."""
    if isinstance(cmd, click.Group):
        paths = []
        for name, sub in cmd.commands.items():
            paths.extend(_leaf_paths(sub, prefix + [name]))
        return paths
    return [" ".join(prefix)]


class TestProfileEntriesResolve:
    """Every profile entry must name a command that actually exists.

    ``limacharlie help discover`` prints these strings as literal
    ``limacharlie <entry>`` invocations, so a rotted entry tells an
    operator — or an agent — to run something that cannot work. This
    catches a command being renamed or moved out from under a profile.

    Note this is deliberately one-directional: it does not require that
    every command appear in some profile. Which commands are worth
    surfacing is a curation call, and many groups are not profiled yet.
    """

    def test_no_unresolvable_entries(self):
        broken = []
        for profile_name, profile in sorted(PROFILES.items()):
            for entry in profile["commands"]:
                reason = _resolve(entry)
                if reason is not None:
                    broken.append(f'    [{profile_name}] "{entry}" -> {reason}')

        if broken:
            pytest.fail(
                "Discovery profiles advertise commands that do not exist. "
                "'limacharlie help discover' prints these verbatim, so each "
                "one is advice that cannot be followed:\n\n"
                + "\n".join(broken)
                + "\n\n  Fix the spelling, or drop the entry, in "
                "limacharlie/discovery.py."
            )


class TestCommandGroupCoverage:
    """Every registered top-level CLI group must be discoverable."""

    def test_every_registered_group_appears_in_a_profile(self):
        from limacharlie.cli import _COMMAND_MODULE_MAP

        profiled_groups = {
            entry.split()[0]
            for profile in PROFILES.values()
            for entry in profile["commands"]
        }
        missing = set(_COMMAND_MODULE_MAP) - profiled_groups

        if missing:
            pytest.fail(
                "registered command groups that no discovery profile lists:\n\n"
                + "\n".join(f"    {name}" for name in sorted(missing))
                + "\n\n  Add at least one runnable command from each group to "
                "the appropriate profile in limacharlie/discovery.py."
            )


class TestMailsecCoverage:
    """Pin ``mailsec`` command coverage in PROFILES.

    ``limacharlie help discover`` is how an operator (or an agent) finds
    out a command exists at all, so a verb that never appears in any
    profile is effectively invisible. These tests fail when the mailsec
    surface and the discovery map drift apart in either direction.
    """

    @staticmethod
    def _mailsec_paths() -> set[str]:
        from limacharlie.commands.mailsec import group as mailsec_group

        return set(_leaf_paths(mailsec_group, ["mailsec"]))

    @staticmethod
    def _profiled_paths() -> set[str]:
        return {
            cmd
            for profile in PROFILES.values()
            for cmd in profile["commands"]
            if cmd.split()[0] == "mailsec"
        }

    def test_every_mailsec_command_is_discoverable(self):
        """A new mailsec verb must be added to a discovery profile."""
        missing = self._mailsec_paths() - self._profiled_paths()
        if missing:
            pytest.fail(
                "mailsec commands that no discovery profile lists, so "
                "'limacharlie help discover' cannot surface them:\n\n"
                + "\n".join(f'    "{cmd}",' for cmd in sorted(missing))
                + "\n\n  Add them to the 'email_security' profile in "
                "limacharlie/discovery.py."
            )

    def test_no_stale_mailsec_entries(self):
        """A profile must not advertise a mailsec verb that no longer exists."""
        stale = self._profiled_paths() - self._mailsec_paths()
        assert not stale, (
            f"Discovery profiles list mailsec commands that do not exist: "
            f"{sorted(stale)}. Remove or rename them in limacharlie/discovery.py."
        )


class TestCloudSecCoverage:
    """Pin ``cloudsec`` command coverage in PROFILES.

    The Cloud Security surface is the one that grows fastest — the code
    lane, the container-image inventory and compliance v2 all arrived
    after the group did — and twice a verb has shipped without ever
    reaching a discovery profile, which makes it invisible to
    ``limacharlie help discover`` and so to any agent finding the CLI by
    that route. These tests fail when the cloudsec surface and the
    discovery map drift apart in either direction.
    """

    @staticmethod
    def _cloudsec_paths() -> set[str]:
        from limacharlie.commands.cloudsec import group as cloudsec_group

        return set(_leaf_paths(cloudsec_group, ["cloudsec"]))

    @staticmethod
    def _profiled_paths() -> set[str]:
        return {
            cmd
            for profile in PROFILES.values()
            for cmd in profile["commands"]
            if cmd.split()[0] == "cloudsec"
        }

    def test_every_cloudsec_command_is_discoverable(self):
        """A new cloudsec verb must be added to a discovery profile."""
        missing = self._cloudsec_paths() - self._profiled_paths()
        if missing:
            pytest.fail(
                "cloudsec commands that no discovery profile lists, so "
                "'limacharlie help discover' cannot surface them:\n\n"
                + "\n".join(f'    "{cmd}",' for cmd in sorted(missing))
                + "\n\n  Add them to the 'cloud_security' profile in "
                "limacharlie/discovery.py."
            )

    def test_no_stale_cloudsec_entries(self):
        """A profile must not advertise a cloudsec verb that no longer exists."""
        stale = self._profiled_paths() - self._cloudsec_paths()
        assert not stale, (
            f"Discovery profiles list cloudsec commands that do not exist: "
            f"{sorted(stale)}. Remove or rename them in limacharlie/discovery.py."
        )


class TestExplainRegistry:
    def test_register_and_get(self):
        register_explain("test.command", "This is a test command explanation.")
        text = get_explain("test.command")
        assert text == "This is a test command explanation."

    def test_get_unknown(self):
        assert get_explain("nonexistent.command") is None


class TestFormatDiscovery:
    def test_all_profiles(self):
        output = format_discovery()
        assert "sensor_management" in output
        assert "detection_engineering" in output
        assert "Command Discovery" in output

    def test_specific_profile(self):
        output = format_discovery("sensor_management")
        assert "sensor list" in output
        assert "sensor_management" in output

    def test_unknown_profile(self):
        output = format_discovery("nonexistent")
        assert "Unknown profile" in output
