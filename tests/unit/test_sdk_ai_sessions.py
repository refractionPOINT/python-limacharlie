"""Tests for AI.start_session in limacharlie.sdk.ai."""

import json
from unittest.mock import MagicMock, patch, call

import pytest

from limacharlie.sdk.ai import AI, _AI_SESSIONS_URL


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_org():
    org = MagicMock()
    org.oid = "test-oid"
    org.client = MagicMock()
    org.client._api_key = "test-api-key"
    org.client._oid = "test-oid"
    return org


@pytest.fixture
def ai(mock_org):
    return AI(mock_org)


def _make_hive_record(data):
    """Return a mock HiveRecord with the given data dict."""
    record = MagicMock()
    record.data = data
    return record


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestStartSessionBasic:
    """Minimal definition with inline credentials (no hive://secret/ refs)."""

    def test_sends_correct_request(self, ai, mock_org):
        defn = {
            "prompt": "Analyze this event",
            "anthropic_secret": "sk-ant-literal",
            "lc_api_key_secret": "lc-key-literal",
            "model": "claude-sonnet-4-6",
            "max_turns": 10,
        }

        with patch("limacharlie.sdk.hive.Hive") as MockHive:
            hive_instance = MagicMock()
            MockHive.return_value = hive_instance
            hive_instance.get.return_value = _make_hive_record(defn)
            mock_org.client.request.return_value = {
                "session_id": "sess-123",
                "status": "pending",
            }

            result = ai.start_session("my-agent")

        # Verify hive was queried for the ai_agent record.
        MockHive.assert_called_with(mock_org, "ai_agent")
        hive_instance.get.assert_called_with("my-agent")

        # Verify the POST call.
        call_args = mock_org.client.request.call_args
        assert call_args[0] == ("POST", "v1/api/sessions")
        assert call_args[1]["content_type"] == "application/json"
        assert call_args[1]["is_no_auth"] is True
        assert call_args[1]["alt_root"] == _AI_SESSIONS_URL
        assert call_args[1]["extra_headers"]["Authorization"] == "Bearer test-api-key"
        assert call_args[1]["extra_headers"]["X-LC-OID"] == "test-oid"

        body = json.loads(call_args[1]["raw_body"])
        assert body["prompt"] == "Analyze this event"
        assert body["anthropic_key"] == "sk-ant-literal"
        assert body["lc_api_key"] == "lc-key-literal"
        assert body["trigger_source"] == "cli"
        assert body["profile"]["model"] == "claude-sonnet-4-6"
        assert body["profile"]["max_turns"] == 10

        assert result == {"session_id": "sess-123", "status": "pending"}


class TestStartSessionSecretResolution:
    """Credentials that use hive://secret/ references get resolved."""

    def test_resolves_secrets(self, ai, mock_org):
        defn = {
            "prompt": "investigate",
            "anthropic_secret": "hive://secret/anthropic-key",
            "lc_api_key_secret": "hive://secret/lc-key",
            "lc_uid_secret": "hive://secret/lc-uid",
        }

        with patch("limacharlie.sdk.hive.Hive") as MockHive:
            hive_instance = MagicMock()
            MockHive.return_value = hive_instance

            def get_side_effect(name):
                records = {
                    "my-agent": _make_hive_record(defn),
                    "anthropic-key": _make_hive_record({"secret": "sk-resolved"}),
                    "lc-key": _make_hive_record({"secret": "lc-resolved"}),
                    "lc-uid": _make_hive_record({"secret": "uid-resolved"}),
                }
                return records[name]

            hive_instance.get.side_effect = get_side_effect
            mock_org.client.request.return_value = {"session_id": "s1"}

            ai.start_session("my-agent")

        body = json.loads(mock_org.client.request.call_args[1]["raw_body"])
        assert body["anthropic_key"] == "sk-resolved"
        assert body["lc_api_key"] == "lc-resolved"
        assert body["lc_uid"] == "uid-resolved"


class TestStartSessionLcApiKeyFallback:
    """When lc_api_key_secret is not in the definition, falls back to client key."""

    def test_uses_client_api_key(self, ai, mock_org):
        defn = {
            "prompt": "analyze",
            "anthropic_secret": "sk-ant",
        }

        with patch("limacharlie.sdk.hive.Hive") as MockHive:
            hive_instance = MagicMock()
            MockHive.return_value = hive_instance
            hive_instance.get.return_value = _make_hive_record(defn)
            mock_org.client.request.return_value = {"session_id": "s1"}

            ai.start_session("agent")

        body = json.loads(mock_org.client.request.call_args[1]["raw_body"])
        assert body["lc_api_key"] == "test-api-key"


class TestStartSessionOverrides:
    """Prompt and name can be overridden from CLI parameters."""

    def test_overrides_prompt_and_name(self, ai, mock_org):
        defn = {
            "prompt": "original prompt",
            "name": "original name",
            "anthropic_secret": "sk-ant",
            "lc_api_key_secret": "lc-key",
        }

        with patch("limacharlie.sdk.hive.Hive") as MockHive:
            hive_instance = MagicMock()
            MockHive.return_value = hive_instance
            hive_instance.get.return_value = _make_hive_record(defn)
            mock_org.client.request.return_value = {"session_id": "s1"}

            ai.start_session("agent", prompt="override prompt",
                             name="override name", idempotent_key="dedup-1")

        body = json.loads(mock_org.client.request.call_args[1]["raw_body"])
        assert body["prompt"] == "override prompt"
        assert body["name"] == "override name"
        assert body["idempotent_key"] == "dedup-1"


class TestStartSessionData:
    """Data dict is appended to prompt as JSON."""

    def test_appends_data_to_prompt(self, ai, mock_org):
        defn = {
            "prompt": "Investigate the alert",
            "anthropic_secret": "sk-ant",
            "lc_api_key_secret": "lc-key",
        }

        with patch("limacharlie.sdk.hive.Hive") as MockHive:
            hive_instance = MagicMock()
            MockHive.return_value = hive_instance
            hive_instance.get.return_value = _make_hive_record(defn)
            mock_org.client.request.return_value = {"session_id": "s1"}

            ai.start_session("agent", data={"hostname": "srv-01", "alert_id": "abc-123"})

        body = json.loads(mock_org.client.request.call_args[1]["raw_body"])
        assert body["prompt"].startswith("Investigate the alert\n\nEvent data:\n```json\n")
        assert body["prompt"].endswith("\n```")
        embedded = json.loads(body["prompt"].split("```json\n", 1)[1].rsplit("\n```", 1)[0])
        assert embedded == {"hostname": "srv-01", "alert_id": "abc-123"}

    def test_no_data_leaves_prompt_unchanged(self, ai, mock_org):
        defn = {
            "prompt": "Investigate the alert",
            "anthropic_secret": "sk-ant",
            "lc_api_key_secret": "lc-key",
        }

        with patch("limacharlie.sdk.hive.Hive") as MockHive:
            hive_instance = MagicMock()
            MockHive.return_value = hive_instance
            hive_instance.get.return_value = _make_hive_record(defn)
            mock_org.client.request.return_value = {"session_id": "s1"}

            ai.start_session("agent")

        body = json.loads(mock_org.client.request.call_args[1]["raw_body"])
        assert body["prompt"] == "Investigate the alert"


class TestStartSessionMCPServers:
    """MCP server configs have their secrets resolved."""

    def test_resolves_mcp_server_secrets(self, ai, mock_org):
        defn = {
            "prompt": "do things",
            "anthropic_secret": "sk-ant",
            "lc_api_key_secret": "lc-key",
            "mcp_servers": {
                "github": {
                    "type": "http",
                    "url": "https://api.github.com",
                    "headers": {
                        "Authorization": "hive://secret/gh-token",
                        "Accept": "application/json",
                    },
                },
                "local": {
                    "type": "stdio",
                    "command": "/usr/bin/tool",
                    "env": {
                        "API_KEY": "hive://secret/tool-key",
                        "DEBUG": "false",
                    },
                },
            },
        }

        with patch("limacharlie.sdk.hive.Hive") as MockHive:
            hive_instance = MagicMock()
            MockHive.return_value = hive_instance

            def get_side_effect(name):
                records = {
                    "agent": _make_hive_record(defn),
                    "gh-token": _make_hive_record({"secret": "ghp_resolved"}),
                    "tool-key": _make_hive_record({"secret": "tool-resolved"}),
                }
                return records[name]

            hive_instance.get.side_effect = get_side_effect
            mock_org.client.request.return_value = {"session_id": "s1"}

            ai.start_session("agent")

        body = json.loads(mock_org.client.request.call_args[1]["raw_body"])
        mcp = body["profile"]["mcp_servers"]
        assert mcp["github"]["headers"]["Authorization"] == "ghp_resolved"
        assert mcp["github"]["headers"]["Accept"] == "application/json"
        assert mcp["local"]["env"]["API_KEY"] == "tool-resolved"
        assert mcp["local"]["env"]["DEBUG"] == "false"


class TestStartSessionEnvironmentSecrets:
    """Environment map values with hive://secret/ are resolved."""

    def test_resolves_environment_secrets(self, ai, mock_org):
        defn = {
            "prompt": "go",
            "anthropic_secret": "sk-ant",
            "lc_api_key_secret": "lc-key",
            "environment": {
                "EXTERNAL_KEY": "hive://secret/ext-key",
                "PLAIN": "plain-value",
            },
        }

        with patch("limacharlie.sdk.hive.Hive") as MockHive:
            hive_instance = MagicMock()
            MockHive.return_value = hive_instance

            def get_side_effect(name):
                records = {
                    "agent": _make_hive_record(defn),
                    "ext-key": _make_hive_record({"secret": "ext-resolved"}),
                }
                return records[name]

            hive_instance.get.side_effect = get_side_effect
            mock_org.client.request.return_value = {"session_id": "s1"}

            ai.start_session("agent")

        body = json.loads(mock_org.client.request.call_args[1]["raw_body"])
        assert body["profile"]["environment"]["EXTERNAL_KEY"] == "ext-resolved"
        assert body["profile"]["environment"]["PLAIN"] == "plain-value"
