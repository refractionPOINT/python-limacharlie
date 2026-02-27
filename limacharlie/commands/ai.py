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
