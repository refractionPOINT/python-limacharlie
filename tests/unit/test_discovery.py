"""Tests for limacharlie.discovery module."""

import click
import pytest

from limacharlie.discovery import (
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
            "sensor_management", "detection_engineering", "historical_data",
            "live_investigation", "threat_response", "fleet_management",
            "platform_admin", "ai_powered", "cases", "email_security",
        ]
        for name in expected:
            assert name in PROFILES, f"Missing profile: {name}"

    def test_each_profile_has_description_and_commands(self):
        for name, profile in PROFILES.items():
            assert "description" in profile, f"Profile {name} missing description"
            assert "commands" in profile, f"Profile {name} missing commands"
            assert len(profile["commands"]) > 0, f"Profile {name} has no commands"

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


def _leaf_paths(cmd: click.BaseCommand, prefix: list[str]) -> list[str]:
    """Every runnable command path under ``cmd``, space-joined."""
    if isinstance(cmd, click.Group):
        paths = []
        for name, sub in cmd.commands.items():
            paths.extend(_leaf_paths(sub, prefix + [name]))
        return paths
    return [" ".join(prefix)]


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
