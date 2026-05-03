"""CLI tests for the ai-skill and ai-memory shortcut groups.

The ai-memory tests are the important ones: they pin down that the CLI
sends a partial-merge payload (``{memories: {name: content}}`` for set,
``{memories: {name: null}}`` for delete) rather than rewriting the
whole record. Other memory entries on the server stay put.
"""

from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

from click.testing import CliRunner

from limacharlie.cli import cli


# ---------------------------------------------------------------------------
# ai-skill (delegates to the generic _hive_shortcut factory)
# ---------------------------------------------------------------------------

class TestAiSkillCli:
    @patch("limacharlie.commands._hive_shortcut.Client")
    @patch("limacharlie.commands._hive_shortcut.Organization")
    @patch("limacharlie.commands._hive_shortcut.Hive")
    def test_list_calls_ai_skill_hive(self, mock_hive_cls, _org, _client):
        mock_record = MagicMock()
        mock_record.to_dict.return_value = {"data": {"content": "..."}, "usr_mtd": {}, "sys_mtd": {}}
        mock_hive = MagicMock()
        mock_hive.list.return_value = {"my-skill": mock_record}
        mock_hive_cls.return_value = mock_hive

        result = CliRunner().invoke(cli, ["--output", "json", "ai-skill", "list"])
        assert result.exit_code == 0, result.output
        # The shortcut must target the ai_skill hive name.
        assert mock_hive_cls.call_args[0][1] == "ai_skill"
        parsed = json.loads(result.output)
        assert "my-skill" in parsed

    @patch("limacharlie.commands._hive_shortcut.Client")
    @patch("limacharlie.commands._hive_shortcut.Organization")
    @patch("limacharlie.commands._hive_shortcut.Hive")
    def test_set_passes_record_data_through(self, mock_hive_cls, _org, _client):
        mock_hive = MagicMock()
        mock_hive.set.return_value = {"etag": "e2"}
        mock_hive_cls.return_value = mock_hive

        payload = {"data": {"content": "skill body", "effort": "high"}}
        result = CliRunner().invoke(
            cli, ["ai-skill", "set", "--key", "triage"],
            input=json.dumps(payload),
        )
        assert result.exit_code == 0, result.output
        assert mock_hive_cls.call_args[0][1] == "ai_skill"
        record = mock_hive.set.call_args[0][0]
        assert record.name == "triage"
        assert record.data == {"content": "skill body", "effort": "high"}

    def test_delete_requires_confirm(self):
        # No mocks needed: the confirm check fires before any API call.
        result = CliRunner().invoke(cli, ["ai-skill", "delete", "--key", "x"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# ai-memory (custom commands with partial-merge payloads)
# ---------------------------------------------------------------------------

def _post_payload(mock_client) -> dict:
    """Decode the JSON payload the CLI POSTed for the most recent set/delete."""
    # The AiMemory SDK always uses the org's client.request directly.
    args, kwargs = mock_client.request.call_args
    assert args[0] == "POST", f"expected POST, got {args[0]}"
    return json.loads(kwargs["params"]["data"])


def _last_post_url(mock_client) -> str:
    args, _ = mock_client.request.call_args
    return args[1]


class TestAiMemorySetCli:
    """A set on one memory_name must send only that one entry."""

    @patch("limacharlie.commands.ai_memory.Client")
    @patch("limacharlie.commands.ai_memory.Organization")
    def test_set_with_content_flag(self, mock_org_cls, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_org = MagicMock()
        mock_org.oid = "test-oid"
        mock_org.client = mock_client
        mock_org_cls.return_value = mock_org

        result = CliRunner().invoke(cli, [
            "ai-memory", "set",
            "--key", "agent-A",
            "--memory-name", "notes/today",
            "--content", "wrote the cli wrapper",
        ])
        assert result.exit_code == 0, result.output

        payload = _post_payload(mock_client)
        # Critical: only the named memory is in the payload. The rest of
        # the record (other memory names) must be preserved server-side
        # by the partial-merge hook, not sent down the wire by the CLI.
        assert payload == {
            "memories": {"notes/today": "wrote the cli wrapper"}
        }
        assert "/agent-A/data" in _last_post_url(mock_client)

    @patch("limacharlie.commands.ai_memory.Client")
    @patch("limacharlie.commands.ai_memory.Organization")
    def test_set_with_stdin(self, mock_org_cls, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_org = MagicMock()
        mock_org.oid = "test-oid"
        mock_org.client = mock_client
        mock_org_cls.return_value = mock_org

        result = CliRunner().invoke(
            cli, ["ai-memory", "set", "--key", "agent-A", "--memory-name", "k"],
            input="multi\nline\ncontent\n",
        )
        assert result.exit_code == 0, result.output

        payload = _post_payload(mock_client)
        assert payload == {"memories": {"k": "multi\nline\ncontent\n"}}

    @patch("limacharlie.commands.ai_memory.Client")
    @patch("limacharlie.commands.ai_memory.Organization")
    def test_set_does_not_get_first(self, mock_org_cls, mock_client_cls):
        """Critical: the CLI must trust the merge hook, not round-trip
        through GET to fetch the existing record."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_org = MagicMock()
        mock_org.oid = "test-oid"
        mock_org.client = mock_client
        mock_org_cls.return_value = mock_org

        result = CliRunner().invoke(cli, [
            "ai-memory", "set",
            "--key", "agent-A", "--memory-name", "k", "--content", "v",
        ])
        assert result.exit_code == 0, result.output

        # Single API call. No GET-then-PUT race window.
        assert mock_client.request.call_count == 1

    def test_set_requires_memory_name(self):
        result = CliRunner().invoke(cli, [
            "ai-memory", "set", "--key", "agent-A", "--content", "v",
        ])
        # Click reports missing required option as exit code 2.
        assert result.exit_code != 0
        assert "memory-name" in result.output.lower()


class TestAiMemoryDeleteCli:
    @patch("limacharlie.commands.ai_memory.Client")
    @patch("limacharlie.commands.ai_memory.Organization")
    def test_delete_sends_null_for_named_memory(self, mock_org_cls, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_org = MagicMock()
        mock_org.oid = "test-oid"
        mock_org.client = mock_client
        mock_org_cls.return_value = mock_org

        result = CliRunner().invoke(cli, [
            "ai-memory", "delete",
            "--key", "agent-A", "--memory-name", "notes/today",
            "--confirm",
        ])
        assert result.exit_code == 0, result.output

        payload = _post_payload(mock_client)
        # Server-side hook drops the entry on a JSON-null value.
        assert payload == {"memories": {"notes/today": None}}

    def test_delete_requires_confirm(self):
        result = CliRunner().invoke(cli, [
            "ai-memory", "delete",
            "--key", "agent-A", "--memory-name", "k",
        ])
        assert result.exit_code != 0

    @patch("limacharlie.commands.ai_memory.Client")
    @patch("limacharlie.commands.ai_memory.Organization")
    def test_delete_record_uses_delete_verb(self, mock_org_cls, mock_client_cls):
        """delete-record removes the whole agent record, not via the merge."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_org = MagicMock()
        mock_org.oid = "test-oid"
        mock_org.client = mock_client
        mock_org_cls.return_value = mock_org

        result = CliRunner().invoke(cli, [
            "ai-memory", "delete-record",
            "--key", "agent-A", "--confirm",
        ])
        assert result.exit_code == 0, result.output

        args, _ = mock_client.request.call_args
        assert args[0] == "DELETE"
        assert args[1].endswith("/agent-A")


class TestAiMemoryReadCli:
    @patch("limacharlie.commands.ai_memory.Client")
    @patch("limacharlie.commands.ai_memory.Organization")
    def test_get_returns_only_named_memory(self, mock_org_cls, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {
            "data": {"memories": {"alpha": "A", "beta": "B"}},
            "usr_mtd": {},
            "sys_mtd": {},
        }
        mock_client_cls.return_value = mock_client
        mock_org = MagicMock()
        mock_org.oid = "test-oid"
        mock_org.client = mock_client
        mock_org_cls.return_value = mock_org

        result = CliRunner().invoke(cli, [
            "--output", "json",
            "ai-memory", "get", "--key", "agent-A", "--memory-name", "alpha",
        ])
        assert result.exit_code == 0, result.output
        parsed = json.loads(result.output)
        assert parsed["content"] == "A"
        assert parsed["memory_name"] == "alpha"

    @patch("limacharlie.commands.ai_memory.Client")
    @patch("limacharlie.commands.ai_memory.Organization")
    def test_get_missing_memory_exits_nonzero(self, mock_org_cls, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {
            "data": {"memories": {"alpha": "A"}},
            "usr_mtd": {},
            "sys_mtd": {},
        }
        mock_client_cls.return_value = mock_client
        mock_org = MagicMock()
        mock_org.oid = "test-oid"
        mock_org.client = mock_client
        mock_org_cls.return_value = mock_org

        result = CliRunner().invoke(cli, [
            "ai-memory", "get", "--key", "agent-A", "--memory-name", "missing",
        ])
        assert result.exit_code != 0

    @patch("limacharlie.commands.ai_memory.Client")
    @patch("limacharlie.commands.ai_memory.Organization")
    def test_list_returns_flat_memory_map(self, mock_org_cls, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {
            "data": {"memories": {"alpha": "A", "beta": "B"}},
            "usr_mtd": {},
            "sys_mtd": {},
        }
        mock_client_cls.return_value = mock_client
        mock_org = MagicMock()
        mock_org.oid = "test-oid"
        mock_org.client = mock_client
        mock_org_cls.return_value = mock_org

        result = CliRunner().invoke(cli, [
            "--output", "json", "ai-memory", "list", "--key", "agent-A",
        ])
        assert result.exit_code == 0, result.output
        parsed = json.loads(result.output)
        assert parsed == {"alpha": "A", "beta": "B"}
