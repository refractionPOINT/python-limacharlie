"""Streaming + interactive runtime for `limacharlie ai session attach`.

Kept in its own module so the main ``commands/ai.py`` file stays readable.
Exposes :func:`run_attach` which is called by the Click command and
handles both the passive "view the stream" and the interactive
"chat with the session" modes.
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

import click

from ..sdk.ai import AI as AISDK
from ..sdk.ai_session import (
    AttachmentForbidden,
    MSG_ASK_USER_QUESTION,
    MSG_ASSISTANT,
    MSG_ERROR,
    MSG_HISTORY,
    MSG_RESULT,
    MSG_SESSION_END,
    MSG_SYSTEM,
    MSG_TOOL_APPROVAL_REQUEST,
    MSG_TOOL_RESULT,
    MSG_TOOL_USE,
    MSG_USER,
    SessionAttachment,
)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_attach(sdk: AISDK, session_id: str, *,
               read_only: bool,
               interactive: bool,
               show_history: bool,
               raw: bool) -> int:
    """Run the attach session loop.

    Returns the process exit code: 0 on clean disconnect, 1 on error.
    """
    try:
        return asyncio.run(_attach(
            sdk, session_id,
            read_only=read_only,
            interactive=interactive,
            show_history=show_history,
            raw=raw,
        ))
    except KeyboardInterrupt:
        return 0


# ---------------------------------------------------------------------------
# Async core
# ---------------------------------------------------------------------------

async def _attach(sdk: AISDK, session_id: str, *,
                  read_only: bool,
                  interactive: bool,
                  show_history: bool,
                  raw: bool) -> int:
    # Choose the endpoint.  If the user didn't force --read-only and the
    # owner endpoint refuses us with 403, fall back transparently.
    att = sdk.attach_session(session_id, read_only=read_only)
    try:
        await att.connect()
    except AttachmentForbidden:
        if read_only:
            _err("Access denied: you do not have ai_agent.get on this org.")
            return 1
        _notice("Owner access denied; retrying in read-only mode.")
        att = sdk.attach_session(session_id, read_only=True)
        try:
            await att.connect()
        except AttachmentForbidden:
            _err("Access denied for both owner and org-scoped endpoints.")
            return 1
        read_only = True

    _notice(
        f"Attached to session {session_id} "
        f"({'read-only' if read_only else 'interactive'} mode). "
        f"Ctrl+C to detach."
    )

    try:
        async with att:
            reader = asyncio.create_task(_reader_loop(
                att,
                interactive=interactive and not read_only,
                show_history=show_history,
                raw=raw,
            ))
            writer: asyncio.Task | None = None
            if interactive and not read_only:
                writer = asyncio.create_task(_input_loop(att))

            try:
                await reader
            finally:
                if writer is not None:
                    writer.cancel()
                    try:
                        await writer
                    except (asyncio.CancelledError, Exception):
                        pass
    except Exception as e:
        _err(f"Connection error: {e}")
        return 1

    return 0


# ---------------------------------------------------------------------------
# Reader (server -> terminal)
# ---------------------------------------------------------------------------

async def _reader_loop(att: SessionAttachment, *,
                       interactive: bool,
                       show_history: bool,
                       raw: bool) -> None:
    async for msg in att.messages():
        if raw:
            click.echo(json.dumps(msg))
            if msg.get("type") == MSG_SESSION_END:
                return
            continue

        mtype = msg.get("type")
        payload = msg.get("payload") or {}

        if mtype == MSG_HISTORY:
            if show_history:
                messages = payload.get("messages") or []
                _print_banner(f"History ({len(messages)} messages)")
                for m in messages:
                    _render_message(m)
                _print_banner("Live stream")
            continue

        if mtype == MSG_TOOL_APPROVAL_REQUEST and interactive:
            await _handle_approval(att, payload)
            continue

        if mtype == MSG_ASK_USER_QUESTION and interactive:
            await _handle_question(att, payload)
            continue

        _render_message(msg)

        if mtype == MSG_SESSION_END:
            return


# ---------------------------------------------------------------------------
# Writer (terminal -> server)
# ---------------------------------------------------------------------------

async def _input_loop(att: SessionAttachment) -> None:
    """Read stdin lines and send them as prompts.

    Each line is sent as a ``prompt`` message.  An empty line is
    ignored.  ``/interrupt`` is translated to a WebSocket interrupt
    message; ``/quit`` ends the session loop.
    """
    loop = asyncio.get_running_loop()
    while True:
        try:
            line = await loop.run_in_executor(None, _read_line_or_eof)
        except (EOFError, KeyboardInterrupt):
            return
        if line is None:  # EOF
            return
        stripped = line.strip()
        if not stripped:
            continue
        if stripped == "/quit":
            return
        if stripped == "/interrupt":
            try:
                await att.interrupt()
                _notice("interrupt sent")
            except Exception as e:
                _err(f"failed to send interrupt: {e}")
            continue
        try:
            await att.send_prompt(stripped)
        except Exception as e:
            _err(f"failed to send prompt: {e}")


def _read_line_or_eof() -> str | None:
    """Blocking stdin read returning ``None`` on EOF.

    Printed to stderr so it doesn't interleave with stdout messages
    when the terminal is being driven by another task.
    """
    try:
        sys.stderr.write("> ")
        sys.stderr.flush()
    except Exception:
        pass
    line = sys.stdin.readline()
    if not line:
        return None
    return line.rstrip("\n")


# ---------------------------------------------------------------------------
# Interactive approvals / questions
# ---------------------------------------------------------------------------

async def _handle_approval(att: SessionAttachment, payload: dict) -> None:
    tool_use_id = payload.get("tool_use_id", "")
    tool_name = payload.get("tool_name", "<unknown>")
    tool_input = payload.get("tool_input")
    click.echo(click.style(
        f"\nTool approval requested: {tool_name}",
        fg="yellow", bold=True,
    ))
    if tool_input is not None:
        click.echo(click.style(
            f"  input: {_oneline(json.dumps(tool_input))}",
            fg="yellow",
        ))

    loop = asyncio.get_running_loop()
    answer = await loop.run_in_executor(
        None, lambda: click.prompt(
            "Approve? [y/n/session]",
            default="n", show_default=False,
        ),
    )
    answer = answer.strip().lower()
    if answer in ("y", "yes"):
        await att.approve_tool(tool_use_id, True, scope="once")
        _notice("approved (this call)")
    elif answer in ("session", "s"):
        await att.approve_tool(tool_use_id, True, scope="session")
        _notice("approved (session)")
    else:
        await att.approve_tool(tool_use_id, False, scope="once",
                               message="denied by CLI user")
        _notice("denied")


async def _handle_question(att: SessionAttachment, payload: dict) -> None:
    question_id = payload.get("question_id", "")
    questions = payload.get("questions") or []
    answers: dict[str, str] = {}

    loop = asyncio.get_running_loop()
    for q in questions:
        header = q.get("header") or q.get("question", "question")
        prompt_text = q.get("question", header)
        options = q.get("options") or []

        click.echo(click.style(f"\nQuestion: {prompt_text}", fg="magenta", bold=True))
        if options:
            for i, opt in enumerate(options, 1):
                label = opt.get("label") if isinstance(opt, dict) else str(opt)
                desc = opt.get("description") if isinstance(opt, dict) else ""
                line = f"  {i}. {label}"
                if desc:
                    line += f" - {desc}"
                click.echo(click.style(line, fg="magenta"))
            choice = await loop.run_in_executor(
                None, lambda: click.prompt("Choose", type=str),
            )
            choice = choice.strip()
            if choice.isdigit() and 1 <= int(choice) <= len(options):
                opt = options[int(choice) - 1]
                answer = opt.get("label") if isinstance(opt, dict) else str(opt)
            else:
                answer = choice
        else:
            answer = await loop.run_in_executor(
                None, lambda: click.prompt("Answer", type=str),
            )
            answer = answer.strip()
        answers[header] = answer

    await att.answer_question(question_id, answers)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _render_message(msg: dict[str, Any]) -> None:
    mtype = msg.get("type")
    payload = msg.get("payload") or {}
    ts = msg.get("timestamp")
    prefix = f"[{ts}] " if ts else ""

    if mtype == MSG_ASSISTANT:
        text = _extract_assistant_text(payload)
        click.echo(click.style(f"{prefix}assistant:", fg="cyan", bold=True))
        if text:
            click.echo(_indent(text))
        return

    if mtype == MSG_USER:
        text = payload.get("text", "")
        click.echo(click.style(f"{prefix}user:", fg="green", bold=True))
        if text:
            click.echo(_indent(text))
        return

    if mtype == MSG_TOOL_USE:
        name = payload.get("name", "<tool>")
        tid = payload.get("id", "")
        tool_in = _oneline(json.dumps(payload.get("input", {})))
        click.echo(click.style(
            f"{prefix}tool_use {name} ({tid}): {tool_in}",
            fg="yellow",
        ))
        return

    if mtype == MSG_TOOL_RESULT:
        tid = payload.get("tool_use_id", "")
        content = payload.get("content", "")
        if isinstance(content, (dict, list)):
            content = json.dumps(content)
        click.echo(click.style(
            f"{prefix}tool_result ({tid}):", fg="yellow", dim=True,
        ))
        if content:
            click.echo(_indent(_truncate(str(content), 4000)))
        return

    if mtype == MSG_SYSTEM:
        subtype = payload.get("subtype", "")
        text = payload.get("message") or payload.get("text") or ""
        tag = f"system[{subtype}]" if subtype else "system"
        click.echo(click.style(f"{prefix}{tag}: {_oneline(str(text))}", dim=True))
        return

    if mtype == MSG_ERROR:
        code = payload.get("code", "")
        message = payload.get("message", "")
        click.echo(click.style(
            f"{prefix}error [{code}]: {message}", fg="red", bold=True,
        ), err=True)
        return

    if mtype == MSG_SESSION_END:
        reason = payload.get("reason", "")
        exit_code = payload.get("exit_code")
        extra = f" (exit_code={exit_code})" if exit_code is not None else ""
        click.echo(click.style(
            f"{prefix}session ended: {reason}{extra}",
            fg="red", bold=True,
        ))
        return

    if mtype == MSG_RESULT:
        summary = payload.get("summary") or payload.get("message") or ""
        click.echo(click.style(f"{prefix}result: {summary}", fg="blue"))
        return

    if mtype == MSG_TOOL_APPROVAL_REQUEST:
        name = payload.get("tool_name", "<tool>")
        tool_in = _oneline(json.dumps(payload.get("tool_input", {})))
        click.echo(click.style(
            f"{prefix}approval requested for {name}: {tool_in}",
            fg="yellow", bold=True,
        ))
        return

    if mtype == MSG_ASK_USER_QUESTION:
        questions = payload.get("questions") or []
        headers = ", ".join(q.get("question", "?") for q in questions) or "?"
        click.echo(click.style(
            f"{prefix}question: {headers}", fg="magenta", bold=True,
        ))
        return

    # Unknown type: fall back to compact JSON.
    click.echo(click.style(
        f"{prefix}{mtype}: {_oneline(json.dumps(payload))}", dim=True,
    ))


def _extract_assistant_text(payload: dict) -> str:
    content = payload.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif "text" in block:
                    parts.append(str(block["text"]))
        return "\n".join(p for p in parts if p)
    return str(content or "")


# ---------------------------------------------------------------------------
# Small utilities
# ---------------------------------------------------------------------------

def _indent(text: str, prefix: str = "  ") -> str:
    return "\n".join(prefix + line for line in text.splitlines() or [""])


def _oneline(text: str, limit: int = 500) -> str:
    collapsed = " ".join(text.split())
    return _truncate(collapsed, limit)


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _print_banner(text: str) -> None:
    click.echo(click.style(f"--- {text} ---", dim=True), err=True)


def _notice(text: str) -> None:
    click.echo(click.style(text, dim=True), err=True)


def _err(text: str) -> None:
    click.echo(click.style(text, fg="red", bold=True), err=True)
