"""WebSocket attachment to AI sessions.

Thin async wrapper around the ai-sessions WebSocket protocol defined in
``ai-sessions/api/WEBSOCKET_PROTOCOL.md``.  The WS URL is derived from
the same base host used for the AI sessions REST API and authenticated
with the LimaCharlie JWT carried by :class:`limacharlie.Client`.

Two endpoints are exposed by ai-sessions:

* ``/v1/ws/sessions/{id}`` — owner-interactive.  The authenticated user
  must own the session; they can send prompts, interrupts, tool
  approvals, and question answers.
* ``/v1/ws/org/sessions/{id}`` — org-scoped read-only view.  Requires
  ``ai_agent.get`` on the session's owner org.  Write messages are
  rejected locally.

The GCP load balancer routes ``/v1/ws/*`` to the interaction-proxy
(which serves these WebSockets) and ``/v1/sessions/*`` to the
session-manager (REST API); the ``/v1/ws/...`` prefix is what the LB
URL Map actually forwards, so that is the form used here.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator, TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    from .ai import AI


DEFAULT_HEARTBEAT_SECONDS = 25
DEFAULT_MAX_FRAME_BYTES = 10 * 1024 * 1024  # 10 MiB

# Server -> client message types.
MSG_ASSISTANT = "assistant"
MSG_USER = "user"
MSG_SYSTEM = "system"
MSG_TOOL_USE = "tool_use"
MSG_TOOL_RESULT = "tool_result"
MSG_TOOL_APPROVAL_REQUEST = "tool_approval_request"
MSG_ASK_USER_QUESTION = "ask_user_question"
MSG_HISTORY = "history"
MSG_ERROR = "error"
MSG_SESSION_END = "session_end"
MSG_RESULT = "result"

# Client -> server message types.
MSG_PROMPT = "prompt"
MSG_INTERRUPT = "interrupt"
MSG_HEARTBEAT = "heartbeat"
MSG_TOOL_APPROVAL_RESPONSE = "tool_approval_response"
MSG_ASK_USER_QUESTION_RESPONSE = "ask_user_question_response"


class AttachmentForbidden(Exception):
    """The server refused the WebSocket upgrade with 403.

    Typically means the authenticated user is not the session owner.
    Callers may want to retry against the org-scoped read-only endpoint.
    """


def _derive_ws_url(base_url: str, session_id: str, read_only: bool) -> str:
    """Convert the AI sessions HTTP(S) base URL to a wss:// attach URL."""
    parsed = urlparse(base_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    host = parsed.netloc or parsed.path.strip("/")
    sub = "ws/org/sessions" if read_only else "ws/sessions"
    return f"{scheme}://{host}/v1/{sub}/{session_id}"


class SessionAttachment:
    """Open WebSocket connection to an AI session.

    Usage::

        async with ai.attach_session(session_id) as att:
            async for msg in att.messages():
                print(msg)
    """

    def __init__(self, ai: "AI", session_id: str, *,
                 read_only: bool = False,
                 base_url: str | None = None) -> None:
        self._ai = ai
        self._session_id = session_id
        self._read_only = read_only
        # When no explicit override is supplied, resolve the per-org
        # ai-sessions host lazily (in :meth:`url`) so we honour the org's
        # deployment (prod vs staging) rather than a hardcoded host.
        self._base_url = base_url
        self._ws: Any = None
        self._heartbeat_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def read_only(self) -> bool:
        return self._read_only

    def url(self) -> str:
        base_url = self._base_url or self._ai._get_ai_url()
        return _derive_ws_url(base_url, self._session_id, self._read_only)

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        try:
            import websockets
        except ImportError as e:  # pragma: no cover - surfaced to the caller
            raise ImportError(
                "The 'websockets' package is required for AI session "
                "attachment. Install it with: pip install websockets>=13"
            ) from e
        from websockets.exceptions import InvalidStatus, InvalidStatusCode

        client = self._ai.client
        jwt = client.get_jwt()
        url = self.url()
        headers = {"Authorization": f"Bearer {jwt}"}

        connect = getattr(websockets, "connect")
        try:
            # ``websockets`` renamed the header kwarg between releases.
            try:
                self._ws = await connect(
                    url,
                    additional_headers=headers,
                    max_size=DEFAULT_MAX_FRAME_BYTES,
                )
            except TypeError:
                self._ws = await connect(
                    url,
                    extra_headers=headers,
                    max_size=DEFAULT_MAX_FRAME_BYTES,
                )
        except (InvalidStatus, InvalidStatusCode) as e:
            status = _extract_status_code(e)
            if status == 403:
                raise AttachmentForbidden(
                    f"Server refused WebSocket upgrade with 403 for {url}"
                ) from e
            raise

        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def close(self) -> None:
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except (asyncio.CancelledError, Exception):
                pass
            self._heartbeat_task = None
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

    async def __aenter__(self) -> "SessionAttachment":
        await self.connect()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Message stream
    # ------------------------------------------------------------------

    async def messages(self) -> AsyncIterator[dict]:
        if self._ws is None:
            raise RuntimeError("SessionAttachment is not connected")
        async for raw in self._ws:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="replace")
            try:
                yield json.loads(raw)
            except json.JSONDecodeError:
                continue

    # ------------------------------------------------------------------
    # Outbound messages (owner endpoint only)
    # ------------------------------------------------------------------

    async def _send(self, msg: dict) -> None:
        if self._ws is None:
            raise RuntimeError("SessionAttachment is not connected")
        if self._read_only and msg.get("type") != MSG_HEARTBEAT:
            raise RuntimeError(
                f"Cannot send '{msg.get('type')}' on a read-only attachment"
            )
        await self._ws.send(json.dumps(msg))

    async def send_prompt(self, text: str) -> None:
        await self._send({"type": MSG_PROMPT, "payload": {"text": text}})

    async def interrupt(self) -> None:
        await self._send({"type": MSG_INTERRUPT})

    async def approve_tool(self, tool_use_id: str, approved: bool, *,
                           scope: str = "once",
                           pattern: str | None = None,
                           updated_input: dict | None = None,
                           message: str | None = None) -> None:
        payload: dict[str, Any] = {
            "tool_use_id": tool_use_id,
            "approved": approved,
            "approval_scope": scope,
        }
        if pattern:
            payload["approval_pattern"] = pattern
        if updated_input is not None:
            payload["updated_input"] = updated_input
        if message:
            payload["message"] = message
        await self._send({"type": MSG_TOOL_APPROVAL_RESPONSE, "payload": payload})

    async def answer_question(self, question_id: str,
                              answers: dict[str, str]) -> None:
        await self._send({
            "type": MSG_ASK_USER_QUESTION_RESPONSE,
            "payload": {"question_id": question_id, "answers": answers},
        })

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _heartbeat_loop(self) -> None:
        while True:
            await asyncio.sleep(DEFAULT_HEARTBEAT_SECONDS)
            if self._ws is None:
                return
            try:
                await self._ws.send(json.dumps({"type": MSG_HEARTBEAT}))
            except Exception:
                return


def _extract_status_code(exc: Exception) -> int | None:
    """Fetch the HTTP status from ``websockets`` upgrade exceptions.

    The attribute moved across releases: older versions exposed
    ``status_code`` on :class:`InvalidStatusCode`; newer versions use
    :class:`InvalidStatus` which carries a ``response`` object.
    """
    status = getattr(exc, "status_code", None)
    if status is not None:
        return status
    response = getattr(exc, "response", None)
    if response is not None:
        return getattr(response, "status_code", None)
    return None
