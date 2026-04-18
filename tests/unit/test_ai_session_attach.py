"""Tests for the AI session WebSocket attach feature.

Covers:
  * ``_derive_ws_url`` — HTTPS/HTTP -> wss/ws conversion and
    owner-vs-org endpoint selection.
  * ``SessionAttachment`` send/receive plumbing against a stub WS.
  * ``_extract_status_code`` — status extraction across the two
    ``websockets`` exception shapes.
  * Pretty-printer rendering for each known message type.
  * Click registration of ``limacharlie ai session attach``.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import click
import click.testing
import pytest

from limacharlie.sdk import ai_session
from limacharlie.sdk.ai_session import (
    AttachmentForbidden,
    SessionAttachment,
    _derive_ws_url,
    _extract_status_code,
)


# ---------------------------------------------------------------------------
# URL derivation
# ---------------------------------------------------------------------------

class TestDeriveWsUrl:

    def test_https_base_maps_to_wss_owner_endpoint(self):
        url = _derive_ws_url("https://ai.limacharlie.io", "sid-1", read_only=False)
        assert url == "wss://ai.limacharlie.io/v1/ws/sessions/sid-1"

    def test_https_base_maps_to_wss_org_endpoint(self):
        url = _derive_ws_url("https://ai.limacharlie.io", "sid-1", read_only=True)
        assert url == "wss://ai.limacharlie.io/v1/ws/org/sessions/sid-1"

    def test_http_base_maps_to_ws(self):
        url = _derive_ws_url("http://localhost:8080", "sid-2", read_only=False)
        assert url == "ws://localhost:8080/v1/ws/sessions/sid-2"

    def test_staging_host_preserved(self):
        url = _derive_ws_url(
            "https://ai-sessions-staging.limacharlie.io", "abc", read_only=False,
        )
        assert url.startswith("wss://ai-sessions-staging.limacharlie.io/")


# ---------------------------------------------------------------------------
# Status-code extraction (websockets API stability helper)
# ---------------------------------------------------------------------------

class TestExtractStatusCode:

    def test_reads_legacy_status_code_attr(self):
        err = SimpleNamespace(status_code=403)
        assert _extract_status_code(err) == 403

    def test_reads_new_response_status_code(self):
        err = SimpleNamespace(response=SimpleNamespace(status_code=401))
        assert _extract_status_code(err) == 401

    def test_returns_none_when_unavailable(self):
        assert _extract_status_code(ValueError("boom")) is None


# ---------------------------------------------------------------------------
# SessionAttachment plumbing (no real network)
# ---------------------------------------------------------------------------

class FakeWebSocket:
    """Minimal async WS stand-in driven by a pre-seeded message list."""

    def __init__(self, incoming: list[str] | None = None) -> None:
        self._incoming = list(incoming or [])
        self.sent: list[str] = []
        self.closed = False

    async def send(self, data: str) -> None:
        self.sent.append(data)

    async def close(self) -> None:
        self.closed = True

    def __aiter__(self):
        return self._iter()

    async def _iter(self):
        for item in self._incoming:
            yield item


def _make_attachment(ws: FakeWebSocket, *, read_only: bool = False) -> SessionAttachment:
    ai_stub = SimpleNamespace(client=SimpleNamespace(get_jwt=lambda: "jwt"))
    att = SessionAttachment(ai_stub, "sid-xyz", read_only=read_only)
    att._ws = ws
    return att


class TestSessionAttachmentSend:

    def test_send_prompt_writes_json(self):
        ws = FakeWebSocket()
        att = _make_attachment(ws)
        asyncio.run(att.send_prompt("hello world"))
        assert len(ws.sent) == 1
        payload = json.loads(ws.sent[0])
        assert payload == {
            "type": "prompt", "payload": {"text": "hello world"},
        }

    def test_interrupt(self):
        ws = FakeWebSocket()
        att = _make_attachment(ws)
        asyncio.run(att.interrupt())
        assert json.loads(ws.sent[0]) == {"type": "interrupt"}

    def test_approve_tool_once_minimal(self):
        ws = FakeWebSocket()
        att = _make_attachment(ws)
        asyncio.run(att.approve_tool("tu-1", True))
        msg = json.loads(ws.sent[0])
        assert msg["type"] == "tool_approval_response"
        assert msg["payload"] == {
            "tool_use_id": "tu-1",
            "approved": True,
            "approval_scope": "once",
        }

    def test_approve_tool_session_with_pattern(self):
        ws = FakeWebSocket()
        att = _make_attachment(ws)
        asyncio.run(att.approve_tool(
            "tu-1", True, scope="session", pattern="Bash(git:*)",
            updated_input={"command": "git status"},
            message="auto-approve",
        ))
        msg = json.loads(ws.sent[0])
        assert msg["payload"] == {
            "tool_use_id": "tu-1",
            "approved": True,
            "approval_scope": "session",
            "approval_pattern": "Bash(git:*)",
            "updated_input": {"command": "git status"},
            "message": "auto-approve",
        }

    def test_approve_tool_denied(self):
        ws = FakeWebSocket()
        att = _make_attachment(ws)
        asyncio.run(att.approve_tool("tu-1", False, message="no"))
        msg = json.loads(ws.sent[0])
        assert msg["payload"]["approved"] is False
        assert msg["payload"]["message"] == "no"

    def test_answer_question(self):
        ws = FakeWebSocket()
        att = _make_attachment(ws)
        asyncio.run(att.answer_question("q-1", {"Which database": "staging"}))
        msg = json.loads(ws.sent[0])
        assert msg == {
            "type": "ask_user_question_response",
            "payload": {
                "question_id": "q-1",
                "answers": {"Which database": "staging"},
            },
        }

    def test_read_only_rejects_writes(self):
        ws = FakeWebSocket()
        att = _make_attachment(ws, read_only=True)
        with pytest.raises(RuntimeError, match="read-only"):
            asyncio.run(att.send_prompt("x"))
        assert ws.sent == []

    def test_read_only_allows_heartbeat(self):
        ws = FakeWebSocket()
        att = _make_attachment(ws, read_only=True)
        # Direct _send call mimics what the heartbeat task does.
        asyncio.run(att._send({"type": "heartbeat"}))
        assert json.loads(ws.sent[0]) == {"type": "heartbeat"}


class TestSessionAttachmentReceive:

    def test_messages_yields_parsed_json_and_skips_garbage(self):
        ws = FakeWebSocket(incoming=[
            json.dumps({"type": "assistant", "payload": {"content": "hi"}}),
            "not json",
            json.dumps({"type": "session_end", "payload": {"reason": "done"}}),
        ])
        att = _make_attachment(ws)

        async def drain():
            return [m async for m in att.messages()]

        got = asyncio.run(drain())
        assert [m["type"] for m in got] == ["assistant", "session_end"]

    def test_messages_decodes_bytes(self):
        ws = FakeWebSocket(incoming=[
            json.dumps({"type": "system", "payload": {"message": "hi"}}).encode(),
        ])
        att = _make_attachment(ws)

        async def drain():
            return [m async for m in att.messages()]

        got = asyncio.run(drain())
        assert got == [{"type": "system", "payload": {"message": "hi"}}]


class TestSessionAttachmentUrl:

    def test_url_uses_base_url_override(self):
        att = SessionAttachment(
            SimpleNamespace(client=None),
            "sid-42",
            base_url="https://example.test",
        )
        assert att.url() == "wss://example.test/v1/ws/sessions/sid-42"

    def test_url_read_only_uses_org_endpoint(self):
        att = SessionAttachment(
            SimpleNamespace(client=None),
            "sid-42",
            read_only=True,
            base_url="https://example.test",
        )
        assert att.url() == "wss://example.test/v1/ws/org/sessions/sid-42"


# ---------------------------------------------------------------------------
# Pretty-printer
# ---------------------------------------------------------------------------

class TestRenderMessage:
    """Verify every known message type produces human-readable output.

    We assert on substrings rather than exact formatting so that
    colour/layout tweaks in the future don't invalidate the tests.
    """

    def _render(self, msg: dict) -> str:
        from limacharlie.commands import _ai_attach

        runner = click.testing.CliRunner()

        @click.command()
        def dump():
            _ai_attach._render_message(msg)

        result = runner.invoke(dump, [])
        assert result.exit_code == 0, result.output
        return result.output

    def test_assistant_text(self):
        out = self._render({
            "type": "assistant",
            "timestamp": "t1",
            "payload": {"content": [
                {"type": "text", "text": "hello from claude"},
            ]},
        })
        assert "assistant" in out
        assert "hello from claude" in out

    def test_user_text(self):
        out = self._render({
            "type": "user",
            "payload": {"text": "list files"},
        })
        assert "user" in out
        assert "list files" in out

    def test_tool_use_includes_tool_name_and_input(self):
        out = self._render({
            "type": "tool_use",
            "payload": {"id": "t1", "name": "Bash", "input": {"command": "ls"}},
        })
        assert "tool_use" in out
        assert "Bash" in out
        assert "ls" in out

    def test_tool_result_includes_content(self):
        out = self._render({
            "type": "tool_result",
            "payload": {"tool_use_id": "t1", "content": "file1\nfile2"},
        })
        assert "tool_result" in out
        assert "file1" in out

    def test_system_message_inlined(self):
        out = self._render({
            "type": "system",
            "payload": {"subtype": "init_received", "message": "ready"},
        })
        assert "system" in out
        assert "init_received" in out or "ready" in out

    def test_error_renders_code_and_message(self):
        out = self._render({
            "type": "error",
            "payload": {"code": "session_not_running", "message": "nope"},
        })
        assert "error" in out
        assert "session_not_running" in out
        assert "nope" in out

    def test_session_end_shows_reason(self):
        out = self._render({
            "type": "session_end",
            "payload": {"reason": "completed", "exit_code": 0},
        })
        assert "session ended" in out
        assert "completed" in out
        assert "exit_code" in out

    def test_result_shows_summary(self):
        out = self._render({
            "type": "result",
            "payload": {"summary": "task done"},
        })
        assert "result" in out
        assert "task done" in out

    def test_approval_request_renders_tool_and_input(self):
        out = self._render({
            "type": "tool_approval_request",
            "payload": {
                "tool_use_id": "t1",
                "tool_name": "Bash",
                "tool_input": {"command": "rm -rf /"},
            },
        })
        assert "approval" in out
        assert "Bash" in out

    def test_ask_user_question_renders_questions(self):
        out = self._render({
            "type": "ask_user_question",
            "payload": {
                "question_id": "q1",
                "questions": [{"question": "Which env?", "header": "env"}],
            },
        })
        assert "question" in out
        assert "Which env?" in out

    def test_unknown_type_falls_back_to_compact_json(self):
        out = self._render({
            "type": "brand_new_type",
            "payload": {"foo": "bar"},
        })
        assert "brand_new_type" in out
        assert "foo" in out


# ---------------------------------------------------------------------------
# Assistant content extraction
# ---------------------------------------------------------------------------

class TestExtractAssistantText:

    def test_text_content_blocks_concatenated(self):
        from limacharlie.commands._ai_attach import _extract_assistant_text

        text = _extract_assistant_text({"content": [
            {"type": "text", "text": "hello "},
            {"type": "text", "text": "world"},
        ]})
        assert "hello " in text and "world" in text

    def test_string_content_passthrough(self):
        from limacharlie.commands._ai_attach import _extract_assistant_text

        assert _extract_assistant_text({"content": "plain"}) == "plain"

    def test_missing_content(self):
        from limacharlie.commands._ai_attach import _extract_assistant_text

        assert _extract_assistant_text({}) == ""


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

class TestTruncation:

    def test_truncate_preserves_short_strings(self):
        from limacharlie.commands._ai_attach import _truncate

        assert _truncate("abc", 10) == "abc"

    def test_truncate_appends_ellipsis(self):
        from limacharlie.commands._ai_attach import _truncate

        out = _truncate("x" * 20, 5)
        assert out.endswith("...")
        assert len(out) == 5 + 3

    def test_oneline_collapses_whitespace(self):
        from limacharlie.commands._ai_attach import _oneline

        assert _oneline("a\n  b\t\tc") == "a b c"


# ---------------------------------------------------------------------------
# CLI registration
# ---------------------------------------------------------------------------

class TestCliRegistration:

    def test_attach_command_registered_under_ai_session(self):
        from limacharlie.cli import cli

        runner = click.testing.CliRunner()
        result = runner.invoke(cli, ["ai", "session", "attach", "--help"])
        assert result.exit_code == 0, result.output
        assert "--id" in result.output
        assert "--read-only" in result.output
        assert "--interactive" in result.output
        assert "--raw" in result.output

    def test_attach_requires_session_id(self):
        from limacharlie.cli import cli

        runner = click.testing.CliRunner()
        result = runner.invoke(cli, ["ai", "session", "attach"])
        # Click prints usage error and exits non-zero when required
        # option is missing.
        assert result.exit_code != 0
        assert "--id" in result.output or "id" in result.output.lower()


# ---------------------------------------------------------------------------
# Module-level constants sanity check
# ---------------------------------------------------------------------------

def test_exported_message_constants_match_protocol():
    """Defensive: the canonical message-type strings must match what the
    server actually sends.  If ai-sessions ever renames one of these,
    every downstream check in this CLI breaks silently.  Fail loudly.
    """
    assert ai_session.MSG_ASSISTANT == "assistant"
    assert ai_session.MSG_TOOL_USE == "tool_use"
    assert ai_session.MSG_TOOL_APPROVAL_REQUEST == "tool_approval_request"
    assert ai_session.MSG_ASK_USER_QUESTION == "ask_user_question"
    assert ai_session.MSG_SESSION_END == "session_end"
    assert ai_session.MSG_HISTORY == "history"
    assert ai_session.MSG_PROMPT == "prompt"
    assert ai_session.MSG_INTERRUPT == "interrupt"
    assert ai_session.MSG_HEARTBEAT == "heartbeat"
    assert ai_session.MSG_TOOL_APPROVAL_RESPONSE == "tool_approval_response"
    assert ai_session.MSG_ASK_USER_QUESTION_RESPONSE == "ask_user_question_response"
