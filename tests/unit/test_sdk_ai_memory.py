"""Tests for limacharlie.sdk.ai_memory module.

Focus: the partial-merge mechanism. The server-side hook is the source
of truth, but the SDK has to send the right shape ({memories: {name:
content}} for set, {memories: {name: null}} for delete) so the hook can
do its job.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from limacharlie.sdk.ai_memory import AiMemory, MEMORIES_FIELD, HIVE_NAME


@pytest.fixture
def mock_org():
    org = MagicMock()
    org.oid = "test-oid"
    org.client = MagicMock()
    return org


@pytest.fixture
def am(mock_org):
    return AiMemory(mock_org)


def _post_call(mock_org):
    """Pull the most recent client.request POST call args."""
    args, kwargs = mock_org.client.request.call_args
    assert args[0] == "POST"
    return args[1], kwargs.get("params", {})


class TestPartialSetSemantics:
    """Set on one memory name must send only that key's payload."""

    def test_set_sends_only_named_memory(self, am, mock_org):
        am.set("agent-A", "notes/today", "wrote the cli wrapper")
        url, params = _post_call(mock_org)
        assert url == f"hive/{HIVE_NAME}/test-oid/agent-A/data"
        payload = json.loads(params["data"])
        # Only the {memories: {name: content}} envelope - no other fields.
        assert payload == {MEMORIES_FIELD: {"notes/today": "wrote the cli wrapper"}}

    def test_set_does_not_fetch_first(self, am, mock_org):
        """Set must not round-trip through GET; the merge hook handles it."""
        am.set("agent-A", "notes/today", "content")
        # Exactly one request, and it is the POST set.
        assert mock_org.client.request.call_count == 1
        assert mock_org.client.request.call_args[0][0] == "POST"

    def test_set_url_escapes_agent_key(self, am, mock_org):
        am.set("agent/with/slashes", "k", "v")
        url, _ = _post_call(mock_org)
        assert "agent%2Fwith%2Fslashes" in url

    def test_set_many_carries_every_entry(self, am, mock_org):
        am.set_many("agent-A", {"a": "1", "b": "2", "c": None})
        _, params = _post_call(mock_org)
        payload = json.loads(params["data"])
        assert payload == {MEMORIES_FIELD: {"a": "1", "b": "2", "c": None}}


class TestPartialDeleteSemantics:
    """Delete on one memory name must send {name: null} so the hook drops it."""

    def test_delete_sends_null_for_named_memory(self, am, mock_org):
        am.delete("agent-A", "notes/today")
        url, params = _post_call(mock_org)
        assert url == f"hive/{HIVE_NAME}/test-oid/agent-A/data"
        payload = json.loads(params["data"])
        assert payload == {MEMORIES_FIELD: {"notes/today": None}}

    def test_delete_preserves_null_through_json(self, am, mock_org):
        """A regression guard: HiveRecord.set() would strip None on the way
        through json.dumps; verify our partial path keeps it intact."""
        am.delete("agent-A", "k")
        _, params = _post_call(mock_org)
        # The literal "null" must appear in the wire payload.
        assert ': null' in params["data"] or ':null' in params["data"]


class TestDeleteRecord:
    def test_delete_record_uses_hive_delete(self, am, mock_org):
        am.delete_record("agent-A")
        # HiveDelete uses DELETE verb against the bare record path.
        args, _ = mock_org.client.request.call_args
        assert args[0] == "DELETE"
        assert args[1] == f"hive/{HIVE_NAME}/test-oid/agent-A"


class TestRead:
    def _record_response(self, memories):
        return {
            "data": {MEMORIES_FIELD: memories},
            "usr_mtd": {},
            "sys_mtd": {"etag": "e1"},
        }

    def test_get_returns_named_memory_content(self, am, mock_org):
        mock_org.client.request.return_value = self._record_response({
            "alpha": "content-a",
            "beta": "content-b",
        })
        assert am.get("agent-A", "alpha") == "content-a"

    def test_get_missing_memory_returns_none(self, am, mock_org):
        mock_org.client.request.return_value = self._record_response({"alpha": "a"})
        assert am.get("agent-A", "does-not-exist") is None

    def test_list_memories_returns_full_map(self, am, mock_org):
        mock_org.client.request.return_value = self._record_response({
            "alpha": "a", "beta": "b",
        })
        out = am.list_memories("agent-A")
        assert out == {"alpha": "a", "beta": "b"}

    def test_list_memories_missing_field_returns_empty(self, am, mock_org):
        mock_org.client.request.return_value = {
            "data": {},
            "usr_mtd": {},
            "sys_mtd": {},
        }
        assert am.list_memories("agent-A") == {}

    def test_list_records_lists_all_agents(self, am, mock_org):
        mock_org.client.request.return_value = {
            "agent-A": {"data": {MEMORIES_FIELD: {"a": "1"}}, "usr_mtd": {}, "sys_mtd": {}},
            "agent-B": {"data": {MEMORIES_FIELD: {}}, "usr_mtd": {}, "sys_mtd": {}},
        }
        result = am.list_records()
        assert set(result.keys()) == {"agent-A", "agent-B"}
        # The hive list endpoint targets the partition root.
        url = mock_org.client.request.call_args[0][1]
        assert url == f"hive/{HIVE_NAME}/test-oid"


class TestPartitionKey:
    def test_default_partition_is_org_oid(self, mock_org):
        am = AiMemory(mock_org)
        am.set("agent-A", "k", "v")
        url, _ = _post_call(mock_org)
        assert "/test-oid/" in url

    def test_custom_partition(self, mock_org):
        am = AiMemory(mock_org, partition_key="custom-part")
        am.set("agent-A", "k", "v")
        url, _ = _post_call(mock_org)
        assert "/custom-part/" in url
