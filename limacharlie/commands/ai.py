"""AI-powered generation commands for LimaCharlie CLI v2.

Commands for using LimaCharlie's AI capabilities to generate
Detection & Response rules and LCQL queries from natural language
descriptions.
"""

from __future__ import annotations

from typing import Any

import click

from ..cli import pass_context
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.ai import AI as AISDK
from ..output import format_output, detect_output_format
from ..discovery import register_explain


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _output(ctx: click.Context, data: Any) -> None:
    fmt = ctx.obj.output_format or detect_output_format()
    if not ctx.obj.quiet:
        click.echo(format_output(data, fmt))


def _get_org(ctx: click.Context) -> Organization:
    client = Client(oid=ctx.obj.oid, environment=ctx.obj.environment, print_debug_fn=ctx.obj.debug_fn, debug_full_response=ctx.obj.debug_full, debug_curl=ctx.obj.debug_curl, debug_verbose=ctx.obj.debug_verbose)
    return Organization(client)


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------

@click.group("ai")
def group() -> None:
    """AI-powered generation of rules and queries.

    Use natural language descriptions to generate D&R rules and
    LCQL queries.  Generated output should be reviewed before use.
    """


# ---------------------------------------------------------------------------
# generate-rule
# ---------------------------------------------------------------------------

_EXPLAIN_GENERATE_RULE = """\
Generate a complete D&R rule (detection + response) from a natural
language description.  The AI will produce both the detection
component and the response actions.

The output is a YAML structure ready for use with 'limacharlie dr set':

    detect:
      op: ends with
      event: NEW_PROCESS
      path: event/FILE_PATH
      value: powershell.exe
      rules:
        - op: contains
          path: event/COMMAND_LINE
          value: downloadstring
    respond:
      - action: report
        name: powershell-download-detected

The generated rule should be reviewed before deployment.

Example:
  limacharlie ai generate-rule \\
    --prompt "Detect PowerShell downloading files from the internet"
"""
register_explain("ai.generate-rule", _EXPLAIN_GENERATE_RULE)


@group.command("generate-rule")
@click.option("--prompt", required=True, help="Natural language description of the detection.")
@pass_context
def generate_rule(ctx, prompt) -> None:
    org = _get_org(ctx)
    sdk = AISDK(org)
    data = sdk.generate_dr_rule(prompt)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# generate-query
# ---------------------------------------------------------------------------

_EXPLAIN_GENERATE_QUERY = """\
Generate an LCQL (LimaCharlie Query Language) query from a natural
language description.  The AI will produce a query that can be used
with 'limacharlie search run'.

LCQL queries follow a SQL-like syntax for searching telemetry:

    event_type = DNS_REQUEST
    AND event/DOMAIN_NAME ends with ".ru"
    AND timestamp >= now() - 24h

Example:
  limacharlie ai generate-query \\
    --prompt "Find all DNS requests to .ru domains in the last 24 hours"
"""
register_explain("ai.generate-query", _EXPLAIN_GENERATE_QUERY)


@group.command("generate-query")
@click.option("--prompt", required=True, help="Natural language description of the query.")
@pass_context
def generate_query(ctx, prompt) -> None:
    org = _get_org(ctx)
    sdk = AISDK(org)
    data = sdk.generate_lcql(prompt)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# generate-detection
# ---------------------------------------------------------------------------

_EXPLAIN_GENERATE_DETECTION = """\
Generate a detection component from a natural language description.
The AI will produce only the detection part of a D&R rule (no response
actions).

Example:
  limacharlie ai generate-detection \\
    --description "Detect PowerShell executing encoded commands"
"""
register_explain("ai.generate-detection", _EXPLAIN_GENERATE_DETECTION)


@group.command("generate-detection")
@click.option("--description", required=True, help="Natural language description of the detection.")
@pass_context
def generate_detection(ctx, description) -> None:
    org = _get_org(ctx)
    sdk = AISDK(org)
    data = sdk.generate_detection(description)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# generate-response
# ---------------------------------------------------------------------------

_EXPLAIN_GENERATE_RESPONSE = """\
Generate a response component from a natural language description.
The AI will produce only the response actions part of a D&R rule
(no detection logic).

Example:
  limacharlie ai generate-response \\
    --description "Alert and isolate the sensor from the network"
"""
register_explain("ai.generate-response", _EXPLAIN_GENERATE_RESPONSE)


@group.command("generate-response")
@click.option("--description", required=True, help="Natural language description of the response actions.")
@pass_context
def generate_response(ctx, description) -> None:
    org = _get_org(ctx)
    sdk = AISDK(org)
    data = sdk.generate_response(description)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# generate-selector
# ---------------------------------------------------------------------------

_EXPLAIN_GENERATE_SELECTOR = """\
Generate a sensor selector expression (bexpr) from a natural language
description.  Sensor selectors target specific groups of sensors for
D&R rules, tasks, and queries.

Selector syntax examples:
  plat == `windows`
  `production` in tags
  plat == `linux` AND `web-server` in tags

Example:
  limacharlie ai generate-selector \\
    --description "All Windows servers with the production tag"
"""
register_explain("ai.generate-selector", _EXPLAIN_GENERATE_SELECTOR)


@group.command("generate-selector")
@click.option("--description", required=True, help="Natural language description of the sensor selector.")
@pass_context
def generate_selector(ctx, description) -> None:
    org = _get_org(ctx)
    sdk = AISDK(org)
    data = sdk.generate_sensor_selector(description)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# generate-playbook
# ---------------------------------------------------------------------------

_EXPLAIN_GENERATE_PLAYBOOK = """\
Generate a Python playbook from a natural language description.
Playbooks are automation scripts that can be deployed as LimaCharlie
services.

Example:
  limacharlie ai generate-playbook \\
    --description "Collect process listing when a new detection fires"
"""
register_explain("ai.generate-playbook", _EXPLAIN_GENERATE_PLAYBOOK)


@group.command("generate-playbook")
@click.option("--description", required=True, help="Natural language description of the playbook.")
@pass_context
def generate_playbook(ctx, description) -> None:
    org = _get_org(ctx)
    sdk = AISDK(org)
    data = sdk.generate_playbook(description)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# summarize-detection
# ---------------------------------------------------------------------------

_EXPLAIN_SUMMARIZE_DETECTION = """\
Summarize a detection using AI.  Provide the detection ID and the
command will fetch the detection data and produce a human-readable
summary.

Example:
  limacharlie ai summarize-detection --detection-id <DETECTION_ID>
"""
register_explain("ai.summarize-detection", _EXPLAIN_SUMMARIZE_DETECTION)


@group.command("summarize-detection")
@click.option("--detection-id", required=True, help="Detection ID to summarize.")
@pass_context
def summarize_detection(ctx, detection_id) -> None:
    org = _get_org(ctx)
    # Fetch the detection data first, then summarize it.
    detection_data = org.get_detection_by_id(detection_id)
    sdk = AISDK(org)
    data = sdk.summarize_detection(detection_data)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# start-session
# ---------------------------------------------------------------------------

_EXPLAIN_START_SESSION = """\
Start an AI session using an ai_agent Hive definition as a TEMPLATE.

The hive record named by --definition supplies all the default session
configuration: prompt, model, credentials (as hive://secret/
references), tool permissions, MCP servers, environment, budgets, and
so on.  Any --option flag below overrides the matching field from the
template; the rest of the template is used as-is.

This lets you reuse one ai_agent definition as a starting point and
vary only the bits you need per-run (swap the prompt, cap the budget,
change the model, add an env var, etc.).

Override rules:
  * Scalars and lists REPLACE the template value when supplied.
  * --env values are MERGED with the template's environment (override
    values win on key collisions).
  * Omitted flags leave the template's value untouched.
  * Override values may be "hive://secret/<name>" refs (resolved
    before sending), matching D&R rule semantics.

All hive://secret/ references (in the template or in overrides) are
resolved automatically before the request is sent.

When starting a session from the CLI there is no D&R event; use --data
to supply a JSON dictionary that will be appended to the prompt as
event data.

Examples:
  limacharlie ai start-session --definition my-security-analyst

  # Reuse the template but swap the prompt.
  limacharlie ai start-session --definition my-agent \\
    --prompt "Investigate this specific alert" \\
    --name "Alert investigation"

  # Cap budget and force a specific model on top of the template.
  limacharlie ai start-session --definition my-agent \\
    --model claude-sonnet-4-6 --max-budget-usd 2.50

  # Add an env var on top of the template.
  limacharlie ai start-session --definition my-agent \\
    --env SLACK_WEBHOOK=hive://secret/slack-webhook

  # Restrict tools for this run only.
  limacharlie ai start-session --definition my-agent \\
    --allowed-tools Read,Grep --denied-tools Bash,Write
"""
register_explain("ai.start-session", _EXPLAIN_START_SESSION)


def _split_csv(value: str | None) -> list[str] | None:
    """Split a comma-separated CLI value into a list.

    Empty/whitespace-only segments are dropped.  Returns ``None`` when
    the caller did not pass the flag at all, so the SDK sees "no
    override" rather than "override with []".
    """
    if value is None:
        return None
    parts = [p.strip() for p in value.split(",")]
    return [p for p in parts if p]


def _parse_env_kv(items: tuple[str, ...]) -> dict[str, str] | None:
    """Parse ``--env KEY=VALUE`` pairs into a dict.

    Returns ``None`` when no ``--env`` flag was passed so the SDK
    doesn't clobber the template's environment with an empty dict.
    """
    if not items:
        return None
    env: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise click.BadParameter(
                f"--env value '{item}' must be in KEY=VALUE form",
                param_hint="--env",
            )
        key, _, value = item.partition("=")
        key = key.strip()
        if not key:
            raise click.BadParameter(
                f"--env value '{item}' has empty key",
                param_hint="--env",
            )
        env[key] = value
    return env


@group.command("start-session")
@click.option("--definition", required=True,
              help="Name of the ai_agent hive record to use as template.")
@click.option("--prompt", default=None, help="Replace the prompt from the definition.")
@click.option("--name", default=None, help="Replace the session name.")
@click.option("--idempotent-key", default=None, help="Deduplication key for the session.")
@click.option("--data", default=None, help="JSON dictionary of data to include with the session prompt.")
# Profile field overrides.
@click.option("--model", default=None,
              help="Replace the Anthropic model (e.g. claude-sonnet-4-6).")
@click.option("--max-turns", default=None, type=int,
              help="Replace the maximum number of agent turns.")
@click.option("--max-budget-usd", default=None, type=float,
              help="Replace the hard USD cost cap (positive float).")
@click.option("--task-budget-tokens", default=None, type=int,
              help="Replace the per-task token budget.")
@click.option("--ttl-seconds", default=None, type=int,
              help="Replace the session time-to-live in seconds.")
@click.option("--one-shot/--no-one-shot", "one_shot", default=None,
              help="Force one_shot on or off; omit to keep the template value.")
@click.option("--permission-mode", default=None,
              type=click.Choice(["acceptEdits", "plan", "bypassPermissions"]),
              help="Replace the permission mode.")
@click.option("--allowed-tools", default=None,
              help="Comma-separated list of tool names that REPLACES the template's allowed_tools.")
@click.option("--denied-tools", default=None,
              help="Comma-separated list of tool names that REPLACES the template's denied_tools.")
@click.option("--plugin", "plugins", multiple=True,
              help="Repeatable. Replaces the template's plugins list with the values given.")
@click.option("--env", "env_pairs", multiple=True,
              help="Repeatable KEY=VALUE pair merged into the template's environment. "
                   "VALUE may be hive://secret/<name>.")
# Credential overrides.
@click.option("--anthropic-key", default=None,
              help="Replace anthropic_secret. Literal key or hive://secret/<name>.")
@click.option("--lc-api-key", default=None,
              help="Replace lc_api_key_secret. Literal key or hive://secret/<name>.")
@click.option("--lc-uid", default=None,
              help="Replace lc_uid_secret. Literal UID or hive://secret/<name>.")
@pass_context
def start_session(ctx, definition, prompt, name, idempotent_key, data,
                  model, max_turns, max_budget_usd, task_budget_tokens,
                  ttl_seconds, one_shot, permission_mode,
                  allowed_tools, denied_tools, plugins, env_pairs,
                  anthropic_key, lc_api_key, lc_uid) -> None:
    import json as _json
    parsed_data = None
    if data is not None:
        parsed_data = _json.loads(data)
    plugins_override: list[str] | None = list(plugins) if plugins else None
    environment_override = _parse_env_kv(env_pairs)
    org = _get_org(ctx)
    sdk = AISDK(org)
    result = sdk.start_session(
        definition,
        prompt=prompt,
        name=name,
        idempotent_key=idempotent_key,
        data=parsed_data,
        model=model,
        max_turns=max_turns,
        max_budget_usd=max_budget_usd,
        task_budget_tokens=task_budget_tokens,
        ttl_seconds=ttl_seconds,
        one_shot=one_shot,
        permission_mode=permission_mode,
        allowed_tools=_split_csv(allowed_tools),
        denied_tools=_split_csv(denied_tools),
        plugins=plugins_override,
        environment=environment_override,
        anthropic_key=anthropic_key,
        lc_api_key=lc_api_key,
        lc_uid=lc_uid,
    )
    _output(ctx, result)


# ===========================================================================
# session subgroup – AI session lifecycle management
# ===========================================================================

_PROMPT_TRUNCATE_LEN = 120


def _truncate_prompt(text: str, max_len: int = _PROMPT_TRUNCATE_LEN) -> str:
    """Truncate a prompt string for display."""
    if not text or len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def _clean_session_for_list(session: dict) -> dict:
    """Strip heavy fields from a session dict for list display."""
    s = dict(session)
    # Replace the full prompt with a short preview.
    if "initial_prompt" in s:
        s["initial_prompt"] = _truncate_prompt(s["initial_prompt"])
    return s


@click.group("session")
def session_group() -> None:
    """Manage AI sessions (list, inspect, terminate)."""

group.add_command(session_group)


# ---------------------------------------------------------------------------
# session list
# ---------------------------------------------------------------------------

_EXPLAIN_SESSION_LIST = """\
List AI sessions for the organization.  By default every matching
session is returned; pagination is drained automatically.

Statuses: running, starting, ended.

Flags:
  --status   Filter by session status.
  --limit    Total cap on returned sessions (default: unlimited).
  --cursor   Fetch a single page starting from this cursor.  Switches
             output to a raw {sessions, next_cursor} dict so callers
             can resume pagination explicitly.  Intended for scripted
             / streaming access; most users should omit this flag.

The initial_prompt field is truncated in the listing.  Use
'ai session get --id <ID>' to see the full prompt.

Example:
  limacharlie ai session list
  limacharlie ai session list --status running
  limacharlie ai session list --limit 10
  limacharlie ai session list --cursor <CURSOR>
"""
register_explain("ai.session.list", _EXPLAIN_SESSION_LIST)


@session_group.command("list")
@click.option("--status", default=None, help="Filter by session status (running, starting, ended).")
@click.option("--limit", default=None, type=int,
              help="Total cap on returned sessions (or per-page size if --cursor is given).")
@click.option("--cursor", default=None,
              help="Fetch a single page from this cursor; disables auto-drain.")
@pass_context
def session_list(ctx, status, limit, cursor) -> None:
    org = _get_org(ctx)
    sdk = AISDK(org)
    if cursor is not None:
        # Explicit pagination: single page, raw response so the caller
        # can grab next_cursor.
        data = sdk.list_sessions_page(status=status, limit=limit, cursor=cursor)
        if "sessions" in data:
            data["sessions"] = [_clean_session_for_list(s) for s in data["sessions"]]
        _output(ctx, data)
        return
    sessions = [_clean_session_for_list(s)
                for s in sdk.list_sessions(status=status, limit=limit)]
    _output(ctx, sessions)


# ---------------------------------------------------------------------------
# session get
# ---------------------------------------------------------------------------

_EXPLAIN_SESSION_GET = """\
Get details of a specific AI session including status, model,
token usage, cost, trigger info, and end reason.

By default the initial_prompt is truncated.  Use --full-prompt
to include the entire prompt text.

Example:
  limacharlie ai session get --id <SESSION_ID>
  limacharlie ai session get --id <SESSION_ID> --full-prompt
"""
register_explain("ai.session.get", _EXPLAIN_SESSION_GET)


@session_group.command("get")
@click.option("--id", "session_id", required=True, help="Session ID.")
@click.option("--full-prompt", is_flag=True, default=False, help="Include the full initial_prompt text.")
@pass_context
def session_get(ctx, session_id, full_prompt) -> None:
    org = _get_org(ctx)
    sdk = AISDK(org)
    data = sdk.get_session(session_id)
    if not full_prompt and "session" in data:
        s = data["session"]
        if isinstance(s, dict) and "initial_prompt" in s:
            s["initial_prompt"] = _truncate_prompt(s["initial_prompt"])
    _output(ctx, data)


# ---------------------------------------------------------------------------
# session terminate
# ---------------------------------------------------------------------------

_EXPLAIN_SESSION_TERMINATE = """\
Terminate a running AI session.  The session will be stopped and
its status set to ended.

Requires the ai_agent.set permission on the organization.

Example:
  limacharlie ai session terminate --id <SESSION_ID>
"""
register_explain("ai.session.terminate", _EXPLAIN_SESSION_TERMINATE)


@session_group.command("terminate")
@click.option("--id", "session_id", required=True, help="Session ID to terminate.")
@pass_context
def session_terminate(ctx, session_id) -> None:
    org = _get_org(ctx)
    sdk = AISDK(org)
    data = sdk.terminate_session(session_id)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# session history
# ---------------------------------------------------------------------------

_EXPLAIN_SESSION_HISTORY = """\
Get the conversation history of an AI session.  Returns the
message log including user prompts, assistant responses, tool
calls and results.

By default, internal system messages (init, config, diagnostics)
are filtered out.  Use --raw to include everything.

Example:
  limacharlie ai session history --id <SESSION_ID>
  limacharlie ai session history --id <SESSION_ID> --raw
"""
register_explain("ai.session.history", _EXPLAIN_SESSION_HISTORY)

def _filter_history(messages: list[dict]) -> list[dict]:
    """Remove internal system init messages from history.

    Reuses the single source-of-truth noise set defined alongside the
    live-stream renderer in ``_ai_attach`` so both surfaces hide the
    same plumbing subtypes.
    """
    from ._ai_attach import _NOISY_SYSTEM_SUBTYPES

    filtered = []
    for m in messages:
        if m.get("type") == "system":
            payload = m.get("payload", {})
            if isinstance(payload, dict) and payload.get("subtype") in _NOISY_SYSTEM_SUBTYPES:
                continue
        filtered.append(m)
    return filtered


@session_group.command("history")
@click.option("--id", "session_id", required=True, help="Session ID.")
@click.option("--raw", is_flag=True, default=False, help="Include all messages including internal system init.")
@pass_context
def session_history(ctx, session_id, raw) -> None:
    org = _get_org(ctx)
    sdk = AISDK(org)
    data = sdk.get_session_history(session_id)
    if not raw and "messages" in data:
        data["messages"] = _filter_history(data["messages"])
    _output(ctx, data)


# ---------------------------------------------------------------------------
# session attach
# ---------------------------------------------------------------------------

_EXPLAIN_SESSION_ATTACH = """\
Attach to an AI session and stream its messages live over WebSocket.

Two endpoints are exposed by ai-sessions:

  * owner-interactive - /v1/sessions/{id}/ws
    The authenticated user must own the session.  With --interactive
    the terminal becomes a chat: type a line and press Enter to send
    a prompt.  Tool approval requests and questions from the agent
    are surfaced as interactive prompts.

  * org-scoped read-only - /v1/org/sessions/{id}/ws
    Requires the ai_agent.get permission on the session's owner org.
    Use --read-only to connect here directly.  Input is disabled.

If the owner endpoint returns 403 the command automatically falls
back to the read-only endpoint.

In the interactive input loop:
  * an empty line is ignored
  * '/interrupt' sends an interrupt message to the agent
  * '/quit' detaches from the session

Messages are colour-coded by type.  --raw dumps each message as JSON
instead, which is useful for piping to another tool.

By default a history block is rendered on connect (the messages that
preceded your attach).  Use --no-history to skip it.

Example:
  limacharlie ai session attach --id <SESSION_ID>
  limacharlie ai session attach --id <SESSION_ID> --interactive
  limacharlie ai session attach --id <SESSION_ID> --read-only
  limacharlie ai session attach --id <SESSION_ID> --raw | jq .
"""
register_explain("ai.session.attach", _EXPLAIN_SESSION_ATTACH)


@session_group.command("attach")
@click.option("--id", "session_id", required=True, help="Session ID to attach to.")
@click.option("--read-only", is_flag=True, default=False,
              help="Use the org-scoped read-only WebSocket endpoint.")
@click.option("--interactive", "-i", is_flag=True, default=False,
              help="Enable interactive input (sends stdin lines as prompts).")
@click.option("--no-history", is_flag=True, default=False,
              help="Don't render the initial history block on connect.")
@click.option("--raw", is_flag=True, default=False,
              help="Print raw JSON messages instead of pretty formatting.")
@click.option("--verbose", "-v", is_flag=True, default=False,
              help="Show plumbing system/status messages and full ISO timestamps.")
@pass_context
def session_attach(ctx, session_id, read_only, interactive, no_history, raw, verbose) -> None:
    from ._ai_attach import run_attach

    org = _get_org(ctx)
    sdk = AISDK(org)
    exit_code = run_attach(
        sdk, session_id,
        read_only=read_only,
        interactive=interactive,
        show_history=not no_history,
        raw=raw,
        verbose=verbose,
    )
    ctx.exit(exit_code)


# ===========================================================================
# usage subgroup – AI session usage tracking
# ===========================================================================

@click.group("usage")
def usage_group() -> None:
    """AI session usage tracking per API key identity."""

group.add_command(usage_group)


# ---------------------------------------------------------------------------
# usage list
# ---------------------------------------------------------------------------

_EXPLAIN_USAGE_LIST = """\
List all API key identities that have AI session usage data for
the organization.

Example:
  limacharlie ai usage list
"""
register_explain("ai.usage.list", _EXPLAIN_USAGE_LIST)


@usage_group.command("list")
@pass_context
def usage_list(ctx) -> None:
    org = _get_org(ctx)
    sdk = AISDK(org)
    data = sdk.list_usage_identities()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# usage get
# ---------------------------------------------------------------------------

_EXPLAIN_USAGE_GET = """\
Get hourly token and cost usage breakdown for a specific API key
identity.  Use 'limacharlie ai usage list' to discover available
identities.

Example:
  limacharlie ai usage get --identity my-api-key
"""
register_explain("ai.usage.get", _EXPLAIN_USAGE_GET)


@usage_group.command("get")
@click.option("--identity", required=True, help="API key identity name.")
@pass_context
def usage_get(ctx, identity) -> None:
    org = _get_org(ctx)
    sdk = AISDK(org)
    data = sdk.get_usage(identity)
    _output(ctx, data)


# ===========================================================================
# auth subgroup – per-user Claude credential management
#
# The `ai chat` command runs user-owned sessions, which require the
# caller to have Claude credentials (OAuth token or Anthropic API key)
# stored server-side.  `ai start-session` and its org-owned workflow
# are unaffected — those use an anthropic_secret from the ai_agent
# template and do not depend on these commands.
# ===========================================================================

@click.group("auth")
def auth_group() -> None:
    """Manage per-user credentials for AI sessions.

    The ``claude`` subgroup stores the Anthropic credential that
    user-owned sessions (``ai chat``) use to talk to Claude.  Org-owned
    sessions (``ai start-session``) ignore these and use the template's
    ``anthropic_secret`` instead.
    """

group.add_command(auth_group)


@click.group("claude")
def claude_auth_group() -> None:
    """Manage the authenticated user's stored Anthropic credential."""

auth_group.add_command(claude_auth_group)


# ---------------------------------------------------------------------------
# auth claude status
# ---------------------------------------------------------------------------

@claude_auth_group.command("status")
@pass_context
def claude_auth_status(ctx) -> None:
    """Show whether the authenticated user has Claude credentials stored."""
    org = _get_org(ctx)
    sdk = AISDK(org)
    _output(ctx, sdk.claude_auth_status())


# ---------------------------------------------------------------------------
# auth claude login  (interactive browser OAuth flow)
# ---------------------------------------------------------------------------

_CLAUDE_OAUTH_POLL_SECONDS = 2.0
_CLAUDE_OAUTH_POLL_TIMEOUT = 120.0


@claude_auth_group.command("login")
@pass_context
def claude_auth_login(ctx) -> None:
    """Run the interactive browser OAuth flow to store a Claude token.

    Starts a server-side OAuth job, prints the URL to visit in your
    browser, and prompts for the authorization code returned by Claude.
    On success the credential is stored server-side and usable by
    ``ai chat``.
    """
    import time

    org = _get_org(ctx)
    sdk = AISDK(org)

    start = sdk.claude_login_start()
    oauth_session_id = start.get("oauth_session_id")
    if not oauth_session_id:
        raise click.ClickException(
            f"server returned no oauth_session_id: {start}"
        )

    # Poll until the URL is ready.
    url = None
    deadline = time.monotonic() + _CLAUDE_OAUTH_POLL_TIMEOUT
    while time.monotonic() < deadline:
        resp = sdk.claude_login_get_url(oauth_session_id)
        status = resp.get("status")
        if status == "ready" and resp.get("url"):
            url = resp["url"]
            break
        if status == "failed":
            raise click.ClickException(
                f"OAuth flow failed: {resp.get('error') or resp.get('message')}"
            )
        time.sleep(_CLAUDE_OAUTH_POLL_SECONDS)
    if url is None:
        raise click.ClickException(
            "timed out waiting for OAuth URL from server"
        )

    click.echo("Open this URL in your browser, approve, then paste the code below:")
    click.echo(f"  {url}")
    code = click.prompt("Code", hide_input=True)

    result = sdk.claude_login_submit_code(oauth_session_id, code)
    if not result.get("success"):
        raise click.ClickException(
            f"server rejected OAuth code: {result.get('error') or result.get('message')}"
        )
    _output(ctx, result)


# ---------------------------------------------------------------------------
# auth claude set-key  (non-interactive, direct API key)
# ---------------------------------------------------------------------------

@claude_auth_group.command("set-key")
@click.option("--key", default=None,
              help="Anthropic API key. Literal value or hive://secret/<name>. "
                   "Mutually exclusive with --key-from-stdin.")
@click.option("--key-from-stdin", is_flag=True, default=False,
              help="Read the API key from stdin (useful for piping).")
@pass_context
def claude_auth_set_key(ctx, key, key_from_stdin) -> None:
    """Store a raw Anthropic API key for the authenticated user."""
    import sys

    if key and key_from_stdin:
        raise click.UsageError("--key and --key-from-stdin are mutually exclusive")
    if not key and not key_from_stdin:
        raise click.UsageError("one of --key or --key-from-stdin is required")
    if key_from_stdin:
        key = sys.stdin.read().strip()
    if not key:
        raise click.UsageError("API key is empty")

    org = _get_org(ctx)
    sdk = AISDK(org)
    _output(ctx, sdk.claude_set_apikey(key))


# ---------------------------------------------------------------------------
# auth claude logout
# ---------------------------------------------------------------------------

@claude_auth_group.command("logout")
@pass_context
def claude_auth_logout(ctx) -> None:
    """Remove the authenticated user's stored Claude credential."""
    org = _get_org(ctx)
    sdk = AISDK(org)
    _output(ctx, sdk.claude_logout())


# ===========================================================================
# chat – user-owned interactive session
# ===========================================================================

_EXPLAIN_CHAT = """\
Create a fresh user-owned AI session and drop into an interactive
chat.  Unlike 'ai start-session' (which runs an ai_agent template
on behalf of the organization), this command starts a blank session
owned by the authenticated user and streams an interactive WebSocket
conversation over it.

Prerequisites:
  * The user must have stored a Claude credential.  Run one of:
      limacharlie ai auth claude login        # browser OAuth
      limacharlie ai auth claude set-key ...  # raw API key

Billing and credentials:
  * Sessions created here bill against the caller's registered Claude
    credential (OAuth token or API key), not the org's anthropic_secret.

Supplying a prompt on the command line (argument or via stdin) seeds
the session; you can keep chatting afterwards by typing into stdin.
'/interrupt' and '/quit' behave as in 'ai session attach'.

Example:
  limacharlie ai chat "what sensors do I have in the last 24h?"
  echo "summarise today's detections" | limacharlie ai chat
  limacharlie ai chat --model claude-sonnet-4-6 --max-budget-usd 1.00
"""
register_explain("ai.chat", _EXPLAIN_CHAT)


@group.command("chat")
@click.argument("prompt", required=False)
@click.option("--name", default=None, help="Session name.")
@click.option("--model", default=None,
              help="Anthropic model (e.g. claude-sonnet-4-6).")
@click.option("--max-turns", default=None, type=int,
              help="Maximum number of agent turns before auto-stop.")
@click.option("--max-budget-usd", default=None, type=float,
              help="Hard USD cost cap for the session.")
@click.option("--task-budget-tokens", default=None, type=int,
              help="Per-task token budget.")
@click.option("--permission-mode", default=None,
              type=click.Choice(["acceptEdits", "plan", "bypassPermissions"]),
              help="Permission mode for tool use.")
@click.option("--allowed-tools", default=None,
              help="Comma-separated list of allowed tool names.")
@click.option("--denied-tools", default=None,
              help="Comma-separated list of denied tool names.")
@click.option("--plugin", "plugins", multiple=True,
              help="Repeatable. Plugin names to enable.")
@click.option("--idempotent-key", default=None,
              help="Deduplication key for session creation.")
@click.option("--verbose", "-v", is_flag=True, default=False,
              help="Show plumbing system/status messages and full ISO timestamps.")
@pass_context
def chat(ctx, prompt, name, model, max_turns, max_budget_usd,
         task_budget_tokens, permission_mode,
         allowed_tools, denied_tools, plugins, idempotent_key, verbose) -> None:
    from ._ai_attach import run_attach

    org = _get_org(ctx)
    sdk = AISDK(org)

    # Verify the user has Claude credentials before spending effort
    # creating a session that would immediately fail.
    status = sdk.claude_auth_status()
    if not status.get("has_credentials"):
        raise click.ClickException(
            "No Claude credentials registered for this user. Run one of:\n"
            "  limacharlie ai auth claude login\n"
            "  limacharlie ai auth claude set-key --key <ANTHROPIC_API_KEY>"
        )

    # Register is idempotent server-side; calling it here lets a
    # first-time user run `ai chat` immediately after `auth claude
    # set-key` without a separate step.
    sdk.register_user()

    # The opening prompt is the PROMPT argument; further turns come
    # from interactive stdin once the session is attached.  We do NOT
    # consume stdin as the prompt: piping multiple lines used to glue
    # them into one prompt and then leave stdin empty for follow-ups.
    initial_prompt = prompt

    plugins_override: list[str] | None = list(plugins) if plugins else None

    created = sdk.create_user_session(
        name=name,
        idempotent_key=idempotent_key,
        model=model,
        max_turns=max_turns,
        max_budget_usd=max_budget_usd,
        task_budget_tokens=task_budget_tokens,
        permission_mode=permission_mode,
        allowed_tools=_split_csv(allowed_tools),
        denied_tools=_split_csv(denied_tools),
        plugins=plugins_override,
    )
    # The POST /v1/sessions handler returns the session under a
    # "session" key (same shape as `ai session get`).  Fall back to a
    # top-level id for forward compatibility if that ever changes.
    session_obj = created.get("session") or created
    session_id = session_obj.get("id") or session_obj.get("session_id")
    if not session_id:
        raise click.ClickException(
            f"server response missing session id: {created}"
        )
    click.echo(f"Started session {session_id}", err=True)

    exit_code = run_attach(
        sdk, session_id,
        read_only=False,
        interactive=True,
        show_history=False,
        raw=False,
        verbose=verbose,
        initial_prompt=initial_prompt,
    )
    ctx.exit(exit_code)


# ===========================================================================
# chats subgroup – manage user-owned sessions (the counterpart to
# `ai session`, which manages org-owned sessions).  Mirrors the org
# commands one-for-one but routes through the user-scoped REST API.
# ===========================================================================

@click.group("chats")
def chats_group() -> None:
    """Manage user-owned AI sessions (started via ``ai chat``).

    The ``ai session`` group manages org-owned sessions (started via
    ``ai start-session``); this group is the same surface for the
    user-owned sessions that ``ai chat`` creates.  Sessions of one
    kind are not visible from the other group's commands.
    """

group.add_command(chats_group)


# ---------------------------------------------------------------------------
# chats list
# ---------------------------------------------------------------------------

@chats_group.command("list")
@click.option("--status", default=None,
              help="Filter by session status (running, starting, ended).")
@click.option("--limit", default=None, type=int,
              help="Total cap on returned sessions (or per-page size if --cursor is given).")
@click.option("--cursor", default=None,
              help="Fetch a single page from this cursor; disables auto-drain.")
@pass_context
def chats_list(ctx, status, limit, cursor) -> None:
    """List the authenticated user's AI sessions.

    By default every matching session is returned; pagination is
    drained automatically.  Pass --cursor to fetch a single page and
    receive the raw {sessions, next_cursor} dict for explicit
    pagination control (intended for scripted access).
    """
    org = _get_org(ctx)
    sdk = AISDK(org)
    if cursor is not None:
        data = sdk.list_user_sessions_page(status=status, limit=limit,
                                           cursor=cursor)
        if "sessions" in data:
            data["sessions"] = [_clean_session_for_list(s) for s in data["sessions"]]
        _output(ctx, data)
        return
    sessions = [_clean_session_for_list(s)
                for s in sdk.list_user_sessions(status=status, limit=limit)]
    _output(ctx, sessions)


# ---------------------------------------------------------------------------
# chats get
# ---------------------------------------------------------------------------

@chats_group.command("get")
@click.option("--id", "session_id", required=True, help="Session ID.")
@click.option("--full-prompt", is_flag=True, default=False,
              help="Include the full initial_prompt text.")
@pass_context
def chats_get(ctx, session_id, full_prompt) -> None:
    """Get details of one of the user's AI sessions."""
    org = _get_org(ctx)
    sdk = AISDK(org)
    data = sdk.get_user_session(session_id)
    if not full_prompt and "session" in data:
        s = data["session"]
        if isinstance(s, dict) and "initial_prompt" in s:
            s["initial_prompt"] = _truncate_prompt(s["initial_prompt"])
    _output(ctx, data)


# ---------------------------------------------------------------------------
# chats terminate
# ---------------------------------------------------------------------------

@chats_group.command("terminate")
@click.option("--id", "session_id", required=True,
              help="Session ID to terminate.")
@pass_context
def chats_terminate(ctx, session_id) -> None:
    """Terminate one of the user's running AI sessions."""
    org = _get_org(ctx)
    sdk = AISDK(org)
    _output(ctx, sdk.terminate_user_session(session_id))


# ---------------------------------------------------------------------------
# chats history
# ---------------------------------------------------------------------------

@chats_group.command("history")
@click.option("--id", "session_id", required=True, help="Session ID.")
@click.option("--raw", is_flag=True, default=False,
              help="Include all messages including internal system init.")
@pass_context
def chats_history(ctx, session_id, raw) -> None:
    """Show the conversation history of one of the user's AI sessions."""
    org = _get_org(ctx)
    sdk = AISDK(org)
    data = sdk.get_user_session_history(session_id)
    if not raw and "messages" in data:
        data["messages"] = _filter_history(data["messages"])
    _output(ctx, data)
