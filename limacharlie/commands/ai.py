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
    client = Client(oid=ctx.obj.oid, environment=ctx.obj.environment)
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
Start an AI session using an ai_agent Hive definition.  The definition
contains the full session configuration including prompt, model,
credentials (as hive://secret/ references), tool permissions, and
MCP server configs.

All hive://secret/ references in the definition are resolved
automatically before the session is created.

When starting a session from the CLI (as opposed to a D&R rule),
there is no event to apply the definition's data transform to.
Use --data to supply a JSON dictionary that will be appended to
the prompt as event data.

Example:
  limacharlie ai start-session --definition my-security-analyst

  limacharlie ai start-session --definition my-agent \\
    --prompt "Investigate this specific alert" \\
    --name "Alert investigation"

  limacharlie ai start-session --definition my-agent \\
    --data '{"hostname": "srv-01", "alert_id": "abc-123"}'
"""
register_explain("ai.start-session", _EXPLAIN_START_SESSION)


@group.command("start-session")
@click.option("--definition", required=True, help="Name of the ai_agent hive record to use.")
@click.option("--prompt", default=None, help="Override the prompt from the definition.")
@click.option("--name", default=None, help="Override the session name.")
@click.option("--idempotent-key", default=None, help="Deduplication key for the session.")
@click.option("--data", default=None, help="JSON dictionary of data to include with the session prompt.")
@pass_context
def start_session(ctx, definition, prompt, name, idempotent_key, data) -> None:
    import json as _json
    parsed_data = None
    if data is not None:
        parsed_data = _json.loads(data)
    org = _get_org(ctx)
    sdk = AISDK(org)
    result = sdk.start_session(definition, prompt=prompt, name=name,
                               idempotent_key=idempotent_key, data=parsed_data)
    _output(ctx, result)


# ===========================================================================
# session subgroup – AI session lifecycle management
# ===========================================================================

@click.group("session")
def session_group() -> None:
    """Manage AI sessions (list, inspect, terminate)."""

group.add_command(session_group)


# ---------------------------------------------------------------------------
# session list
# ---------------------------------------------------------------------------

_EXPLAIN_SESSION_LIST = """\
List AI sessions for the organization.  By default all sessions are
returned; use --status to filter by state.

Statuses: running, starting, ended.

Pagination is supported via --limit and --cursor.

Example:
  limacharlie ai session list
  limacharlie ai session list --status running
  limacharlie ai session list --limit 10
"""
register_explain("ai.session.list", _EXPLAIN_SESSION_LIST)


@session_group.command("list")
@click.option("--status", default=None, help="Filter by session status (running, starting, ended).")
@click.option("--limit", default=None, type=int, help="Max results per page (1-200, default 50).")
@click.option("--cursor", default=None, help="Pagination cursor from a previous response.")
@pass_context
def session_list(ctx, status, limit, cursor) -> None:
    org = _get_org(ctx)
    sdk = AISDK(org)
    data = sdk.list_sessions(status=status, limit=limit, cursor=cursor)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# session get
# ---------------------------------------------------------------------------

_EXPLAIN_SESSION_GET = """\
Get details of a specific AI session including status, model,
token usage, cost, trigger info, and end reason.

Example:
  limacharlie ai session get --id <SESSION_ID>
"""
register_explain("ai.session.get", _EXPLAIN_SESSION_GET)


@session_group.command("get")
@click.option("--id", "session_id", required=True, help="Session ID.")
@pass_context
def session_get(ctx, session_id) -> None:
    org = _get_org(ctx)
    sdk = AISDK(org)
    data = sdk.get_session(session_id)
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
Get the conversation history of an AI session.  Returns the full
message log including user prompts, assistant responses, tool
calls and results.

Example:
  limacharlie ai session history --id <SESSION_ID>
"""
register_explain("ai.session.history", _EXPLAIN_SESSION_HISTORY)


@session_group.command("history")
@click.option("--id", "session_id", required=True, help="Session ID.")
@pass_context
def session_history(ctx, session_id) -> None:
    org = _get_org(ctx)
    sdk = AISDK(org)
    data = sdk.get_session_history(session_id)
    _output(ctx, data)


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
