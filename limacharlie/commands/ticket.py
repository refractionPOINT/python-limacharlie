"""Ticket commands for LimaCharlie CLI v2.

Commands for managing SOC tickets: lifecycle management, investigation
tracking (entities, telemetry, artifacts), reporting, and configuration
via the LimaCharlie Ticketing extension.
"""

from __future__ import annotations

import base64
import json
import os
import sys
from typing import Any
from urllib.request import urlopen

import click
import yaml

from ..cli import pass_context
from ..client import Client
from ..sdk.artifacts import Artifacts
from ..sdk.organization import Organization
from ..sdk.sensor import Sensor
from ..sdk.ticketing import Ticketing
from ..output import format_output, detect_output_format
from ..discovery import register_explain


# ---------------------------------------------------------------------------
# Explain texts
# ---------------------------------------------------------------------------

_EXPLAIN_LIST = """\
List tickets for the organization with optional filtering, sorting,
and pagination.

Filters (all repeatable/comma-separated):
  --status    new, acknowledged, in_progress, escalated, resolved, closed
  --severity  critical, high, medium, low
  --classification  pending, true_positive, false_positive
  --assignee  filter by assignee email
  --search    full-text search in detection_cat and hostname
  --sid       filter to tickets with any detection from this sensor ID
  --tag       filter by tag (repeat for AND logic)

Sorting:
  --sort      created_at (default), severity, ticket_number
  --order     asc, desc (default)

Pagination:
  --limit     page size (1-200, default 50)
  --cursor    page token from previous response

The response includes total_counts showing status distribution
for the current filter, useful for building dashboards.

Examples:
  limacharlie ticket list
  limacharlie ticket list --status new,acknowledged --severity critical,high
  limacharlie ticket list --assignee alice@example.com --sort severity
  limacharlie ticket list --search "mimikatz" --limit 20
  limacharlie ticket list --tag phishing --tag urgent
"""

_EXPLAIN_GET = """\
Get a single ticket with its full event timeline.  Returns the
complete ticket record plus an ordered list of all events (status
changes, notes, entity additions, etc.).

The event timeline provides a full audit trail of the ticket's
lifecycle including who made each change and when.

Examples:
  limacharlie ticket get --id 42
"""

_EXPLAIN_UPDATE = """\
Update a ticket's fields.  Only provided fields are changed;
omitted fields are left untouched.

Updatable fields:
  --status           new, acknowledged, in_progress, escalated,
                     resolved, closed (state machine enforced)
  --assignee         email of the assignee
  --classification   pending, true_positive, false_positive
  --escalation-group arbitrary group name for escalation routing
  --investigation-id link to a LimaCharlie investigation
  --summary          investigation findings (max 8192 chars)
  --conclusion       root cause & remediation (max 8192 chars)
  --tag              add/replace tags (repeatable; see ticket tag subcommand)

Status transitions follow a state machine:
  new -> acknowledged, in_progress, escalated, closed
  acknowledged -> in_progress, escalated, closed
  in_progress -> escalated, resolved, closed
  escalated -> in_progress, resolved, closed
  resolved -> closed, in_progress (reopen)
  closed -> (terminal)

Examples:
  limacharlie ticket update --id 42 --status acknowledged
  limacharlie ticket update --id 42 --assignee alice@example.com
  limacharlie ticket update --id 42 --status resolved \\
      --classification true_positive \\
      --conclusion "Contained via network isolation"
"""

_EXPLAIN_ADD_NOTE = """\
Add a note to a ticket.  Notes support categorization for structured
investigation workflows.

Note types:
  general      - General notes (default)
  analysis     - Threat analysis findings
  remediation  - Remediation steps taken or recommended
  escalation   - Escalation context and reasoning
  handoff      - Shift handoff notes

Provide content via --content, --input-file, or stdin.

Examples:
  limacharlie ticket add-note --id 42 --content "Initial triage complete"
  limacharlie ticket add-note --id 42 --type analysis \\
      --content "Confirmed C2 beacon to 10.0.0.1"
  echo "Handoff notes" | limacharlie ticket add-note --id 42 --type handoff
"""

_EXPLAIN_BULK_UPDATE = """\
Batch update up to 200 tickets at once.  Provide ticket numbers as a
comma-separated list or via --input-file (one number per line or JSON
array).

Only status and classification can be set in bulk.

Examples:
  limacharlie ticket bulk-update --numbers 1,2,3 \\
      --status closed --classification false_positive
  limacharlie ticket bulk-update --input-file ticket_numbers.txt --status resolved
"""

_EXPLAIN_MERGE = """\
Merge multiple source tickets into a single target ticket.  This
copies all investigation content (entities, telemetry, artifacts,
notes) from the source tickets into the target and marks the source
tickets with status 'merged' (terminal).

This is useful for consolidating duplicate tickets created from
related detections.

Examples:
  limacharlie ticket merge --target 10 --sources 11,12,13
"""

_EXPLAIN_ENTITY_LIST = """\
List all entities (IOCs) attached to a ticket.  Entities represent
indicators of compromise found during investigation.

Entity types: ip, domain, hash, url, user, email, file, process,
registry, other.

Each entity has a verdict: malicious, suspicious, benign, unknown,
informational.

Example:
  limacharlie ticket entity list --ticket 42
"""

_EXPLAIN_ENTITY_ADD = """\
Add an entity (IOC) to a ticket.  Duplicate type+value pairs on the
same ticket are rejected (409).

Required: --type and --value.  Optional: --name, --verdict, --context,
--first-seen, --last-seen (RFC3339 timestamps).

Entity values are normalized (lowercased) for IP, domain, hash, and
email types.

Examples:
  limacharlie ticket entity add --ticket 42 \\
      --type ip --value "10.0.0.1" --verdict malicious
  limacharlie ticket entity add --ticket 42 \\
      --type hash --value "d41d8cd98f00b204e9800998ecf8427e" \\
      --verdict suspicious --context "Found in startup folder"
"""

_EXPLAIN_ENTITY_UPDATE = """\
Update an existing entity on a ticket.

Updatable fields: --name, --verdict, --context, --first-seen, --last-seen.

Example:
  limacharlie ticket entity update --ticket 42 --entity-id <EID> \\
      --verdict malicious --context "Confirmed C2 server"
"""

_EXPLAIN_ENTITY_REMOVE = """\
Remove an entity from a ticket.

Example:
  limacharlie ticket entity remove --ticket 42 --entity-id <EID>
"""

_EXPLAIN_ENTITY_SEARCH = """\
Search for an entity across all tickets in accessible organizations.
Returns all tickets containing the given entity type+value pair.

Useful for pivoting: "which other tickets reference this IP?"

Examples:
  limacharlie ticket entity search --type ip --value "10.0.0.1"
  limacharlie ticket entity search --type domain --value "evil.com"
"""

_EXPLAIN_TELEMETRY_LIST = """\
List telemetry event references linked to a ticket.  These reference
LimaCharlie events by atom+sid without storing the full payload.

Example:
  limacharlie ticket telemetry list --ticket 42
"""

_EXPLAIN_TELEMETRY_ADD = """\
Link a LimaCharlie telemetry event to a ticket.

Pass either (--atom + --sid) for a bare reference, or --event with a
full LC event JSON object for automatic field extraction (routing.this
→ atom, routing.sid → sid, routing.event_type → event_type).

Optional: --event-type, --event-summary, --verdict, --relevance.

Examples:
  limacharlie ticket telemetry add --ticket 42 \\
      --atom <ATOM_UUID> --sid <SENSOR_ID> \\
      --event-type NEW_PROCESS --verdict suspicious
  limacharlie ticket telemetry add --ticket 42 \\
      --event '<full LC event JSON>'
"""

_EXPLAIN_TELEMETRY_UPDATE = """\
Update a telemetry reference on a ticket.

Updatable fields: --event-summary, --verdict, --relevance.

Example:
  limacharlie ticket telemetry update --ticket 42 \\
      --telemetry-id <TID> --verdict malicious
"""

_EXPLAIN_TELEMETRY_REMOVE = """\
Remove a telemetry reference from a ticket.

Example:
  limacharlie ticket telemetry remove --ticket 42 --telemetry-id <TID>
"""

_EXPLAIN_ARTIFACT_LIST = """\
List forensic artifact references on a ticket.  Artifacts reference
external forensic data (PCAPs, memory dumps, disk images, etc.)
without storing the actual files.

Example:
  limacharlie ticket artifact list --ticket 42
"""

_EXPLAIN_ARTIFACT_ADD = """\
Add a forensic artifact reference to a ticket.

The --type field is free-form (e.g., pcap, memory_dump, disk_image,
log_export).  Optional: --description, --verdict.

Examples:
  limacharlie ticket artifact add --ticket 42 \\
      --type pcap --description "Network capture during incident"
  limacharlie ticket artifact add --ticket 42 \\
      --type memory_dump --verdict suspicious \\
      --description "Process memory from PID 1234"
"""

_EXPLAIN_ARTIFACT_REMOVE = """\
Remove a forensic artifact reference from a ticket.

Example:
  limacharlie ticket artifact remove --ticket 42 --artifact-id <AID>
"""

_EXPLAIN_DETECTION_LIST = """\
List detections linked to a ticket.

Example:
  limacharlie ticket detection list --ticket 42
"""

_EXPLAIN_DETECTION_ADD = """\
Link an additional detection to a ticket.  Pass either --detection-id
for a bare reference or --detection with a full detection JSON object
for automatic field extraction (detect_id, cat, routing.sid,
routing.hostname extracted by the backend).

At least one of --detection-id or --detection is required.

Examples:
  limacharlie ticket detection add --ticket 42 \\
      --detection-id <DETECTION_ID>
  limacharlie ticket detection add --ticket 42 \\
      --detection '<full detection JSON>'
  limacharlie ticket detection add --ticket 42 \\
      --detection-id <DETECTION_ID> \\
      --detection-cat "lateral_movement" --hostname "ws-01"
"""

_EXPLAIN_DETECTION_REMOVE = """\
Remove a detection link from a ticket.

Example:
  limacharlie ticket detection remove --ticket 42 \\
      --detection-id <DETECTION_ID>
"""

_EXPLAIN_REPORT = """\
Generate a comprehensive SOC performance report including MTTA,
MTTR, TP/FP rates, volume metrics, repeat offenders, and top
detection categories.

A time range is required via --from and --to (RFC3339 format).
Use --group-by to segment data (e.g., by severity or region).

Examples:
  limacharlie ticket report \\
      --from 2026-01-01T00:00:00Z --to 2026-02-01T00:00:00Z
  limacharlie ticket report \\
      --from 2026-01-01T00:00:00Z --to 2026-02-01T00:00:00Z \\
      --group-by severity
"""

_EXPLAIN_DASHBOARD = """\
Get real-time ticket counts by status and severity, including
SLA breach counts.  Useful for building operational dashboards
and monitoring SOC workload.

Example:
  limacharlie ticket dashboard
"""

_EXPLAIN_CONFIG_GET = """\
Get the organization's ticketing configuration.

Returns severity_mapping, SLA thresholds (mtta/mttr per severity),
retention_days, and auto_close_resolved_after_days.

Example:
  limacharlie ticket config-get
"""

_EXPLAIN_CONFIG_SET = """\
Update the organization's ticketing configuration.  Provide data
via --input-file (JSON/YAML) or stdin.

Configurable fields:
  severity_mapping:
    critical_min: 8   # priorities >= 8 -> Critical
    high_min: 5
    medium_min: 3
  sla_config:
    critical: {mtta_minutes: 15, mttr_minutes: 240}
    high:     {mtta_minutes: 15, mttr_minutes: 720}
    medium:   {mtta_minutes: 60, mttr_minutes: 1440}
    low:      {mtta_minutes: 100, mttr_minutes: 2800}
  retention_days: 90
  auto_close_resolved_after_days: 30

Examples:
  limacharlie ticket config-set --input-file config.yaml
  cat config.json | limacharlie ticket config-set
"""

_EXPLAIN_ASSIGNEES = """\
List all unique assignee emails across tickets in the organization.
Useful for populating assignee dropdowns or verifying team coverage.

Example:
  limacharlie ticket assignees
"""

_EXPLAIN_EXPORT = """\
Export a ticket with all its components in a single JSON object.
Fetches the ticket record (with event timeline), linked detections,
entities (IOCs), telemetry references, and forensic artifacts in one
call.

This is a convenience command that aggregates data from multiple
endpoints into a single output for backup, migration, or offline
analysis.

Without --with-data the combined JSON is printed to stdout.

With --with-data <DIR> the command creates a directory with the full
ticket data including the actual detection records, telemetry events,
and artifact binaries:

  <DIR>/
    ticket.json        ticket record, timeline, entities
    detections/        one JSON file per linked detection
    telemetry/         one JSON file per linked telemetry event
    artifacts/         downloaded artifact binaries

Fetches that fail (e.g. expired data) emit a warning on stderr and
are skipped.

Examples:
  limacharlie ticket export --id 42
  limacharlie ticket export --id 42 --output json > ticket.json
  limacharlie ticket export --id 42 --with-data ./ticket-export
"""

_EXPLAIN_CREATE = """\
Create a new SOC ticket.  Pass either --detection-id for a bare reference
or --detection with a full detection JSON object for automatic field
extraction (detect_id, cat, routing.sid, routing.hostname extracted
by the backend).

At least one of --detection-id or --detection is required.  Additional
metadata (category, severity, sensor, hostname) can be provided to
enrich the ticket and will take precedence over values in the detection
object.

If --severity is omitted the extension defaults to 'medium'.  Valid
severities: critical, high, medium, low.

Examples:
  limacharlie ticket create --detection-id <DETECTION_ID>
  limacharlie ticket create --detection '<full detection JSON>'
  limacharlie ticket create --detection-id <DETECTION_ID> \\
      --detection-cat "lateral_movement" --severity high \\
      --sensor-id <SID> --hostname ws-01
  limacharlie ticket create --detection-id <DETECTION_ID> \\
      --detection-source dr-general --detection-priority 7
"""

register_explain("ticket.create", _EXPLAIN_CREATE)
register_explain("ticket.list", _EXPLAIN_LIST)
register_explain("ticket.get", _EXPLAIN_GET)
register_explain("ticket.update", _EXPLAIN_UPDATE)
register_explain("ticket.add-note", _EXPLAIN_ADD_NOTE)
register_explain("ticket.bulk-update", _EXPLAIN_BULK_UPDATE)
register_explain("ticket.merge", _EXPLAIN_MERGE)
register_explain("ticket.entity.list", _EXPLAIN_ENTITY_LIST)
register_explain("ticket.entity.add", _EXPLAIN_ENTITY_ADD)
register_explain("ticket.entity.update", _EXPLAIN_ENTITY_UPDATE)
register_explain("ticket.entity.remove", _EXPLAIN_ENTITY_REMOVE)
register_explain("ticket.entity.search", _EXPLAIN_ENTITY_SEARCH)
register_explain("ticket.telemetry.list", _EXPLAIN_TELEMETRY_LIST)
register_explain("ticket.telemetry.add", _EXPLAIN_TELEMETRY_ADD)
register_explain("ticket.telemetry.update", _EXPLAIN_TELEMETRY_UPDATE)
register_explain("ticket.telemetry.remove", _EXPLAIN_TELEMETRY_REMOVE)
register_explain("ticket.artifact.list", _EXPLAIN_ARTIFACT_LIST)
register_explain("ticket.artifact.add", _EXPLAIN_ARTIFACT_ADD)
register_explain("ticket.artifact.remove", _EXPLAIN_ARTIFACT_REMOVE)
register_explain("ticket.detection.list", _EXPLAIN_DETECTION_LIST)
register_explain("ticket.detection.add", _EXPLAIN_DETECTION_ADD)
register_explain("ticket.detection.remove", _EXPLAIN_DETECTION_REMOVE)
register_explain("ticket.report", _EXPLAIN_REPORT)
register_explain("ticket.dashboard", _EXPLAIN_DASHBOARD)
register_explain("ticket.config-get", _EXPLAIN_CONFIG_GET)
register_explain("ticket.config-set", _EXPLAIN_CONFIG_SET)
register_explain("ticket.assignees", _EXPLAIN_ASSIGNEES)
register_explain("ticket.export", _EXPLAIN_EXPORT)

_EXPLAIN_TAG_SET = """\
Replace all tags on a ticket.  Any existing tags are removed and
replaced with the provided set.  Use --tag/-t for each tag value.

Examples:
  limacharlie ticket tag set --id 42 --tag phishing
  limacharlie ticket tag set --id 42 -t phishing -t urgent
"""

_EXPLAIN_TAG_ADD = """\
Add one or more tags to a ticket, merging with any existing tags.
Duplicate tags are automatically deduplicated.

Examples:
  limacharlie ticket tag add --id 42 --tag new-tag
  limacharlie ticket tag add --id 42 -t phishing -t urgent
"""

_EXPLAIN_TAG_REMOVE = """\
Remove one or more tags from a ticket.  Tags not currently on the
ticket are silently ignored.

Examples:
  limacharlie ticket tag remove --id 42 --tag old-tag
  limacharlie ticket tag remove --id 42 -t phishing -t urgent
"""

register_explain("ticket.tag.set", _EXPLAIN_TAG_SET)
register_explain("ticket.tag.add", _EXPLAIN_TAG_ADD)
register_explain("ticket.tag.remove", _EXPLAIN_TAG_REMOVE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _output(ctx: click.Context, data: Any) -> None:
    fmt = ctx.obj.output_format or detect_output_format()
    if not ctx.obj.quiet:
        click.echo(format_output(data, fmt))


def _get_ticketing(ctx: click.Context) -> Ticketing:
    client = Client(oid=ctx.obj.oid, environment=ctx.obj.environment)
    org = Organization(client)
    return Ticketing(org)


# ---------------------------------------------------------------------------
# Shared option values
# ---------------------------------------------------------------------------

_STATUS_CHOICES = click.Choice(
    ["new", "acknowledged", "in_progress", "escalated", "resolved", "closed"],
    case_sensitive=False,
)
_SEVERITY_CHOICES = click.Choice(
    ["critical", "high", "medium", "low"],
    case_sensitive=False,
)
_CLASSIFICATION_CHOICES = click.Choice(
    ["pending", "true_positive", "false_positive"],
    case_sensitive=False,
)
_VERDICT_CHOICES = click.Choice(
    ["malicious", "suspicious", "benign", "unknown", "informational"],
    case_sensitive=False,
)
_NOTE_TYPE_CHOICES = click.Choice(
    ["general", "analysis", "remediation", "escalation", "handoff"],
    case_sensitive=False,
)
_ENTITY_TYPE_CHOICES = click.Choice(
    ["ip", "domain", "hash", "url", "user", "email", "file", "process", "registry", "other"],
    case_sensitive=False,
)
_SORT_CHOICES = click.Choice(
    ["created_at", "severity", "ticket_number"],
    case_sensitive=False,
)
_ORDER_CHOICES = click.Choice(["asc", "desc"], case_sensitive=False)


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------

@click.group("ticket")
def group() -> None:
    """Manage SOC tickets (closed beta — contact LimaCharlie for access).

    Full ticket lifecycle management including triage, investigation,
    and resolution.  Supports entities (IOCs), telemetry linking,
    forensic artifacts, reporting, and configuration.

    NOTE: Ticketing is currently in closed beta. Please contact
    LimaCharlie to request access.
    """


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------

@group.command()
@click.option("--detection-id", default=None, help="Detection ID to create the ticket for.")
@click.option("--detection", "detection_json", default=None, help="Full detection JSON object.")
@click.option("--detection-cat", default=None, help="Detection category / rule name.")
@click.option("--severity", default=None, type=_SEVERITY_CHOICES, help="Ticket severity (default: medium).")
@click.option("--detection-source", default=None, help="Detection source (e.g. dr-general).")
@click.option("--detection-priority", default=None, type=int, help="Detection priority (0-10).")
@click.option("--sensor-id", default=None, help="Sensor ID.")
@click.option("--hostname", default=None, help="Hostname.")
@pass_context
def create(ctx, detection_id, detection_json, detection_cat, severity,
           detection_source, detection_priority, sensor_id, hostname) -> None:
    """Create a new ticket from a detection.

    Examples:
        limacharlie ticket create --detection-id <DET_ID>
        limacharlie ticket create --detection '<full detection JSON>'
        limacharlie ticket create --detection-id <DET_ID> \\
            --severity high --hostname ws-01
    """
    if detection_id is None and detection_json is None:
        raise click.UsageError(
            "At least one of --detection-id or --detection is required."
        )
    detection = None
    if detection_json is not None:
        try:
            detection = json.loads(detection_json)
        except json.JSONDecodeError as exc:
            raise click.BadParameter(
                f"invalid JSON for --detection: {exc}",
                param_hint="--detection",
            )
    t = _get_ticketing(ctx)
    data = t.create_ticket(
        detection_id,
        detection=detection,
        detection_cat=detection_cat,
        severity=severity,
        detection_source=detection_source,
        detection_priority=detection_priority,
        sensor_id=sensor_id,
        hostname=hostname,
    )
    _output(ctx, data)


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

@group.command("list")
@click.option("--status", multiple=True, type=_STATUS_CHOICES, help="Filter by status (repeatable).")
@click.option("--severity", multiple=True, type=_SEVERITY_CHOICES, help="Filter by severity (repeatable).")
@click.option("--classification", multiple=True, type=_CLASSIFICATION_CHOICES, help="Filter by classification (repeatable).")
@click.option("--assignee", default=None, help="Filter by assignee email.")
@click.option("--search", default=None, help="Full-text search (detection_cat, hostname).")
@click.option("--sid", default=None, help="Filter to tickets with any detection from this sensor ID.")
@click.option("--tag", multiple=True, help="Filter by tag (repeat for AND logic).")
@click.option("--sort", default=None, type=_SORT_CHOICES, help="Sort field (default: created_at).")
@click.option("--order", default=None, type=_ORDER_CHOICES, help="Sort order (default: desc).")
@click.option("--limit", default=None, type=click.IntRange(1, 200), help="Page size (1-200, default 50).")
@click.option("--cursor", default=None, help="Page token for next page.")
@pass_context
def list_tickets(ctx, status, severity, classification, assignee, search,
                 sid, tag, sort, order, limit, cursor) -> None:
    """List tickets.

    Examples:
        limacharlie ticket list
        limacharlie ticket list --status new --status acknowledged
        limacharlie ticket list --severity critical --severity high
        limacharlie ticket list --search "mimikatz" --limit 20
        limacharlie ticket list --tag phishing --tag urgent
        limacharlie ticket list --sid 8f4b1c2e-...
    """
    t = _get_ticketing(ctx)
    data = t.list_tickets(
        status=list(status) or None,
        severity=list(severity) or None,
        classification=list(classification) or None,
        assignee=assignee,
        search=search,
        sensor_id=sid,
        tag=list(tag) or None,
        sort=sort,
        order=order,
        page_size=limit,
        page_token=cursor,
    )
    _output(ctx, data)


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------

@group.command()
@click.option("--id", "ticket_number", required=True, type=int, help="Ticket number.")
@pass_context
def get(ctx, ticket_number) -> None:
    """Get a ticket with its event timeline.

    Example:
        limacharlie ticket get --id 42
    """
    t = _get_ticketing(ctx)
    data = t.get_ticket(ticket_number)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------

@group.command()
@click.option("--id", "ticket_number", required=True, type=int, help="Ticket number.")
@click.option("--with-data", "output_dir", default=None, type=click.Path(),
              help="Export with full data to a directory.")
@pass_context
def export(ctx, ticket_number, output_dir) -> None:
    """Export a ticket with all its components.

    Without --with-data, prints combined JSON to stdout.
    With --with-data <DIR>, writes a directory containing the ticket
    metadata plus actual detection records, telemetry events, and
    artifact binaries.

    Examples:
        limacharlie ticket export --id 42
        limacharlie ticket export --id 42 --with-data ./out
    """
    t = _get_ticketing(ctx)
    data = t.export_ticket(ticket_number)

    if output_dir is None:
        _output(ctx, data)
        return

    _export_with_data(ctx, t, data, output_dir)


def _safe_filename(name: str) -> str:
    """Sanitize a string for use as a filename (strip path separators)."""
    return os.path.basename(name).replace("\x00", "_")


def _export_with_data(ctx: click.Context, t: Ticketing, data: dict[str, Any],
                      output_dir: str) -> None:
    """Write ticket export to a directory with full data."""
    org = t._org
    os.makedirs(output_dir, exist_ok=True)

    # Write ticket.json (core metadata + timeline + entities).
    with open(os.path.join(output_dir, "ticket.json"), "w") as f:
        json.dump(data, f, indent=2)

    # Fetch actual detection records.
    detections = data.get("detections", {}).get("detections", [])
    if detections:
        det_dir = os.path.join(output_dir, "detections")
        os.makedirs(det_dir, exist_ok=True)
        for det in detections:
            det_id = det.get("detection_id")
            if not det_id:
                continue
            try:
                det_data = org.get_detection_by_id(det_id)
                fname = f"{_safe_filename(det_id)}.json"
                with open(os.path.join(det_dir, fname), "w") as f:
                    json.dump(det_data, f, indent=2)
            except Exception as e:
                click.echo(f"Warning: could not fetch detection {det_id}: {e}", err=True)

    # Fetch actual telemetry events.
    telemetry = data.get("telemetry", {}).get("telemetry", [])
    if telemetry:
        tel_dir = os.path.join(output_dir, "telemetry")
        os.makedirs(tel_dir, exist_ok=True)
        for tel in telemetry:
            atom = tel.get("atom")
            sid = tel.get("sid")
            if not atom or not sid:
                continue
            try:
                sensor = Sensor(org, sid)
                event_data = sensor.get_event_by_atom(atom)
                fname = f"{_safe_filename(atom)}.json"
                with open(os.path.join(tel_dir, fname), "w") as f:
                    json.dump(event_data, f, indent=2)
            except Exception as e:
                click.echo(f"Warning: could not fetch event {atom}: {e}", err=True)

    # Download artifact content.
    artifacts = data.get("artifacts", {}).get("artifacts", [])
    if artifacts:
        art_dir = os.path.join(output_dir, "artifacts")
        os.makedirs(art_dir, exist_ok=True)
        artifacts_sdk = Artifacts(org)
        for art in artifacts:
            art_id = art.get("artifact_id")
            if not art_id:
                continue
            try:
                url_data = artifacts_sdk.get_url(art_id)
                dest = os.path.join(art_dir, f"{_safe_filename(art_id)}.bin")
                if "payload" in url_data:
                    payload = url_data["payload"]
                    raw = base64.b64decode(payload) if isinstance(payload, str) else payload
                    with open(dest, "wb") as f:
                        f.write(raw)
                elif "export" in url_data:
                    with urlopen(url_data["export"]) as resp:
                        with open(dest, "wb") as f:
                            while True:
                                chunk = resp.read(1024 * 1024 * 5)
                                if not chunk:
                                    break
                                f.write(chunk)
            except Exception as e:
                click.echo(f"Warning: could not fetch artifact {art_id}: {e}", err=True)

    if not ctx.obj.quiet:
        click.echo(f"Ticket exported to '{output_dir}'.")


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------

@group.command()
@click.option("--id", "ticket_number", required=True, type=int, help="Ticket number.")
@click.option("--status", default=None, type=_STATUS_CHOICES, help="New status.")
@click.option("--assignee", default=None, help="Assignee email.")
@click.option("--classification", default=None, type=_CLASSIFICATION_CHOICES, help="Classification.")
@click.option("--escalation-group", default=None, help="Escalation group name.")
@click.option("--investigation-id", default=None, help="LC investigation ID to link.")
@click.option("--summary", default=None, help="Investigation summary (max 8192 chars).")
@click.option("--conclusion", default=None, help="Root cause & remediation (max 8192 chars).")
@click.option("--tag", multiple=True, help="Set tags (replaces all existing tags; repeat for multiple).")
@pass_context
def update(ctx, ticket_number, status, assignee, classification,
           escalation_group, investigation_id, summary, conclusion, tag) -> None:
    """Update a ticket.

    Only provided fields are changed.

    Examples:
        limacharlie ticket update --id 42 --status acknowledged
        limacharlie ticket update --id 42 --assignee alice@example.com
        limacharlie ticket update --id 42 --status resolved \\
            --classification true_positive
        limacharlie ticket update --id 42 --tag phishing --tag urgent
    """
    fields = {
        "status": status,
        "assignee": assignee,
        "classification": classification,
        "escalation_group": escalation_group,
        "investigation_id": investigation_id,
        "summary": summary,
        "conclusion": conclusion,
    }
    # Filter out None values
    fields = {k: v for k, v in fields.items() if v is not None}
    if tag:
        fields["tags"] = list(tag)
    if not fields:
        raise click.UsageError("Provide at least one field to update.")

    t = _get_ticketing(ctx)
    data = t.update_ticket(ticket_number, **fields)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# add-note
# ---------------------------------------------------------------------------

@group.command("add-note")
@click.option("--id", "ticket_number", required=True, type=int, help="Ticket number.")
@click.option("--content", default=None, help="Note content.")
@click.option("--input-file", default=None, type=click.Path(exists=True), help="Read note content from file.")
@click.option("--type", "note_type", default=None, type=_NOTE_TYPE_CHOICES,
              help="Note type (default: general).")
@pass_context
def add_note(ctx, ticket_number, content, input_file, note_type) -> None:
    """Add a note to a ticket.

    Provide content via --content, --input-file, or stdin.

    Examples:
        limacharlie ticket add-note --id 42 --content "Triage complete"
        limacharlie ticket add-note --id 42 --type analysis \\
            --content "Confirmed C2 beacon"
        echo "notes" | limacharlie ticket add-note --id 42
    """
    if content:
        text = content
    elif input_file:
        with open(input_file, "r") as f:
            text = f.read()
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        raise click.UsageError("Provide content via --content, --input-file, or stdin.")

    t = _get_ticketing(ctx)
    data = t.add_note(ticket_number, text.strip(), note_type=note_type)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# bulk-update
# ---------------------------------------------------------------------------

@group.command("bulk-update")
@click.option("--numbers", default=None, help="Comma-separated ticket numbers.")
@click.option("--input-file", default=None, type=click.Path(exists=True),
              help="File with ticket numbers (one per line or JSON array).")
@click.option("--status", default=None, type=_STATUS_CHOICES, help="New status for all tickets.")
@click.option("--classification", default=None, type=_CLASSIFICATION_CHOICES,
              help="New classification for all tickets.")
@pass_context
def bulk_update(ctx, numbers, input_file, status, classification) -> None:
    """Bulk update up to 200 tickets.

    Provide ticket numbers via --numbers or --input-file.

    Examples:
        limacharlie ticket bulk-update --numbers 1,2,3 --status closed
        limacharlie ticket bulk-update --input-file numbers.txt \\
            --classification false_positive
    """
    ticket_numbers = _parse_number_list(numbers, input_file)
    if not ticket_numbers:
        raise click.UsageError("Provide ticket numbers via --numbers or --input-file.")

    fields: dict[str, Any] = {}
    if status:
        fields["status"] = status
    if classification:
        fields["classification"] = classification
    if not fields:
        raise click.UsageError("Provide at least --status or --classification.")

    t = _get_ticketing(ctx)
    data = t.bulk_update(ticket_numbers, **fields)
    _output(ctx, data)


def _parse_number_list(numbers_str: str | None, input_file: str | None) -> list[int]:
    """Parse ticket numbers from comma-separated string or file."""
    if numbers_str:
        return [int(i.strip()) for i in numbers_str.split(",") if i.strip()]
    if input_file:
        with open(input_file, "r") as f:
            content = f.read().strip()
        # Try JSON array first
        try:
            parsed = json.loads(content)
            if isinstance(parsed, list):
                return [int(i) for i in parsed]
        except (json.JSONDecodeError, ValueError):
            pass
        # Fall back to one-per-line
        return [int(line.strip()) for line in content.splitlines() if line.strip()]
    if not sys.stdin.isatty():
        content = sys.stdin.read().strip()
        try:
            parsed = json.loads(content)
            if isinstance(parsed, list):
                return [int(i) for i in parsed]
        except (json.JSONDecodeError, ValueError):
            pass
        return [int(line.strip()) for line in content.splitlines() if line.strip()]
    return []


# ---------------------------------------------------------------------------
# merge
# ---------------------------------------------------------------------------

@group.command()
@click.option("--target", required=True, type=int, help="Target ticket number (receives merged content).")
@click.option("--sources", required=True, help="Comma-separated source ticket numbers to merge.")
@pass_context
def merge(ctx, target, sources) -> None:
    """Merge source tickets into a target ticket.

    Investigation content is copied; source tickets become 'merged'.

    Example:
        limacharlie ticket merge --target 10 --sources 11,12
    """
    source_numbers = [int(s.strip()) for s in sources.split(",") if s.strip()]
    if not source_numbers:
        raise click.UsageError("Provide at least one source ticket number.")

    t = _get_ticketing(ctx)
    data = t.merge(target, source_numbers)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# entity (nested group)
# ---------------------------------------------------------------------------

@group.group("entity")
def entity_group() -> None:
    """Manage ticket entities (IOCs).

    Entities represent indicators of compromise found during
    investigation: IPs, domains, hashes, URLs, users, etc.
    """


@entity_group.command("list")
@click.option("--ticket", required=True, type=int, help="Ticket number.")
@pass_context
def entity_list(ctx, ticket) -> None:
    """List entities on a ticket.

    Example:
        limacharlie ticket entity list --ticket 42
    """
    t = _get_ticketing(ctx)
    data = t.list_entities(ticket)
    _output(ctx, data)


@entity_group.command("add")
@click.option("--ticket", required=True, type=int, help="Ticket number.")
@click.option("--type", "entity_type", required=True, type=_ENTITY_TYPE_CHOICES, help="Entity type.")
@click.option("--value", "entity_value", required=True, help="Entity value (max 1024 chars).")
@click.option("--name", default=None, help="Display name.")
@click.option("--verdict", default=None, type=_VERDICT_CHOICES, help="Verdict assessment.")
@click.option("--context", default=None, help="Context notes (max 4096 chars).")
@click.option("--first-seen", default=None, help="First seen timestamp (RFC3339).")
@click.option("--last-seen", default=None, help="Last seen timestamp (RFC3339).")
@pass_context
def entity_add(ctx, ticket, entity_type, entity_value, name, verdict,
               context, first_seen, last_seen) -> None:
    """Add an entity to a ticket.

    Examples:
        limacharlie ticket entity add --ticket 42 \\
            --type ip --value "10.0.0.1" --verdict malicious
        limacharlie ticket entity add --ticket 42 \\
            --type hash --value "d41d8..." --context "In startup folder"
    """
    t = _get_ticketing(ctx)
    data = t.add_entity(
        ticket, entity_type, entity_value,
        name=name, verdict=verdict, context=context,
        first_seen=first_seen, last_seen=last_seen,
    )
    _output(ctx, data)


@entity_group.command("update")
@click.option("--ticket", required=True, type=int, help="Ticket number.")
@click.option("--entity-id", required=True, help="Entity ID to update.")
@click.option("--name", default=None, help="Display name.")
@click.option("--verdict", default=None, type=_VERDICT_CHOICES, help="Verdict assessment.")
@click.option("--context", default=None, help="Context notes (max 4096 chars).")
@click.option("--first-seen", default=None, help="First seen timestamp (RFC3339).")
@click.option("--last-seen", default=None, help="Last seen timestamp (RFC3339).")
@pass_context
def entity_update(ctx, ticket, entity_id, name, verdict, context,
                  first_seen, last_seen) -> None:
    """Update an entity on a ticket.

    Example:
        limacharlie ticket entity update --ticket 42 \\
            --entity-id <EID> --verdict malicious
    """
    fields = {
        "name": name, "verdict": verdict, "context": context,
        "first_seen": first_seen, "last_seen": last_seen,
    }
    fields = {k: v for k, v in fields.items() if v is not None}
    if not fields:
        raise click.UsageError("Provide at least one field to update.")

    t = _get_ticketing(ctx)
    data = t.update_entity(ticket, entity_id, **fields)
    _output(ctx, data)


@entity_group.command("remove")
@click.option("--ticket", required=True, type=int, help="Ticket number.")
@click.option("--entity-id", required=True, help="Entity ID to remove.")
@pass_context
def entity_remove(ctx, ticket, entity_id) -> None:
    """Remove an entity from a ticket.

    Example:
        limacharlie ticket entity remove --ticket 42 --entity-id <EID>
    """
    t = _get_ticketing(ctx)
    data = t.remove_entity(ticket, entity_id)
    _output(ctx, data)


@entity_group.command("search")
@click.option("--type", "entity_type", required=True, type=_ENTITY_TYPE_CHOICES, help="Entity type.")
@click.option("--value", "entity_value", required=True, help="Entity value to search for.")
@pass_context
def entity_search(ctx, entity_type, entity_value) -> None:
    """Search for an entity across all tickets.

    Examples:
        limacharlie ticket entity search --type ip --value "10.0.0.1"
        limacharlie ticket entity search --type domain --value "evil.com"
    """
    t = _get_ticketing(ctx)
    data = t.search_entities(entity_type, entity_value)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# telemetry (nested group)
# ---------------------------------------------------------------------------

@group.group("telemetry")
def telemetry_group() -> None:
    """Manage ticket telemetry references.

    Link LimaCharlie telemetry events to tickets by atom+sensor ID
    for investigation context without storing full event payloads.
    """


@telemetry_group.command("list")
@click.option("--ticket", required=True, type=int, help="Ticket number.")
@pass_context
def telemetry_list(ctx, ticket) -> None:
    """List telemetry references on a ticket.

    Example:
        limacharlie ticket telemetry list --ticket 42
    """
    t = _get_ticketing(ctx)
    data = t.list_telemetry(ticket)
    _output(ctx, data)


@telemetry_group.command("add")
@click.option("--ticket", required=True, type=int, help="Ticket number.")
@click.option("--atom", default=None, help="LC event atom (UUID).")
@click.option("--sid", default=None, help="LC sensor ID (UUID).")
@click.option("--event", "event_json", default=None, help="Full LC event JSON object.")
@click.option("--event-type", default=None, help="Event type (e.g., NEW_PROCESS).")
@click.option("--event-summary", default=None, help="Human-readable event summary.")
@click.option("--verdict", default=None, type=_VERDICT_CHOICES, help="Verdict assessment.")
@click.option("--relevance", default=None, help="Relevance notes (max 1024 chars).")
@pass_context
def telemetry_add(ctx, ticket, atom, sid, event_json, event_type,
                  event_summary, verdict, relevance) -> None:
    """Link a telemetry event to a ticket.

    Examples:
        limacharlie ticket telemetry add --ticket 42 \\
            --atom <ATOM> --sid <SID> --event-type NEW_PROCESS
        limacharlie ticket telemetry add --ticket 42 \\
            --event '<full LC event JSON>'
    """
    if atom is None and sid is None and event_json is None:
        raise click.UsageError(
            "At least one of (--atom + --sid) or --event is required."
        )
    event = None
    if event_json is not None:
        try:
            event = json.loads(event_json)
        except json.JSONDecodeError as exc:
            raise click.BadParameter(
                f"invalid JSON for --event: {exc}",
                param_hint="--event",
            )
    t = _get_ticketing(ctx)
    data = t.add_telemetry(
        ticket, atom, sid,
        event=event,
        event_type=event_type, event_summary=event_summary,
        verdict=verdict, relevance=relevance,
    )
    _output(ctx, data)


@telemetry_group.command("update")
@click.option("--ticket", required=True, type=int, help="Ticket number.")
@click.option("--telemetry-id", required=True, help="Telemetry reference ID.")
@click.option("--event-summary", default=None, help="Human-readable event summary.")
@click.option("--verdict", default=None, type=_VERDICT_CHOICES, help="Verdict assessment.")
@click.option("--relevance", default=None, help="Relevance notes (max 1024 chars).")
@pass_context
def telemetry_update(ctx, ticket, telemetry_id, event_summary, verdict,
                     relevance) -> None:
    """Update a telemetry reference on a ticket.

    Example:
        limacharlie ticket telemetry update --ticket 42 \\
            --telemetry-id <TID> --verdict malicious
    """
    fields = {
        "event_summary": event_summary,
        "verdict": verdict,
        "relevance": relevance,
    }
    fields = {k: v for k, v in fields.items() if v is not None}
    if not fields:
        raise click.UsageError("Provide at least one field to update.")

    t = _get_ticketing(ctx)
    data = t.update_telemetry(ticket, telemetry_id, **fields)
    _output(ctx, data)


@telemetry_group.command("remove")
@click.option("--ticket", required=True, type=int, help="Ticket number.")
@click.option("--telemetry-id", required=True, help="Telemetry reference ID.")
@pass_context
def telemetry_remove(ctx, ticket, telemetry_id) -> None:
    """Remove a telemetry reference from a ticket.

    Example:
        limacharlie ticket telemetry remove --ticket 42 \\
            --telemetry-id <TID>
    """
    t = _get_ticketing(ctx)
    data = t.remove_telemetry(ticket, telemetry_id)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# artifact (nested group)
# ---------------------------------------------------------------------------

@group.group("artifact")
def artifact_group() -> None:
    """Manage ticket forensic artifacts.

    Reference external forensic data (PCAPs, memory dumps, disk
    images, log exports) attached to tickets for investigation.
    """


@artifact_group.command("list")
@click.option("--ticket", required=True, type=int, help="Ticket number.")
@pass_context
def artifact_list(ctx, ticket) -> None:
    """List artifacts on a ticket.

    Example:
        limacharlie ticket artifact list --ticket 42
    """
    t = _get_ticketing(ctx)
    data = t.list_artifacts(ticket)
    _output(ctx, data)


@artifact_group.command("add")
@click.option("--ticket", required=True, type=int, help="Ticket number.")
@click.option("--type", "artifact_type", required=True,
              help="Artifact type (e.g., pcap, memory_dump, disk_image, log_export).")
@click.option("--description", default=None, help="Description (max 2048 chars).")
@click.option("--verdict", default=None, type=_VERDICT_CHOICES, help="Verdict assessment.")
@pass_context
def artifact_add(ctx, ticket, artifact_type, description, verdict) -> None:
    """Add a forensic artifact reference to a ticket.

    Examples:
        limacharlie ticket artifact add --ticket 42 \\
            --type pcap --description "Network capture"
        limacharlie ticket artifact add --ticket 42 \\
            --type memory_dump --verdict suspicious
    """
    t = _get_ticketing(ctx)
    data = t.add_artifact(
        ticket, artifact_type,
        description=description, verdict=verdict,
    )
    _output(ctx, data)


@artifact_group.command("remove")
@click.option("--ticket", required=True, type=int, help="Ticket number.")
@click.option("--artifact-id", required=True, help="Artifact ID to remove.")
@pass_context
def artifact_remove(ctx, ticket, artifact_id) -> None:
    """Remove an artifact from a ticket.

    Example:
        limacharlie ticket artifact remove --ticket 42 \\
            --artifact-id <AID>
    """
    t = _get_ticketing(ctx)
    data = t.remove_artifact(ticket, artifact_id)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# detection (nested group)
# ---------------------------------------------------------------------------

@group.group("detection")
def detection_group() -> None:
    """Manage detections linked to tickets.

    Link or unlink LimaCharlie detection records to tickets for
    tracking which detections triggered an investigation.
    """


@detection_group.command("list")
@click.option("--ticket", required=True, type=int, help="Ticket number.")
@pass_context
def detection_list(ctx, ticket) -> None:
    """List detections linked to a ticket.

    Example:
        limacharlie ticket detection list --ticket 42
    """
    t = _get_ticketing(ctx)
    data = t.list_detections(ticket)
    _output(ctx, data)


@detection_group.command("add")
@click.option("--ticket", required=True, type=int, help="Ticket number.")
@click.option("--detection-id", default=None, help="Detection ID to link.")
@click.option("--detection", "detection_json", default=None, help="Full detection JSON object.")
@click.option("--detection-cat", default=None, help="Detection category/rule name.")
@click.option("--detection-source", default=None, help="Detection source (e.g., dr-general).")
@click.option("--detection-priority", default=None, type=int, help="Priority (0-10).")
@click.option("--sensor-id", default=None, help="Sensor ID.")
@click.option("--hostname", default=None, help="Hostname.")
@pass_context
def detection_add(ctx, ticket, detection_id, detection_json, detection_cat,
                  detection_source, detection_priority, sensor_id,
                  hostname) -> None:
    """Link a detection to a ticket.

    Examples:
        limacharlie ticket detection add --ticket 42 \\
            --detection-id <DET_ID>
        limacharlie ticket detection add --ticket 42 \\
            --detection '<full detection JSON>'
        limacharlie ticket detection add --ticket 42 \\
            --detection-id <DET_ID> --detection-cat lateral_movement
    """
    if detection_id is None and detection_json is None:
        raise click.UsageError(
            "At least one of --detection-id or --detection is required."
        )
    detection = None
    if detection_json is not None:
        try:
            detection = json.loads(detection_json)
        except json.JSONDecodeError as exc:
            raise click.BadParameter(
                f"invalid JSON for --detection: {exc}",
                param_hint="--detection",
            )
    t = _get_ticketing(ctx)
    data = t.add_detection(
        ticket, detection_id,
        detection=detection,
        detection_cat=detection_cat,
        detection_source=detection_source,
        detection_priority=detection_priority,
        sensor_id=sensor_id,
        hostname=hostname,
    )
    _output(ctx, data)


@detection_group.command("remove")
@click.option("--ticket", required=True, type=int, help="Ticket number.")
@click.option("--detection-id", required=True, help="Detection ID to unlink.")
@pass_context
def detection_remove(ctx, ticket, detection_id) -> None:
    """Remove a detection link from a ticket.

    Example:
        limacharlie ticket detection remove --ticket 42 \\
            --detection-id <DET_ID>
    """
    t = _get_ticketing(ctx)
    data = t.remove_detection(ticket, detection_id)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

@group.command()
@click.option("--from", "time_from", required=True,
              help="Start time (RFC3339, e.g. 2026-01-01T00:00:00Z).")
@click.option("--to", "time_to", required=True,
              help="End time (RFC3339, e.g. 2026-02-01T00:00:00Z).")
@click.option("--group-by", default=None,
              help="Group results by field (e.g., severity, region).")
@pass_context
def report(ctx, time_from, time_to, group_by) -> None:
    """Generate a SOC performance report.

    Returns MTTA, MTTR, TP/FP rates, volume metrics, repeat
    offenders, and top detection categories.

    Examples:
        limacharlie ticket report \\
            --from 2026-01-01T00:00:00Z --to 2026-02-01T00:00:00Z
        limacharlie ticket report \\
            --from 2026-01-01T00:00:00Z --to 2026-02-01T00:00:00Z \\
            --group-by severity
    """
    t = _get_ticketing(ctx)
    data = t.report_summary(
        time_from=time_from,
        time_to=time_to,
        group_by=group_by,
    )
    _output(ctx, data)


# ---------------------------------------------------------------------------
# dashboard
# ---------------------------------------------------------------------------

@group.command()
@pass_context
def dashboard(ctx) -> None:
    """Get real-time ticket counts and SLA breach status.

    Example:
        limacharlie ticket dashboard
    """
    t = _get_ticketing(ctx)
    data = t.dashboard_counts()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# config-get
# ---------------------------------------------------------------------------

@group.command("config-get")
@pass_context
def config_get(ctx) -> None:
    """Get ticketing configuration.

    Example:
        limacharlie ticket config-get
    """
    t = _get_ticketing(ctx)
    data = t.get_config()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# config-set
# ---------------------------------------------------------------------------

@group.command("config-set")
@click.option("--input-file", default=None, type=click.Path(exists=True),
              help="Path to config data (JSON or YAML). Reads stdin if omitted.")
@pass_context
def config_set(ctx, input_file) -> None:
    """Update ticketing configuration.

    Provide data via --input-file or stdin.

    Examples:
        limacharlie ticket config-set --input-file config.yaml
        cat config.json | limacharlie ticket config-set
    """
    if input_file:
        with open(input_file, "r") as f:
            content = f.read()
    elif not sys.stdin.isatty():
        content = sys.stdin.read()
    else:
        raise click.UsageError("Provide config via --input-file or stdin.")

    try:
        data = yaml.safe_load(content)
    except Exception:
        data = json.loads(content)

    t = _get_ticketing(ctx)
    result = t.set_config(data)
    if not ctx.obj.quiet:
        click.echo("Ticketing configuration updated.")
    _output(ctx, result)


# ---------------------------------------------------------------------------
# assignees
# ---------------------------------------------------------------------------

@group.command()
@pass_context
def assignees(ctx) -> None:
    """List unique assignee emails.

    Example:
        limacharlie ticket assignees
    """
    t = _get_ticketing(ctx)
    data = t.list_assignees()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# tag (nested group)
# ---------------------------------------------------------------------------

@group.group("tag")
def tag_group() -> None:
    """Manage ticket tags.

    Set, add, or remove tags on tickets.  Tags are free-form strings
    used for categorization and filtering.
    """


@tag_group.command("set")
@click.option("--id", "ticket_number", required=True, type=int, help="Ticket number.")
@click.option("--tag", "-t", "tags", multiple=True, required=True, help="Tag value (repeatable).")
@pass_context
def tag_set(ctx, ticket_number, tags) -> None:
    """Replace all tags on a ticket.

    Examples:
        limacharlie ticket tag set --id 42 --tag phishing
        limacharlie ticket tag set --id 42 -t phishing -t urgent
    """
    t = _get_ticketing(ctx)
    data = t.update_ticket(ticket_number, tags=list(tags))
    _output(ctx, data)


@tag_group.command("add")
@click.option("--id", "ticket_number", required=True, type=int, help="Ticket number.")
@click.option("--tag", "-t", "tags", multiple=True, required=True, help="Tag value to add (repeatable).")
@pass_context
def tag_add(ctx, ticket_number, tags) -> None:
    """Add tags to a ticket (merged with existing).

    Examples:
        limacharlie ticket tag add --id 42 --tag new-tag
        limacharlie ticket tag add --id 42 -t phishing -t urgent
    """
    tk = _get_ticketing(ctx)
    current = tk.get_ticket(ticket_number)
    existing = current.get("ticket", current).get("tags") or []
    seen = {}
    for tag in existing + list(tags):
        key = tag.lower()
        if key not in seen:
            seen[key] = tag
    merged = list(seen.values())
    data = tk.update_ticket(ticket_number, tags=merged)
    _output(ctx, data)


@tag_group.command("remove")
@click.option("--id", "ticket_number", required=True, type=int, help="Ticket number.")
@click.option("--tag", "-t", "tags", multiple=True, required=True, help="Tag value to remove (repeatable).")
@pass_context
def tag_remove(ctx, ticket_number, tags) -> None:
    """Remove tags from a ticket.

    Examples:
        limacharlie ticket tag remove --id 42 --tag old-tag
        limacharlie ticket tag remove --id 42 -t phishing -t urgent
    """
    tk = _get_ticketing(ctx)
    current = tk.get_ticket(ticket_number)
    existing = current.get("ticket", current).get("tags") or []
    to_remove = {t.lower() for t in tags}
    remaining = [t for t in existing if t.lower() not in to_remove]
    data = tk.update_ticket(ticket_number, tags=remaining)
    _output(ctx, data)
