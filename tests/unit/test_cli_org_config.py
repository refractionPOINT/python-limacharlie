"""CLI tests for 'org config-get' and 'org config-set'.

The commands pass the configuration name straight to the API, which is the
authority on which names exist.  The help text has to name the ones the API
accepts, and only those.
"""

from __future__ import annotations

import re
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner

# Command modules are lazy-loaded; importing this one registers its explain
# text, which get_explain() below reads.
import limacharlie.commands.org  # noqa: F401
from limacharlie.cli import cli
from limacharlie.discovery import get_explain

# The names the API accepts, matched exactly.
_CONFIG_NAMES = [
    "vt", "otx", "domain", "shodan", "pagerduty", "twilio", "socprime",
    "alphamountain", "pangea", "echotrail", "hybrid_analysis", "greynoise",
    "ipqs", "sensor_auto_upgrade", "retention_months",
]

# Names earlier help text advertised and the API rejects as unknown.
_REJECTED_NAMES = ["retention", "sensor_version", "twilio_", "otx_key"]


def _has_name(text: str, name: str) -> bool:
    return re.search(rf"(?<![\w.]){re.escape(name)}(?![\w.])", text) is not None


@pytest.fixture
def org():
    with patch("limacharlie.commands.org.Client"), \
         patch("limacharlie.commands.org.Organization") as org_cls:
        mock_org = MagicMock()
        org_cls.return_value = mock_org
        yield mock_org


class TestConfigSetHelp:
    @pytest.mark.parametrize("name", _CONFIG_NAMES)
    def test_lists_every_accepted_name(self, name):
        assert _has_name(get_explain("org.config-set"), name)

    @pytest.mark.parametrize("name", _REJECTED_NAMES)
    @pytest.mark.parametrize("command", ["org.config-get", "org.config-set"])
    def test_does_not_list_rejected_names(self, command, name):
        assert not _has_name(get_explain(command), name)

    def test_documents_sensor_auto_upgrade(self):
        text = get_explain("org.config-set")
        assert "module.update" in text
        assert "org.conf.set" in text
        assert "limacharlie org config-set --name sensor_auto_upgrade --value true" in text

    def test_ai_help_shows_the_names(self):
        result = CliRunner().invoke(cli, ["org", "config-set", "--ai-help"])
        assert result.exit_code == 0, result.output
        assert "sensor_auto_upgrade" in result.output
        assert "hybrid_analysis" in result.output


class TestConfigPassThrough:
    def test_set_sends_name_and_value_as_given(self, org):
        org.set_config.return_value = {}
        result = CliRunner().invoke(
            cli, ["org", "config-set", "--name", "sensor_auto_upgrade", "--value", "true"])
        assert result.exit_code == 0, result.output
        org.set_config.assert_called_once_with("sensor_auto_upgrade", "true")

    def test_set_does_not_validate_the_name_client_side(self, org):
        # The server owns the list of names; a name this CLI has never heard
        # of must still reach it.
        org.set_config.return_value = {}
        result = CliRunner().invoke(
            cli, ["org", "config-set", "--name", "some_future_name", "--value", "x"])
        assert result.exit_code == 0, result.output
        org.set_config.assert_called_once_with("some_future_name", "x")

    def test_get_sends_name_as_given(self, org):
        org.get_config.return_value = "true"
        result = CliRunner().invoke(
            cli, ["org", "config-get", "--name", "sensor_auto_upgrade"])
        assert result.exit_code == 0, result.output
        org.get_config.assert_called_once_with("sensor_auto_upgrade")
