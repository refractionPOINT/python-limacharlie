"""Feedback commands for LimaCharlie CLI v2.

Commands for sending interactive feedback requests (approval,
acknowledgement, free-form question) to external channels and managing
feedback channel configuration via the ext-feedback extension.
"""

from __future__ import annotations

import json
from typing import Any

import click

from ..cli import pass_context
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.feedback import Feedback
from ..output import format_output, detect_output_format
from ..discovery import register_explain


# ---------------------------------------------------------------------------
# Explain texts
# ---------------------------------------------------------------------------

_EXPLAIN_REQUEST_APPROVAL = """\
Send a simple Approve/Deny feedback request to a channel.

When the recipient responds, the result is dispatched to the
specified destination: either added as a note to a case or used
to trigger a playbook.

Channels must be configured first (see 'feedback channel' commands).
Channel types: web (built-in UI), slack, email, telegram, ms_teams.

For web channels, the response includes a shareable URL.

Optionally attach JSON data that will be included in the response
payload when the recipient approves or denies:
  --approved-content '{"action": "isolate"}'
  --denied-content '{"action": "skip"}'

Timeout: use --timeout to auto-respond after N seconds if no human
responds.  Requires --timeout-choice (approved or denied).
  --timeout 300 --timeout-choice denied
  --timeout 300 --timeout-choice denied --timeout-content '{"reason": "timeout"}'

Examples:
  limacharlie feedback request-approval \\
      --channel ops-slack --question "Isolate host-01?" \\
      --destination case --case-id 42
  limacharlie feedback request-approval \\
      --channel web-default --question "Approve remediation?" \\
      --destination playbook --playbook remediate-host
  limacharlie feedback request-approval \\
      --channel ops-slack --question "Block IP 10.0.0.1?" \\
      --destination playbook --playbook block-ip \\
      --approved-content '{"ip": "10.0.0.1"}'
  limacharlie feedback request-approval \\
      --channel ops-slack --question "Isolate host?" \\
      --destination case --case-id 42 \\
      --timeout 300 --timeout-choice denied
"""

_EXPLAIN_REQUEST_ACK = """\
Send an acknowledgement request (single Acknowledge button) to a
channel.

When acknowledged, the result is dispatched to the specified
destination (case note or playbook trigger).

Optionally attach JSON data included in the response payload:
  --acknowledged-content '{"status": "seen"}'

Timeout: use --timeout to auto-acknowledge after N seconds if no
human responds.
  --timeout 300
  --timeout 300 --timeout-content '{"status": "auto-ack", "reason": "timeout"}'

Examples:
  limacharlie feedback request-ack \\
      --channel ops-slack --question "Alert: lateral movement detected" \\
      --destination case --case-id 42
  limacharlie feedback request-ack \\
      --channel email-oncall --question "Acknowledge incident #7" \\
      --destination playbook --playbook ack-handler
  limacharlie feedback request-ack \\
      --channel ops-slack --question "Ack alert X" \\
      --destination case --case-id 42 --timeout 600
"""

_EXPLAIN_REQUEST_QUESTION = """\
Send a question with a free-form text input field to a channel.

The respondent types a text answer which is dispatched to the
specified destination (case note or playbook trigger).

Timeout: use --timeout to auto-answer after N seconds if no human
responds.  --timeout-content is required for question type (provides
the automatic answer).
  --timeout 300 --timeout-content '{"answer": "no response", "reason": "timeout"}'

Examples:
  limacharlie feedback request-question \\
      --channel ops-slack --question "What is the root cause?" \\
      --destination case --case-id 42
  limacharlie feedback request-question \\
      --channel web-default \\
      --question "Provide remediation steps for host-01" \\
      --destination playbook --playbook collect-input
  limacharlie feedback request-question \\
      --channel ops-slack --question "Root cause?" \\
      --destination case --case-id 42 \\
      --timeout 300 --timeout-content '{"answer": "no response"}'
"""

_EXPLAIN_CHANNEL_LIST = """\
List all configured feedback channels for the organization.

Channels define where feedback requests are sent. Each channel has
a name, type (web, slack, email, telegram, ms_teams), and an optional
Tailored Output name that holds the channel credentials.

The web channel type is built-in and does not require a Tailored
Output.

Example:
  limacharlie feedback channel list
"""

_EXPLAIN_CHANNEL_ADD = """\
Add a feedback channel to the organization's ext-feedback config.

Channel types and their Tailored Output requirements:
  web       - No output needed (built-in web UI)
  slack     - Output with slack_api_token, slack_channel
  email     - Output with dest_host, dest_email, and optional SMTP creds
  telegram  - Output with bot_token, chat_id
  ms_teams  - Output with webhook_url

The --output-name is required for all channel types except web.

Examples:
  limacharlie feedback channel add \\
      --name web-default --type web
  limacharlie feedback channel add \\
      --name ops-slack --type slack --output-name slack-soc
  limacharlie feedback channel add \\
      --name email-oncall --type email --output-name smtp-oncall
  limacharlie feedback channel add \\
      --name tg-alerts --type telegram --output-name telegram-bot
"""

_EXPLAIN_CHANNEL_REMOVE = """\
Remove a feedback channel from the organization's ext-feedback config.

This does not delete the associated Tailored Output.

Example:
  limacharlie feedback channel remove --name ops-slack
"""

register_explain("feedback.request-approval", _EXPLAIN_REQUEST_APPROVAL)
register_explain("feedback.request-ack", _EXPLAIN_REQUEST_ACK)
register_explain("feedback.request-question", _EXPLAIN_REQUEST_QUESTION)
register_explain("feedback.channel.list", _EXPLAIN_CHANNEL_LIST)
register_explain("feedback.channel.add", _EXPLAIN_CHANNEL_ADD)
register_explain("feedback.channel.remove", _EXPLAIN_CHANNEL_REMOVE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _output(ctx: click.Context, data: Any) -> None:
    fmt = ctx.obj.output_format or detect_output_format()
    if not ctx.obj.quiet:
        click.echo(format_output(data, fmt))


def _get_feedback(ctx: click.Context) -> Feedback:
    client = Client(oid=ctx.obj.oid, environment=ctx.obj.environment, print_debug_fn=ctx.obj.debug_fn, debug_full_response=ctx.obj.debug_full, debug_curl=ctx.obj.debug_curl, debug_verbose=ctx.obj.debug_verbose)
    org = Organization(client)
    return Feedback(org)


# ---------------------------------------------------------------------------
# Shared option values
# ---------------------------------------------------------------------------

_DESTINATION_CHOICES = click.Choice(["case", "playbook"], case_sensitive=False)
_CHANNEL_TYPE_CHOICES = click.Choice(
    ["web", "slack", "email", "telegram", "ms_teams"],
    case_sensitive=False,
)
_TIMEOUT_CHOICE_CHOICES = click.Choice(["approved", "denied"], case_sensitive=False)


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------

@click.group("feedback")
def group() -> None:
    """Manage interactive feedback requests (ext-feedback).

    Send approval prompts, acknowledgement requests, or free-form
    questions to external channels (Slack, Email, Telegram, Teams,
    or built-in Web UI).  Responses are dispatched to a case or
    playbook.

    Use 'feedback channel' subcommands to configure channels before
    sending requests.
    """


# ---------------------------------------------------------------------------
# request-approval
# ---------------------------------------------------------------------------

@group.command("request-approval")
@click.option("--channel", required=True, help="Name of the configured feedback channel.")
@click.option("--question", required=True, help="Prompt to present to the respondent.")
@click.option("--destination", required=True, type=_DESTINATION_CHOICES,
              help="Response destination: 'case' or 'playbook'.")
@click.option("--case-id", default=None, help="Case number (required when destination is 'case').")
@click.option("--playbook", "playbook_name", default=None,
              help="Playbook name (required when destination is 'playbook').")
@click.option("--approved-content", default=None,
              help="JSON data included when approved.")
@click.option("--denied-content", default=None,
              help="JSON data included when denied.")
@click.option("--timeout", "timeout_seconds", default=None, type=int,
              help="Auto-respond after N seconds if no response (minimum 60).")
@click.option("--timeout-choice", default=None, type=_TIMEOUT_CHOICE_CHOICES,
              help="Choice on timeout: 'approved' or 'denied' (required with --timeout).")
@click.option("--timeout-content", default=None,
              help="JSON data for the timeout response (overrides choice content).")
@pass_context
def request_approval(ctx, channel, question, destination, case_id,
                     playbook_name, approved_content, denied_content,
                     timeout_seconds, timeout_choice, timeout_content) -> None:
    """Send an Approve/Deny feedback request.

    Examples:
        limacharlie feedback request-approval \\
            --channel ops-slack --question "Isolate host?" \\
            --destination case --case-id 42
        limacharlie feedback request-approval \\
            --channel web-default --question "Approve?" \\
            --destination playbook --playbook my-playbook \\
            --timeout 300 --timeout-choice denied
    """
    approved = None
    if approved_content is not None:
        try:
            approved = json.loads(approved_content)
        except json.JSONDecodeError as exc:
            raise click.BadParameter(
                f"invalid JSON: {exc}", param_hint="--approved-content",
            )
    denied = None
    if denied_content is not None:
        try:
            denied = json.loads(denied_content)
        except json.JSONDecodeError as exc:
            raise click.BadParameter(
                f"invalid JSON: {exc}", param_hint="--denied-content",
            )
    tc = None
    if timeout_content is not None:
        try:
            tc = json.loads(timeout_content)
        except json.JSONDecodeError as exc:
            raise click.BadParameter(
                f"invalid JSON: {exc}", param_hint="--timeout-content",
            )
    fb = _get_feedback(ctx)
    data = fb.request_simple_approval(
        channel, question, destination,
        case_id=case_id,
        playbook_name=playbook_name,
        approved_content=approved,
        denied_content=denied,
        timeout_seconds=timeout_seconds,
        timeout_choice=timeout_choice,
        timeout_content=tc,
    )
    _output(ctx, data)


# ---------------------------------------------------------------------------
# request-ack
# ---------------------------------------------------------------------------

@group.command("request-ack")
@click.option("--channel", required=True, help="Name of the configured feedback channel.")
@click.option("--question", required=True, help="Prompt to present to the respondent.")
@click.option("--destination", required=True, type=_DESTINATION_CHOICES,
              help="Response destination: 'case' or 'playbook'.")
@click.option("--case-id", default=None, help="Case number (required when destination is 'case').")
@click.option("--playbook", "playbook_name", default=None,
              help="Playbook name (required when destination is 'playbook').")
@click.option("--acknowledged-content", default=None,
              help="JSON data included when acknowledged.")
@click.option("--timeout", "timeout_seconds", default=None, type=int,
              help="Auto-acknowledge after N seconds if no response (minimum 60).")
@click.option("--timeout-content", default=None,
              help="JSON data for the timeout response (overrides acknowledged_content).")
@pass_context
def request_ack(ctx, channel, question, destination, case_id,
                playbook_name, acknowledged_content,
                timeout_seconds, timeout_content) -> None:
    """Send an acknowledgement request.

    Examples:
        limacharlie feedback request-ack \\
            --channel ops-slack --question "Ack alert X" \\
            --destination case --case-id 42
        limacharlie feedback request-ack \\
            --channel ops-slack --question "Ack alert X" \\
            --destination case --case-id 42 --timeout 600
    """
    ack_content = None
    if acknowledged_content is not None:
        try:
            ack_content = json.loads(acknowledged_content)
        except json.JSONDecodeError as exc:
            raise click.BadParameter(
                f"invalid JSON: {exc}", param_hint="--acknowledged-content",
            )
    tc = None
    if timeout_content is not None:
        try:
            tc = json.loads(timeout_content)
        except json.JSONDecodeError as exc:
            raise click.BadParameter(
                f"invalid JSON: {exc}", param_hint="--timeout-content",
            )
    fb = _get_feedback(ctx)
    data = fb.request_acknowledgement(
        channel, question, destination,
        case_id=case_id,
        playbook_name=playbook_name,
        acknowledged_content=ack_content,
        timeout_seconds=timeout_seconds,
        timeout_content=tc,
    )
    _output(ctx, data)


# ---------------------------------------------------------------------------
# request-question
# ---------------------------------------------------------------------------

@group.command("request-question")
@click.option("--channel", required=True, help="Name of the configured feedback channel.")
@click.option("--question", required=True, help="Question to present to the respondent.")
@click.option("--destination", required=True, type=_DESTINATION_CHOICES,
              help="Response destination: 'case' or 'playbook'.")
@click.option("--case-id", default=None, help="Case number (required when destination is 'case').")
@click.option("--playbook", "playbook_name", default=None,
              help="Playbook name (required when destination is 'playbook').")
@click.option("--timeout", "timeout_seconds", default=None, type=int,
              help="Auto-answer after N seconds if no response (minimum 60).")
@click.option("--timeout-content", default=None,
              help="JSON data for the timeout response (required with --timeout for questions).")
@pass_context
def request_question(ctx, channel, question, destination, case_id,
                     playbook_name, timeout_seconds, timeout_content) -> None:
    """Send a question for free-form text response.

    Examples:
        limacharlie feedback request-question \\
            --channel ops-slack --question "Root cause?" \\
            --destination case --case-id 42
        limacharlie feedback request-question \\
            --channel ops-slack --question "Root cause?" \\
            --destination case --case-id 42 \\
            --timeout 300 --timeout-content '{"answer": "no response"}'
    """
    tc = None
    if timeout_content is not None:
        try:
            tc = json.loads(timeout_content)
        except json.JSONDecodeError as exc:
            raise click.BadParameter(
                f"invalid JSON: {exc}", param_hint="--timeout-content",
            )
    fb = _get_feedback(ctx)
    data = fb.request_question(
        channel, question, destination,
        case_id=case_id,
        playbook_name=playbook_name,
        timeout_seconds=timeout_seconds,
        timeout_content=tc,
    )
    _output(ctx, data)


# ---------------------------------------------------------------------------
# channel subgroup
# ---------------------------------------------------------------------------

@group.group("channel")
def channel_group() -> None:
    """Manage feedback channels.

    Channels define where feedback requests are delivered.
    Each channel has a name, type, and optional Tailored Output
    with the channel's credentials.
    """


# ---------------------------------------------------------------------------
# channel list
# ---------------------------------------------------------------------------

@channel_group.command("list")
@pass_context
def channel_list(ctx) -> None:
    """List configured feedback channels.

    Example:
        limacharlie feedback channel list
    """
    fb = _get_feedback(ctx)
    data = fb.list_channels()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# channel add
# ---------------------------------------------------------------------------

@channel_group.command("add")
@click.option("--name", required=True, help="Unique channel name.")
@click.option("--type", "channel_type", required=True, type=_CHANNEL_TYPE_CHOICES,
              help="Channel type.")
@click.option("--output-name", default=None,
              help="Tailored Output name with channel credentials (required for non-web types).")
@pass_context
def channel_add(ctx, name, channel_type, output_name) -> None:
    """Add a feedback channel.

    Examples:
        limacharlie feedback channel add --name web-default --type web
        limacharlie feedback channel add \\
            --name ops-slack --type slack --output-name slack-soc
    """
    fb = _get_feedback(ctx)
    data = fb.add_channel(name, channel_type, output_name=output_name)
    if not ctx.obj.quiet:
        click.echo(f"Channel '{name}' added.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# channel remove
# ---------------------------------------------------------------------------

@channel_group.command("remove")
@click.option("--name", required=True, help="Channel name to remove.")
@pass_context
def channel_remove(ctx, name) -> None:
    """Remove a feedback channel.

    Example:
        limacharlie feedback channel remove --name ops-slack
    """
    fb = _get_feedback(ctx)
    data = fb.remove_channel(name)
    if not ctx.obj.quiet:
        click.echo(f"Channel '{name}' removed.")
    _output(ctx, data)
