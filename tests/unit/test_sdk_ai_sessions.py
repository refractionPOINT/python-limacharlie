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
        assert body["prompt"].startswith("Investigate the alert\n\nEvent data:\n```yaml\n")
        assert body["prompt"].endswith("\n```")
        import yaml
        embedded = yaml.safe_load(body["prompt"].split("```yaml\n", 1)[1].rsplit("\n```", 1)[0])
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


# ---------------------------------------------------------------------------
# Profile field overrides (template-on-top-of-hive-record semantics)
# ---------------------------------------------------------------------------

def _minimal_defn(**extra):
    """A hive record with just enough to pass validation."""
    base = {
        "prompt": "template prompt",
        "anthropic_secret": "sk-template",
        "lc_api_key_secret": "lc-template",
    }
    base.update(extra)
    return base


def _run_start(ai, mock_org, defn, extra_records=None, **kwargs):
    """Run start_session with a stubbed hive and return the posted body."""
    records = {"agent": _make_hive_record(defn)}
    if extra_records:
        for name, data in extra_records.items():
            records[name] = _make_hive_record(data)

    with patch("limacharlie.sdk.hive.Hive") as MockHive:
        hive_instance = MagicMock()
        MockHive.return_value = hive_instance
        hive_instance.get.side_effect = lambda n: records[n]
        mock_org.client.request.return_value = {"session_id": "s1"}
        ai.start_session("agent", **kwargs)

    return json.loads(mock_org.client.request.call_args[1]["raw_body"])


class TestStartSessionScalarOverrides:
    """Individual scalar overrides replace matching template fields."""

    def test_model_override_replaces_template(self, ai, mock_org):
        defn = _minimal_defn(model="claude-opus-4-6", max_turns=50)
        body = _run_start(ai, mock_org, defn, model="claude-sonnet-4-6")
        assert body["profile"]["model"] == "claude-sonnet-4-6"
        # max_turns stays from template.
        assert body["profile"]["max_turns"] == 50

    def test_max_budget_override(self, ai, mock_org):
        defn = _minimal_defn(max_budget_usd=10.0)
        body = _run_start(ai, mock_org, defn, max_budget_usd=2.5)
        assert body["profile"]["max_budget_usd"] == 2.5

    def test_max_turns_override(self, ai, mock_org):
        defn = _minimal_defn(max_turns=100)
        body = _run_start(ai, mock_org, defn, max_turns=5)
        assert body["profile"]["max_turns"] == 5

    def test_task_budget_tokens_override(self, ai, mock_org):
        defn = _minimal_defn()
        body = _run_start(ai, mock_org, defn, task_budget_tokens=50000)
        assert body["profile"]["task_budget_tokens"] == 50000

    def test_ttl_seconds_override(self, ai, mock_org):
        defn = _minimal_defn(ttl_seconds=3600)
        body = _run_start(ai, mock_org, defn, ttl_seconds=60)
        assert body["profile"]["ttl_seconds"] == 60

    def test_permission_mode_override(self, ai, mock_org):
        defn = _minimal_defn(permission_mode="plan")
        body = _run_start(ai, mock_org, defn, permission_mode="acceptEdits")
        assert body["profile"]["permission_mode"] == "acceptEdits"

    def test_one_shot_forced_on(self, ai, mock_org):
        defn = _minimal_defn(one_shot=False)
        body = _run_start(ai, mock_org, defn, one_shot=True)
        assert body["profile"]["one_shot"] is True

    def test_one_shot_forced_off(self, ai, mock_org):
        defn = _minimal_defn(one_shot=True)
        body = _run_start(ai, mock_org, defn, one_shot=False)
        assert body["profile"]["one_shot"] is False

    def test_none_overrides_keep_template(self, ai, mock_org):
        """Passing no overrides leaves every template field intact."""
        defn = _minimal_defn(
            model="claude-opus-4-6",
            max_turns=10,
            max_budget_usd=5.0,
            permission_mode="plan",
            one_shot=True,
            ttl_seconds=120,
        )
        body = _run_start(ai, mock_org, defn)
        p = body["profile"]
        assert p["model"] == "claude-opus-4-6"
        assert p["max_turns"] == 10
        assert p["max_budget_usd"] == 5.0
        assert p["permission_mode"] == "plan"
        assert p["one_shot"] is True
        assert p["ttl_seconds"] == 120


class TestStartSessionListOverrides:
    """List fields replace (not merge) when overridden."""

    def test_allowed_tools_replaces(self, ai, mock_org):
        defn = _minimal_defn(allowed_tools=["Read", "Grep", "Bash", "Write"])
        body = _run_start(ai, mock_org, defn, allowed_tools=["Read"])
        assert body["profile"]["allowed_tools"] == ["Read"]

    def test_denied_tools_replaces(self, ai, mock_org):
        defn = _minimal_defn(denied_tools=["Bash"])
        body = _run_start(ai, mock_org, defn, denied_tools=["Bash", "Write"])
        assert body["profile"]["denied_tools"] == ["Bash", "Write"]

    def test_plugins_replaces(self, ai, mock_org):
        defn = _minimal_defn(plugins=["lc-essentials"])
        body = _run_start(ai, mock_org, defn,
                          plugins=["lc-essentials", "lc-advanced-skills"])
        assert body["profile"]["plugins"] == ["lc-essentials", "lc-advanced-skills"]

    def test_empty_list_override_replaces_with_empty(self, ai, mock_org):
        """Passing [] is distinct from not passing anything.

        An explicit empty list means "clear the template value"; None
        means "keep it".  This matches the CLI semantic where the flag
        defaults to None until the user supplies it.
        """
        defn = _minimal_defn(allowed_tools=["Read", "Bash"])
        body = _run_start(ai, mock_org, defn, allowed_tools=[])
        assert body["profile"]["allowed_tools"] == []


class TestStartSessionEnvironmentOverride:
    """Environment MERGES template + overrides, override wins on collisions."""

    def test_env_override_adds_new_keys(self, ai, mock_org):
        defn = _minimal_defn(environment={"BASE": "base-value"})
        body = _run_start(ai, mock_org, defn,
                          environment={"EXTRA": "extra-value"})
        env = body["profile"]["environment"]
        assert env["BASE"] == "base-value"
        assert env["EXTRA"] == "extra-value"

    def test_env_override_wins_on_collision(self, ai, mock_org):
        defn = _minimal_defn(environment={"SHARED": "from-template"})
        body = _run_start(ai, mock_org, defn,
                          environment={"SHARED": "from-cli"})
        assert body["profile"]["environment"]["SHARED"] == "from-cli"

    def test_env_override_secrets_resolve(self, ai, mock_org):
        defn = _minimal_defn(environment={"TEMPLATE_SECRET": "hive://secret/t-key"})
        body = _run_start(
            ai, mock_org, defn,
            environment={"OVERRIDE_SECRET": "hive://secret/o-key"},
            extra_records={
                "t-key": {"secret": "template-resolved"},
                "o-key": {"secret": "override-resolved"},
            },
        )
        env = body["profile"]["environment"]
        assert env["TEMPLATE_SECRET"] == "template-resolved"
        assert env["OVERRIDE_SECRET"] == "override-resolved"

    def test_env_override_without_template_env(self, ai, mock_org):
        defn = _minimal_defn()
        body = _run_start(ai, mock_org, defn,
                          environment={"NEW": "value"})
        assert body["profile"]["environment"] == {"NEW": "value"}


class TestStartSessionCredentialOverrides:
    """anthropic_key / lc_api_key / lc_uid overrides bypass the hive defaults."""

    def test_anthropic_key_literal_override(self, ai, mock_org):
        defn = _minimal_defn(anthropic_secret="sk-from-template")
        body = _run_start(ai, mock_org, defn, anthropic_key="sk-override")
        assert body["anthropic_key"] == "sk-override"

    def test_anthropic_key_secret_ref_override(self, ai, mock_org):
        defn = _minimal_defn(anthropic_secret="sk-from-template")
        body = _run_start(
            ai, mock_org, defn,
            anthropic_key="hive://secret/different-key",
            extra_records={"different-key": {"secret": "sk-resolved-via-override"}},
        )
        assert body["anthropic_key"] == "sk-resolved-via-override"

    def test_lc_api_key_override(self, ai, mock_org):
        defn = _minimal_defn(lc_api_key_secret="template-lc")
        body = _run_start(ai, mock_org, defn, lc_api_key="override-lc")
        assert body["lc_api_key"] == "override-lc"

    def test_lc_uid_override(self, ai, mock_org):
        defn = _minimal_defn()
        body = _run_start(ai, mock_org, defn, lc_uid="override-uid")
        assert body["lc_uid"] == "override-uid"


# ---------------------------------------------------------------------------
# CLI surface: parsing helpers and Click registration
# ---------------------------------------------------------------------------

class TestCliOverrideParsing:

    def test_split_csv_none_passthrough(self):
        from limacharlie.commands.ai import _split_csv
        assert _split_csv(None) is None

    def test_split_csv_splits_and_strips(self):
        from limacharlie.commands.ai import _split_csv
        assert _split_csv("a, b ,c,") == ["a", "b", "c"]

    def test_split_csv_empty_string_yields_empty_list(self):
        """Explicit empty value (-t '') clears the template list."""
        from limacharlie.commands.ai import _split_csv
        assert _split_csv("") == []

    def test_parse_env_kv_empty_tuple_returns_none(self):
        from limacharlie.commands.ai import _parse_env_kv
        assert _parse_env_kv(()) is None

    def test_parse_env_kv_builds_dict(self):
        from limacharlie.commands.ai import _parse_env_kv
        assert _parse_env_kv(("FOO=bar", "BAZ=qux")) == {"FOO": "bar", "BAZ": "qux"}

    def test_parse_env_kv_preserves_value_equals(self):
        """Only the first '=' splits; later ones stay in the value."""
        from limacharlie.commands.ai import _parse_env_kv
        assert _parse_env_kv(("URL=https://x?a=1",)) == {"URL": "https://x?a=1"}

    def test_parse_env_kv_rejects_bare_value(self):
        import click
        from limacharlie.commands.ai import _parse_env_kv
        with pytest.raises(click.BadParameter):
            _parse_env_kv(("no-equals-here",))

    def test_parse_env_kv_rejects_empty_key(self):
        import click
        from limacharlie.commands.ai import _parse_env_kv
        with pytest.raises(click.BadParameter):
            _parse_env_kv(("=bare",))


class TestStartSessionCliHelp:
    """The Click command exposes every override flag in --help output."""

    def test_help_lists_every_override(self):
        import click.testing
        from limacharlie.cli import cli

        runner = click.testing.CliRunner()
        result = runner.invoke(cli, ["ai", "start-session", "--help"])
        assert result.exit_code == 0, result.output
        for flag in (
            "--model", "--max-turns", "--max-budget-usd",
            "--task-budget-tokens", "--ttl-seconds", "--one-shot",
            "--permission-mode", "--allowed-tools", "--denied-tools",
            "--plugin", "--env", "--anthropic-key", "--lc-api-key", "--lc-uid",
        ):
            assert flag in result.output, f"missing flag in help: {flag}"


# ---------------------------------------------------------------------------
# User-scoped SDK methods backing `ai chat` and `ai auth claude`
# ---------------------------------------------------------------------------

class TestUserScopedRequestShape:
    """_user_request routes through client.request with JWT auth only."""

    def test_get_omits_oid_header_and_body(self, ai, mock_org):
        mock_org.client.request.return_value = {"has_credentials": False}

        result = ai.claude_auth_status()

        assert result == {"has_credentials": False}
        call_args = mock_org.client.request.call_args
        assert call_args[0] == ("GET", "v1/auth/claude/status")
        assert call_args[1]["alt_root"] == _AI_SESSIONS_URL
        # User-scoped routes must NOT send X-LC-OID and must use JWT auth
        # (is_no_auth is absent → client.request attaches the JWT).
        assert "extra_headers" not in call_args[1]
        assert "is_no_auth" not in call_args[1]
        assert "raw_body" not in call_args[1]

    def test_post_sets_content_type_and_body(self, ai, mock_org):
        mock_org.client.request.return_value = {"success": True}

        ai.claude_set_apikey("sk-ant-literal")

        call_args = mock_org.client.request.call_args
        assert call_args[0] == ("POST", "v1/auth/claude/apikey")
        assert call_args[1]["content_type"] == "application/json"
        body = json.loads(call_args[1]["raw_body"])
        assert body == {"api_key": "sk-ant-literal"}


class TestClaudeAuthSDK:

    def test_register_user_sends_empty_body(self, ai, mock_org):
        mock_org.client.request.return_value = {
            "registered": True,
            "registered_at": "2026-04-18T00:00:00Z",
        }

        result = ai.register_user()

        assert result["registered"] is True
        call_args = mock_org.client.request.call_args
        assert call_args[0] == ("POST", "v1/register")
        # Empty raw_body triggers the JSON content-type path.
        assert call_args[1]["raw_body"] == b""
        assert call_args[1]["content_type"] == "application/json"

    def test_claude_login_start(self, ai, mock_org):
        mock_org.client.request.return_value = {
            "oauth_session_id": "os-1",
            "expires_in": 300,
            "message": "Poll /auth/claude/url for the OAuth URL",
        }

        result = ai.claude_login_start()

        assert result["oauth_session_id"] == "os-1"
        call_args = mock_org.client.request.call_args
        assert call_args[0] == ("POST", "v1/auth/claude/start")

    def test_claude_login_get_url_passes_query_param(self, ai, mock_org):
        mock_org.client.request.return_value = {
            "status": "ready",
            "url": "https://claude.ai/oauth/authorize?code=...",
        }

        result = ai.claude_login_get_url("os-1")

        assert result["status"] == "ready"
        call_args = mock_org.client.request.call_args
        assert call_args[0] == ("GET", "v1/auth/claude/url")
        assert call_args[1]["query_params"] == {"session_id": "os-1"}

    def test_claude_login_submit_code_body(self, ai, mock_org):
        mock_org.client.request.return_value = {
            "success": True,
            "status": "completed",
        }

        ai.claude_login_submit_code("os-1", "code-abc")

        body = json.loads(mock_org.client.request.call_args[1]["raw_body"])
        assert body == {"session_id": "os-1", "code": "code-abc"}

    def test_claude_set_apikey_resolves_hive_secret(self, ai, mock_org):
        """A hive://secret/<name> API key is resolved before sending."""
        mock_org.client.request.return_value = {"success": True}

        with patch("limacharlie.sdk.hive.Hive") as MockHive:
            hive_instance = MagicMock()
            MockHive.return_value = hive_instance
            hive_instance.get.return_value = _make_hive_record(
                {"secret": "sk-ant-resolved"},
            )

            ai.claude_set_apikey("hive://secret/anthropic")

            MockHive.assert_called_with(mock_org, "secret")
            hive_instance.get.assert_called_with("anthropic")

        body = json.loads(mock_org.client.request.call_args[1]["raw_body"])
        assert body == {"api_key": "sk-ant-resolved"}

    def test_claude_logout_deletes(self, ai, mock_org):
        mock_org.client.request.return_value = {"success": True}

        ai.claude_logout()

        assert mock_org.client.request.call_args[0] == (
            "DELETE", "v1/auth/claude",
        )


class TestCreateUserSession:

    def test_omits_fields_when_none(self, ai, mock_org):
        """Unset kwargs must not appear in the POST body at all, so the
        server applies its own defaults."""
        mock_org.client.request.return_value = {
            "id": "sess-user-1",
            "status": "starting",
        }

        ai.create_user_session()

        call_args = mock_org.client.request.call_args
        assert call_args[0] == ("POST", "v1/sessions")
        body = json.loads(call_args[1]["raw_body"])
        assert body == {}

    def test_sends_all_supplied_overrides(self, ai, mock_org):
        mock_org.client.request.return_value = {"id": "sess-1"}

        ai.create_user_session(
            name="chat test",
            idempotent_key="key-1",
            model="claude-sonnet-4-6",
            max_turns=10,
            max_budget_usd=0.5,
            task_budget_tokens=5000,
            one_shot=False,
            permission_mode="acceptEdits",
            allowed_tools=["Read", "Grep"],
            denied_tools=["Bash"],
            plugins=["lc-essentials"],
        )

        body = json.loads(mock_org.client.request.call_args[1]["raw_body"])
        assert body == {
            "name": "chat test",
            "idempotent_key": "key-1",
            "model": "claude-sonnet-4-6",
            "max_turns": 10,
            "max_budget_usd": 0.5,
            "task_budget_tokens": 5000,
            "one_shot": False,
            "permission_mode": "acceptEdits",
            "allowed_tools": ["Read", "Grep"],
            "denied_tools": ["Bash"],
            "plugins": ["lc-essentials"],
        }


# ---------------------------------------------------------------------------
# CLI: `ai auth claude` and `ai chat`
# ---------------------------------------------------------------------------

class TestAuthClaudeCommands:
    """CLI surface around Claude credential management."""

    def test_status_calls_sdk(self):
        import click.testing
        from limacharlie.cli import cli

        runner = click.testing.CliRunner()
        with patch("limacharlie.commands.ai._get_org") as mock_get_org, \
             patch("limacharlie.commands.ai.AISDK") as MockSDK:
            mock_get_org.return_value = MagicMock()
            sdk = MockSDK.return_value
            sdk.claude_auth_status.return_value = {"has_credentials": False}

            result = runner.invoke(
                cli, ["--output", "json", "ai", "auth", "claude", "status"],
            )
            assert result.exit_code == 0, result.output
            sdk.claude_auth_status.assert_called_once_with()

    def test_set_key_rejects_both_sources(self):
        import click.testing
        from limacharlie.cli import cli

        runner = click.testing.CliRunner()
        with patch("limacharlie.commands.ai._get_org") as mock_get_org, \
             patch("limacharlie.commands.ai.AISDK") as MockSDK:
            mock_get_org.return_value = MagicMock()
            MockSDK.return_value = MagicMock()

            result = runner.invoke(cli, [
                "ai", "auth", "claude", "set-key",
                "--key", "sk-literal", "--key-from-stdin",
            ])
            # Mutually exclusive flags must fail fast with a usage error.
            assert result.exit_code != 0
            assert "mutually exclusive" in result.output.lower()

    def test_set_key_requires_one_source(self):
        import click.testing
        from limacharlie.cli import cli

        runner = click.testing.CliRunner()
        with patch("limacharlie.commands.ai._get_org") as mock_get_org, \
             patch("limacharlie.commands.ai.AISDK") as MockSDK:
            mock_get_org.return_value = MagicMock()
            MockSDK.return_value = MagicMock()

            result = runner.invoke(cli, ["ai", "auth", "claude", "set-key"])
            assert result.exit_code != 0
            assert "required" in result.output.lower()

    def test_set_key_reads_stdin(self):
        import click.testing
        from limacharlie.cli import cli

        runner = click.testing.CliRunner()
        with patch("limacharlie.commands.ai._get_org") as mock_get_org, \
             patch("limacharlie.commands.ai.AISDK") as MockSDK:
            mock_get_org.return_value = MagicMock()
            sdk = MockSDK.return_value
            sdk.claude_set_apikey.return_value = {"success": True}

            result = runner.invoke(
                cli,
                ["--output", "json", "ai", "auth", "claude", "set-key",
                 "--key-from-stdin"],
                input="sk-ant-piped\n",
            )
            assert result.exit_code == 0, result.output
            sdk.claude_set_apikey.assert_called_once_with("sk-ant-piped")

    def test_logout_calls_sdk(self):
        import click.testing
        from limacharlie.cli import cli

        runner = click.testing.CliRunner()
        with patch("limacharlie.commands.ai._get_org") as mock_get_org, \
             patch("limacharlie.commands.ai.AISDK") as MockSDK:
            mock_get_org.return_value = MagicMock()
            sdk = MockSDK.return_value
            sdk.claude_logout.return_value = {"success": True}

            result = runner.invoke(
                cli, ["--output", "json", "ai", "auth", "claude", "logout"],
            )
            assert result.exit_code == 0, result.output
            sdk.claude_logout.assert_called_once_with()


class TestChatCommand:
    """CLI surface around the interactive chat command."""

    def test_fails_fast_when_no_claude_credentials(self):
        import click.testing
        from limacharlie.cli import cli

        runner = click.testing.CliRunner()
        with patch("limacharlie.commands.ai._get_org") as mock_get_org, \
             patch("limacharlie.commands.ai.AISDK") as MockSDK:
            mock_get_org.return_value = MagicMock()
            sdk = MockSDK.return_value
            sdk.claude_auth_status.return_value = {"has_credentials": False}

            result = runner.invoke(cli, ["ai", "chat", "hello"])

            assert result.exit_code != 0
            assert "No Claude credentials" in result.output
            # Must not attempt to create a session if creds missing.
            sdk.create_user_session.assert_not_called()
            sdk.register_user.assert_not_called()

    def test_happy_path_creates_and_attaches(self):
        import click.testing
        from limacharlie.cli import cli

        runner = click.testing.CliRunner()
        with patch("limacharlie.commands.ai._get_org") as mock_get_org, \
             patch("limacharlie.commands.ai.AISDK") as MockSDK, \
             patch("limacharlie.commands.ai._split_csv", side_effect=lambda v: None if v is None else v.split(",")), \
             patch("limacharlie.commands._ai_attach.run_attach", return_value=0) as mock_run:
            mock_get_org.return_value = MagicMock()
            sdk = MockSDK.return_value
            sdk.claude_auth_status.return_value = {
                "has_credentials": True, "credential_type": "apikey",
            }
            sdk.register_user.return_value = {"registered": True}
            sdk.create_user_session.return_value = {
                "id": "sess-user-9", "status": "starting",
            }

            result = runner.invoke(cli, [
                "ai", "chat", "hello there",
                "--model", "claude-sonnet-4-6",
                "--max-budget-usd", "0.10",
            ])

            assert result.exit_code == 0, result.output
            sdk.register_user.assert_called_once_with()
            # Overrides propagate as kwargs to create_user_session.
            create_kwargs = sdk.create_user_session.call_args.kwargs
            assert create_kwargs["model"] == "claude-sonnet-4-6"
            assert create_kwargs["max_budget_usd"] == 0.10
            # run_attach called with the created session id, interactive
            # mode on, initial_prompt from the CLI arg.
            mock_run.assert_called_once()
            kwargs = mock_run.call_args.kwargs
            assert mock_run.call_args.args[1] == "sess-user-9"
            assert kwargs["interactive"] is True
            assert kwargs["read_only"] is False
            assert kwargs["initial_prompt"] == "hello there"

    def test_help_lists_flags(self):
        import click.testing
        from limacharlie.cli import cli

        runner = click.testing.CliRunner()
        result = runner.invoke(cli, ["ai", "chat", "--help"])
        assert result.exit_code == 0, result.output
        for flag in (
            "--name", "--model", "--max-turns", "--max-budget-usd",
            "--task-budget-tokens", "--permission-mode",
            "--allowed-tools", "--denied-tools", "--plugin",
            "--idempotent-key",
        ):
            assert flag in result.output, f"missing flag in chat --help: {flag}"
