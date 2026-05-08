"""Tests for limacharlie.discovery module."""

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
            "platform_admin", "ai_powered",
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
