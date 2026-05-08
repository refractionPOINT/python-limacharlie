"""Case commands for LimaCharlie CLI v2.

Commands for managing SOC cases: lifecycle management, investigation
tracking (entities, telemetry, artifacts), reporting, and configuration
via the LimaCharlie Cases extension.
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
from ..sdk.cases import Cases
from ..output import format_output, detect_output_format
from ..discovery import register_explain


# ---------------------------------------------------------------------------
# Explain texts
# ---------------------------------------------------------------------------

_EXPLAIN_LIST = """\
List cases for the organization with optional filtering, sorting,
and pagination.

Filters (all repeatable/comma-separated):
  --status    new, in_progress, resolved, closed
  --severity  critical, high, medium, low, info
  --classification  pending, true_positive, false_positive
  --assignee  filter by assignee email
  --search    full-text search in detection_cat and hostname across linked detections
  --sid       filter to cases with any detection from this sensor ID
  --tag       filter by tag (repeat for AND logic)

Sorting:
  --sort      created_at (default), severity, case_number
  --order     asc, desc (default)

Pagination:
  --limit     page size (1-200, default 50)
  --cursor    page token from previous response

The response includes total_counts showing status distribution
for the current filter, useful for building dashboards.

Examples:
  limacharlie case list
  limacharlie case list --status new,in_progress --severity critical,high
  limacharlie case list --assignee alice@example.com --sort severity
  limacharlie case list --search "mimikatz" --limit 20
  limacharlie case list --tag phishing --tag urgent
"""

_EXPLAIN_GET = """\
Get a single case with its full event timeline.  Returns the
complete case record plus an ordered list of all events (status
changes, notes, entity additions, etc.).

The event timeline provides a full audit trail of the case's
lifecycle including who made each change and when.

Examples:
  limacharlie case get --case-number 42
"""

_EXPLAIN_UPDATE = """\
Update a case's fields.  Only provided fields are changed;
omitted fields are left untouched.

Updatable fields:
  --status           new, in_progress, resolved, closed
                     (state machine enforced)
  --severity         critical, high, medium, low, info
  --assignees        assignee emails (repeatable for multiple)
  --classification   pending, true_positive, false_positive
  --summary          investigation findings (max 8192 chars)
  --conclusion       root cause & remediation (max 8192 chars)
  --tag              add/replace tags (repeatable; see case tag subcommand)

Status transitions follow a state machine:
  new -> in_progress, closed
  in_progress -> resolved, closed
  resolved -> closed
  closed -> in_progress (reopen)

Examples:
  limacharlie case update --case-number 42 --status in_progress
  limacharlie case update --case-number 42 --severity high
  limacharlie case update --case-number 42 --assignees alice@example.com
  limacharlie case update --case-number 42 --status resolved \\
      --classification true_positive \\
      --conclusion "Contained via network isolation"
"""

_EXPLAIN_ADD_NOTE = """\
Add a note to a case.  Notes support categorization for structured
investigation workflows.

Note types:
  general          - General notes (default)
  analysis         - Threat analysis findings
  remediation      - Remediation steps taken or recommended
  escalation       - Escalation context and reasoning
  handoff          - Shift handoff notes
  to_stakeholder   - Notes to stakeholders
  from_stakeholder - Notes from stakeholders

Use --is-public to make the note visible to stakeholders (default: private).

Provide content via --content, --input-file, or stdin.

Examples:
  limacharlie case add-note --case-number 42 --content "Initial triage complete"
  limacharlie case add-note --case-number 42 --type analysis \\
      --content "Confirmed C2 beacon to 10.0.0.1"
  limacharlie case add-note --case-number 42 --is-public \\
      --content "Status update for stakeholders"
  echo "Handoff notes" | limacharlie case add-note --case-number 42 --type handoff
"""

_EXPLAIN_UPDATE_NOTE_VISIBILITY = """\
Toggle a note's public/private visibility.  Public notes are visible
to stakeholders.

Requires the event ID of the note (from the case event timeline).

Examples:
  limacharlie case update-note --case-number 42 --event-id <EID> --is-public
  limacharlie case update-note --case-number 42 --event-id <EID> --no-is-public
"""

_EXPLAIN_BULK_UPDATE = """\
Batch update up to 200 cases at once.  Provide case numbers as a
comma-separated list or via --input-file (one number per line or JSON
array).

Only status and classification can be set in bulk.

Examples:
  limacharlie case bulk-update --numbers 1,2,3 \\
      --status closed --classification false_positive
  limacharlie case bulk-update --input-file case_numbers.txt --status resolved
"""

_EXPLAIN_MERGE = """\
Merge multiple source cases into a single target case.  This
moves detections from the source cases into the target and closes
the source cases (with merged_into_case_id set).

This is useful for consolidating duplicate cases created from
related detections.

Target case must not be closed.  Source cases must not be closed.

Examples:
  limacharlie case merge --target 10 --sources 11,12,13
"""

_EXPLAIN_ENTITY_LIST = """\
List all entities (IOCs) attached to a case.  Entities represent
indicators of compromise found during investigation.

Entity types: ip, domain, hash, url, user, email, file, process,
registry, other.

Each entity has a verdict: malicious, suspicious, benign, unknown,
informational.

Example:
  limacharlie case entity list --case 42
"""

_EXPLAIN_ENTITY_ADD = """\
Add an entity (IOC) to a case.  Duplicate type+value pairs on the
same case are rejected (409).

Required: --type and --value.  Optional: --note, --verdict.

Entity values are normalized (lowercased) for IP, domain, hash, and
email types.

Examples:
  limacharlie case entity add --case 42 \\
      --type ip --value "10.0.0.1" --verdict malicious
  limacharlie case entity add --case 42 \\
      --type hash --value "d41d8cd98f00b204e9800998ecf8427e" \\
      --verdict suspicious --note "Found in startup folder"
"""

_EXPLAIN_ENTITY_UPDATE = """\
Update an existing entity on a case.

Updatable fields: --note, --verdict.

Example:
  limacharlie case entity update --case 42 --entity-id <EID> \\
      --verdict malicious --note "Confirmed C2 server"
"""

_EXPLAIN_ENTITY_REMOVE = """\
Remove an entity from a case.

Example:
  limacharlie case entity remove --case 42 --entity-id <EID>
"""

_EXPLAIN_ENTITY_SEARCH = """\
Search for an entity across all cases in accessible organizations.
Returns all cases containing the given entity type+value pair.

Useful for pivoting: "which other cases reference this IP?"

Examples:
  limacharlie case entity search --type ip --value "10.0.0.1"
  limacharlie case entity search --type domain --value "evil.com"
"""

_EXPLAIN_TELEMETRY_LIST = """\
List telemetry event references linked to a case.  These reference
LimaCharlie events by atom+sid without storing the full payload.

Example:
  limacharlie case telemetry list --case 42
"""

_EXPLAIN_TELEMETRY_ADD = """\
Link a LimaCharlie telemetry event to a case.  Pass the full event
JSON object via --event.  The backend automatically extracts
routing.this (atom), routing.sid, and routing.event_type.

Optional: --note, --verdict.

Example:
  limacharlie case telemetry add --case 42 \\
      --event '<full LC event JSON>' --verdict suspicious
"""

_EXPLAIN_TELEMETRY_UPDATE = """\
Update a telemetry reference on a case.

Updatable fields: --note, --verdict.

Example:
  limacharlie case telemetry update --case 42 \\
      --telemetry-id <TID> --verdict malicious
"""

_EXPLAIN_TELEMETRY_REMOVE = """\
Remove a telemetry reference from a case.

Example:
  limacharlie case telemetry remove --case 42 --telemetry-id <TID>
"""

_EXPLAIN_ARTIFACT_LIST = """\
List forensic artifact references on a case.  Artifacts reference
external forensic data (PCAPs, memory dumps, disk images, etc.)
without storing the actual files.

Example:
  limacharlie case artifact list --case 42
"""

_EXPLAIN_ARTIFACT_ADD = """\
Add a forensic artifact reference to a case.

Required: --path and --source.  Optional: --type, --note, --verdict.

Examples:
  limacharlie case artifact add --case 42 \\
      --path "/captures/incident-01.pcap" --source "sensor-01" \\
      --type pcap --note "Network capture during incident"
  limacharlie case artifact add --case 42 \\
      --path "/dumps/pid1234.dmp" --source "edr-collection" \\
      --type memory_dump --verdict suspicious
"""

_EXPLAIN_ARTIFACT_REMOVE = """\
Remove a forensic artifact reference from a case.

Example:
  limacharlie case artifact remove --case 42 --artifact-id <AID>
"""

_EXPLAIN_DETECTION_LIST = """\
List detections linked to a case.

Example:
  limacharlie case detection list --case 42
"""

_EXPLAIN_DETECTION_ADD = """\
Link an additional detection to a case.  Pass the full detection
JSON object via --detection.  The backend automatically extracts
detect_id, cat, source, routing.sid, routing.hostname, and
detect_mtd.level.

Example:
  limacharlie case detection add --case 42 \\
      --detection '<full detection JSON>'
"""

_EXPLAIN_DETECTION_REMOVE = """\
Remove a detection link from a case.

Example:
  limacharlie case detection remove --case 42 \\
      --detection-id <DETECTION_ID>
"""

_EXPLAIN_REPORT = """\
Generate a comprehensive SOC performance report including MTTA,
MTTR, TP/FP rates, volume metrics, repeat offenders, and top
detection categories.

A time range is required via --from and --to (RFC3339 format).
Use --group-by to segment data (e.g., by severity or region).

Examples:
  limacharlie case report \\
      --from 2026-01-01T00:00:00Z --to 2026-02-01T00:00:00Z
  limacharlie case report \\
      --from 2026-01-01T00:00:00Z --to 2026-02-01T00:00:00Z \\
      --group-by severity
"""

_EXPLAIN_DASHBOARD = """\
Get real-time case counts by status and severity, including
SLA breach counts.  Useful for building operational dashboards
and monitoring SOC workload.

Example:
  limacharlie case dashboard
"""

_EXPLAIN_CONFIG_GET = """\
Get the organization's cases configuration.

Returns severity_mapping, SLA thresholds (mtta/mttr per severity),
retention_days, and auto_close_resolved_after_days.

Example:
  limacharlie case config-get
"""

_EXPLAIN_CONFIG_SET = """\
Update the organization's cases configuration.  Provide data
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
    info:     {mtta_minutes: 480, mttr_minutes: 10080}
  retention_days: 90
  auto_close_resolved_after_days: 30

Examples:
  limacharlie case config-set --input-file config.yaml
  cat config.json | limacharlie case config-set
"""

_EXPLAIN_ASSIGNEES = """\
List all unique assignee emails across cases in the organization.
Useful for populating assignee dropdowns or verifying team coverage.

Example:
  limacharlie case assignees
"""

_EXPLAIN_ORGS = """\
List organizations subscribed to ext-cases that the current user
can access.  Useful for multi-org users to discover which orgs
have cases enabled.

Example:
  limacharlie case orgs
"""

_EXPLAIN_EXPORT = """\
Export a case with all its components in a single JSON object.
Fetches the case record (with event timeline), linked detections,
entities (IOCs), telemetry references, and forensic artifacts in one
call.

This is a convenience command that aggregates data from multiple
endpoints into a single output for backup, migration, or offline
analysis.

Without --with-data the combined JSON is printed to stdout.

With --with-data <DIR> the command creates a directory with the full
case data including the actual detection records, telemetry events,
and artifact binaries:

  <DIR>/
    case.json          case record, timeline, entities
    detections/        one JSON file per linked detection
    telemetry/         one JSON file per linked telemetry event
    artifacts/         downloaded artifact binaries

Fetches that fail (e.g. expired data) emit a warning on stderr and
are skipped.

Examples:
  limacharlie case export --case-number 42
  limacharlie case export --case-number 42 --output json > case.json
  limacharlie case export --case-number 42 --with-data ./case-export
"""

_EXPLAIN_CREATE = """\
Create a new SOC case, optionally from a detection.

With --detection: pass the full detection JSON as produced by
LimaCharlie D&R rules.  The backend automatically extracts detect_id,
cat, source, routing.sid, routing.hostname, and detect_mtd.level.

Without --detection: creates an empty investigation case that can
be populated later with detections, telemetry, entities, etc.

If --severity is omitted, severity is derived from detect_mtd.level
in the detection object (or defaults to 'medium').  Valid severities:
critical, high, medium, low, info.

--summary is required.  The summary is included in the 'created' audit
event so D&R rules and webhooks can act on it immediately.

Examples:
  limacharlie case create --summary "Investigating lateral movement"
  limacharlie case create --detection '<full detection JSON>' \\
      --summary "Triage detection"
  limacharlie case create --detection '<full detection JSON>' \\
      --severity high --summary "High severity lateral movement"
  limacharlie case create --severity medium \\
      --summary "Investigating lateral movement"
"""

register_explain("case.create", _EXPLAIN_CREATE)
register_explain("case.list", _EXPLAIN_LIST)
register_explain("case.get", _EXPLAIN_GET)
register_explain("case.update", _EXPLAIN_UPDATE)
register_explain("case.add-note", _EXPLAIN_ADD_NOTE)
register_explain("case.update-note", _EXPLAIN_UPDATE_NOTE_VISIBILITY)
register_explain("case.bulk-update", _EXPLAIN_BULK_UPDATE)
register_explain("case.merge", _EXPLAIN_MERGE)
register_explain("case.entity.list", _EXPLAIN_ENTITY_LIST)
register_explain("case.entity.add", _EXPLAIN_ENTITY_ADD)
register_explain("case.entity.update", _EXPLAIN_ENTITY_UPDATE)
register_explain("case.entity.remove", _EXPLAIN_ENTITY_REMOVE)
register_explain("case.entity.search", _EXPLAIN_ENTITY_SEARCH)
register_explain("case.telemetry.list", _EXPLAIN_TELEMETRY_LIST)
register_explain("case.telemetry.add", _EXPLAIN_TELEMETRY_ADD)
register_explain("case.telemetry.update", _EXPLAIN_TELEMETRY_UPDATE)
register_explain("case.telemetry.remove", _EXPLAIN_TELEMETRY_REMOVE)
register_explain("case.artifact.list", _EXPLAIN_ARTIFACT_LIST)
register_explain("case.artifact.add", _EXPLAIN_ARTIFACT_ADD)
register_explain("case.artifact.remove", _EXPLAIN_ARTIFACT_REMOVE)
register_explain("case.detection.list", _EXPLAIN_DETECTION_LIST)
register_explain("case.detection.add", _EXPLAIN_DETECTION_ADD)
register_explain("case.detection.remove", _EXPLAIN_DETECTION_REMOVE)
register_explain("case.report", _EXPLAIN_REPORT)
register_explain("case.dashboard", _EXPLAIN_DASHBOARD)
register_explain("case.config-get", _EXPLAIN_CONFIG_GET)
register_explain("case.config-set", _EXPLAIN_CONFIG_SET)
register_explain("case.assignees", _EXPLAIN_ASSIGNEES)
register_explain("case.orgs", _EXPLAIN_ORGS)
register_explain("case.export", _EXPLAIN_EXPORT)

_EXPLAIN_TAG_SET = """\
Replace all tags on a case.  Any existing tags are removed and
replaced with the provided set.  Use --tag/-t for each tag value.

Examples:
  limacharlie case tag set --case-number 42 --tag phishing
  limacharlie case tag set --case-number 42 -t phishing -t urgent
"""

_EXPLAIN_TAG_ADD = """\
Add one or more tags to a case, merging with any existing tags.
Duplicate tags are automatically deduplicated.

Examples:
  limacharlie case tag add --case-number 42 --tag new-tag
  limacharlie case tag add --case-number 42 -t phishing -t urgent
"""

_EXPLAIN_TAG_REMOVE = """\
Remove one or more tags from a case.  Tags not currently on the
case are silently ignored.

Examples:
  limacharlie case tag remove --case-number 42 --tag old-tag
  limacharlie case tag remove --case-number 42 -t phishing -t urgent
"""

register_explain("case.tag.set", _EXPLAIN_TAG_SET)
register_explain("case.tag.add", _EXPLAIN_TAG_ADD)
register_explain("case.tag.remove", _EXPLAIN_TAG_REMOVE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _output(ctx: click.Context, data: Any) -> None:
    fmt = ctx.obj.output_format or detect_output_format()
    if not ctx.obj.quiet:
        click.echo(format_output(data, fmt))


def _get_cases(ctx: click.Context) -> Cases:
    client = Client(oid=ctx.obj.oid, environment=ctx.obj.environment, print_debug_fn=ctx.obj.debug_fn, debug_full_response=ctx.obj.debug_full, debug_curl=ctx.obj.debug_curl, debug_verbose=ctx.obj.debug_verbose)
    org = Organization(client)
    return Cases(org)


# ---------------------------------------------------------------------------
# Shared option values
# ---------------------------------------------------------------------------

_STATUS_CHOICES = click.Choice(
    ["new", "in_progress", "resolved", "closed"],
    case_sensitive=False,
)
_SEVERITY_CHOICES = click.Choice(
    ["critical", "high", "medium", "low", "info"],
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
    ["general", "analysis", "remediation", "escalation", "handoff",
     "to_stakeholder", "from_stakeholder"],
    case_sensitive=False,
)
_ENTITY_TYPE_CHOICES = click.Choice(
    ["ip", "domain", "hash", "url", "user", "email", "file", "process", "registry", "other"],
    case_sensitive=False,
)
_SORT_CHOICES = click.Choice(
    ["created_at", "severity", "case_number"],
    case_sensitive=False,
)
_ORDER_CHOICES = click.Choice(["asc", "desc"], case_sensitive=False)


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------

@click.group("case")
def group() -> None:
    """Manage SOC cases (closed beta -- contact LimaCharlie for access).

    Full case lifecycle management including triage, investigation,
    and resolution.  Supports entities (IOCs), telemetry linking,
    forensic artifacts, reporting, and configuration.

    NOTE: Cases is currently in closed beta. Please contact
    LimaCharlie to request access.
    """


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------

@group.command()
@click.option("--detection", "detection_json", default=None,
              help="Full detection JSON object (optional).")
@click.option("--severity", default=None, type=_SEVERITY_CHOICES,
              help="Case severity override (default: derived from detection).")
@click.option("--summary", required=True,
              help="Case summary (required, max 8192 chars).")
@pass_context
def create(ctx, detection_json, severity, summary) -> None:
    """Create a new case, optionally from a detection.

    Examples:
        limacharlie case create --summary "Investigating lateral movement"
        limacharlie case create --detection '<full detection JSON>' \\
            --summary "Triage detection"
        limacharlie case create --detection '<full detection JSON>' \\
            --severity high --summary "High severity lateral movement"
        limacharlie case create --severity medium --summary "Investigating lateral movement"
    """
    detection = None
    if detection_json is not None:
        try:
            detection = json.loads(detection_json)
        except json.JSONDecodeError as exc:
            raise click.BadParameter(
                f"invalid JSON for --detection: {exc}",
                param_hint="--detection",
            )
    t = _get_cases(ctx)
    data = t.create_case(detection, severity=severity, summary=summary)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

@group.command("list")
@click.option("--status", multiple=True, type=_STATUS_CHOICES, help="Filter by status (repeatable).")
@click.option("--severity", multiple=True, type=_SEVERITY_CHOICES, help="Filter by severity (repeatable).")
@click.option("--classification", multiple=True, type=_CLASSIFICATION_CHOICES, help="Filter by classification (repeatable).")
@click.option("--assignee", default=None, help="Filter by assignee email.")
@click.option("--search", default=None, help="Full-text search (detection_cat, hostname across linked detections).")
@click.option("--sid", default=None, help="Filter to cases with any detection from this sensor ID.")
@click.option("--tag", multiple=True, help="Filter by tag (repeat for AND logic).")
@click.option("--sort", default=None, type=_SORT_CHOICES, help="Sort field (default: created_at).")
@click.option("--order", default=None, type=_ORDER_CHOICES, help="Sort order (default: desc).")
@click.option("--limit", default=None, type=click.IntRange(1, 200), help="Page size (1-200, default 50).")
@click.option("--cursor", default=None, help="Page token for next page.")
@pass_context
def list_cases(ctx, status, severity, classification, assignee, search,
               sid, tag, sort, order, limit, cursor) -> None:
    """List cases.

    Examples:
        limacharlie case list
        limacharlie case list --status new --status in_progress
        limacharlie case list --severity critical --severity high
        limacharlie case list --search "mimikatz" --limit 20
        limacharlie case list --tag phishing --tag urgent
        limacharlie case list --sid 8f4b1c2e-...
    """
    t = _get_cases(ctx)
    data = t.list_cases(
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
@click.option("--case-number", "case_number", required=True, type=int, help="Case number.")
@pass_context
def get(ctx, case_number) -> None:
    """Get a case with its event timeline.

    Example:
        limacharlie case get --case-number 42
    """
    t = _get_cases(ctx)
    data = t.get_case(case_number)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------

@group.command()
@click.option("--case-number", "case_number", required=True, type=int, help="Case number.")
@click.option("--with-data", "output_dir", default=None, type=click.Path(),
              help="Export with full data to a directory.")
@pass_context
def export(ctx, case_number, output_dir) -> None:
    """Export a case with all its components.

    Without --with-data, prints combined JSON to stdout.
    With --with-data <DIR>, writes a directory containing the case
    metadata plus actual detection records, telemetry events, and
    artifact binaries.

    Examples:
        limacharlie case export --case-number 42
        limacharlie case export --case-number 42 --with-data ./out
    """
    t = _get_cases(ctx)
    data = t.export_case(case_number)

    if output_dir is None:
        _output(ctx, data)
        return

    _export_with_data(ctx, t, data, output_dir)


def _safe_filename(name: str) -> str:
    """Sanitize a string for use as a filename (strip path separators)."""
    return os.path.basename(name).replace("\x00", "_")


def _export_with_data(ctx: click.Context, t: Cases, data: dict[str, Any],
                      output_dir: str) -> None:
    """Write case export to a directory with full data."""
    org = t._org
    os.makedirs(output_dir, exist_ok=True)

    # Write case.json (core metadata + timeline + entities).
    with open(os.path.join(output_dir, "case.json"), "w") as f:
        json.dump(data, f, indent=2)

    # Fetch actual detection records.
    detections = data.get("detections", {}).get("detections", [])
    if detections:
        det_dir = os.path.join(output_dir, "detections")
        os.makedirs(det_dir, exist_ok=True)
        for det in detections:
            det_id = det.get("detect_id")
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
        click.echo(f"Case exported to '{output_dir}'.")


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------

@group.command()
@click.option("--case-number", "case_number", required=True, type=int, help="Case number.")
@click.option("--status", default=None, type=_STATUS_CHOICES, help="New status.")
@click.option("--severity", default=None, type=_SEVERITY_CHOICES, help="Case severity (critical, high, medium, low, info).")
@click.option("--assignees", multiple=True, help="Assignee email (repeatable for multiple assignees).")
@click.option("--classification", default=None, type=_CLASSIFICATION_CHOICES, help="Classification.")
@click.option("--summary", default=None, help="Investigation summary (max 8192 chars).")
@click.option("--conclusion", default=None, help="Root cause & remediation (max 8192 chars).")
@click.option("--tag", multiple=True, help="Set tags (replaces all existing tags; repeat for multiple).")
@pass_context
def update(ctx, case_number, status, severity, assignees, classification,
           summary, conclusion, tag) -> None:
    """Update a case.

    Only provided fields are changed.

    Examples:
        limacharlie case update --case-number 42 --status in_progress
        limacharlie case update --case-number 42 --severity high
        limacharlie case update --case-number 42 --assignees alice@example.com
        limacharlie case update --case-number 42 --status resolved \\
            --classification true_positive
        limacharlie case update --case-number 42 --tag phishing --tag urgent
    """
    fields = {
        "status": status,
        "severity": severity,
        "classification": classification,
        "summary": summary,
        "conclusion": conclusion,
    }
    # Filter out None values
    fields = {k: v for k, v in fields.items() if v is not None}
    if assignees:
        fields["assignees"] = list(assignees)
    if tag:
        fields["tags"] = list(tag)
    if not fields:
        raise click.UsageError("Provide at least one field to update.")

    t = _get_cases(ctx)
    data = t.update_case(case_number, **fields)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# add-note
# ---------------------------------------------------------------------------

@group.command("add-note")
@click.option("--case-number", "case_number", required=True, type=int, help="Case number.")
@click.option("--content", default=None, help="Note content.")
@click.option("--input-file", default=None, type=click.Path(exists=True), help="Read note content from file.")
@click.option("--type", "note_type", default=None, type=_NOTE_TYPE_CHOICES,
              help="Note type (default: general).")
@click.option("--is-public/--no-is-public", default=None,
              help="Make note visible to stakeholders (default: private).")
@pass_context
def add_note(ctx, case_number, content, input_file, note_type, is_public) -> None:
    """Add a note to a case.

    Provide content via --content, --input-file, or stdin.

    Examples:
        limacharlie case add-note --case-number 42 --content "Triage complete"
        limacharlie case add-note --case-number 42 --type analysis \\
            --content "Confirmed C2 beacon"
        limacharlie case add-note --case-number 42 --is-public \\
            --content "Status update for stakeholders"
        echo "notes" | limacharlie case add-note --case-number 42
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

    t = _get_cases(ctx)
    data = t.add_note(case_number, text.strip(), note_type=note_type, is_public=is_public)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# update-note
# ---------------------------------------------------------------------------

@group.command("update-note")
@click.option("--case-number", "case_number", required=True, type=int, help="Case number.")
@click.option("--event-id", required=True, help="Event ID of the note.")
@click.option("--is-public/--no-is-public", required=True,
              help="Set note visibility for stakeholders.")
@pass_context
def update_note(ctx, case_number, event_id, is_public) -> None:
    """Toggle a note's public/private visibility.

    Examples:
        limacharlie case update-note --case-number 42 --event-id <EID> --is-public
        limacharlie case update-note --case-number 42 --event-id <EID> --no-is-public
    """
    t = _get_cases(ctx)
    data = t.update_note_visibility(case_number, event_id, is_public)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# bulk-update
# ---------------------------------------------------------------------------

@group.command("bulk-update")
@click.option("--numbers", default=None, help="Comma-separated case numbers.")
@click.option("--input-file", default=None, type=click.Path(exists=True),
              help="File with case numbers (one per line or JSON array).")
@click.option("--status", default=None, type=_STATUS_CHOICES, help="New status for all cases.")
@click.option("--classification", default=None, type=_CLASSIFICATION_CHOICES,
              help="New classification for all cases.")
@pass_context
def bulk_update(ctx, numbers, input_file, status, classification) -> None:
    """Bulk update up to 200 cases.

    Provide case numbers via --numbers or --input-file.

    Examples:
        limacharlie case bulk-update --numbers 1,2,3 --status closed
        limacharlie case bulk-update --input-file numbers.txt \\
            --classification false_positive
    """
    case_numbers = _parse_number_list(numbers, input_file)
    if not case_numbers:
        raise click.UsageError("Provide case numbers via --numbers or --input-file.")

    fields: dict[str, Any] = {}
    if status:
        fields["status"] = status
    if classification:
        fields["classification"] = classification
    if not fields:
        raise click.UsageError("Provide at least --status or --classification.")

    t = _get_cases(ctx)
    data = t.bulk_update(case_numbers, **fields)
    _output(ctx, data)


def _parse_number_list(numbers_str: str | None, input_file: str | None) -> list[int]:
    """Parse case numbers from comma-separated string or file."""
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
@click.option("--target", required=True, type=int, help="Target case number (receives merged content).")
@click.option("--sources", required=True, help="Comma-separated source case numbers to merge.")
@pass_context
def merge(ctx, target, sources) -> None:
    """Merge source cases into a target case.

    Detections are moved to the target; source cases are closed.

    Example:
        limacharlie case merge --target 10 --sources 11,12
    """
    source_numbers = [int(s.strip()) for s in sources.split(",") if s.strip()]
    if not source_numbers:
        raise click.UsageError("Provide at least one source case number.")

    t = _get_cases(ctx)
    data = t.merge(target, source_numbers)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# entity (nested group)
# ---------------------------------------------------------------------------

@group.group("entity")
def entity_group() -> None:
    """Manage case entities (IOCs).

    Entities represent indicators of compromise found during
    investigation: IPs, domains, hashes, URLs, users, etc.
    """


@entity_group.command("list")
@click.option("--case", required=True, type=int, help="Case number.")
@pass_context
def entity_list(ctx, case) -> None:
    """List entities on a case.

    Example:
        limacharlie case entity list --case 42
    """
    t = _get_cases(ctx)
    data = t.list_entities(case)
    _output(ctx, data)


@entity_group.command("add")
@click.option("--case", required=True, type=int, help="Case number.")
@click.option("--type", "entity_type", required=True, type=_ENTITY_TYPE_CHOICES, help="Entity type.")
@click.option("--value", "entity_value", required=True, help="Entity value (max 1024 chars).")
@click.option("--note", default=None, help="Analyst note (max 2048 chars).")
@click.option("--verdict", default=None, type=_VERDICT_CHOICES, help="Verdict assessment.")
@pass_context
def entity_add(ctx, case, entity_type, entity_value, note, verdict) -> None:
    """Add an entity to a case.

    Examples:
        limacharlie case entity add --case 42 \\
            --type ip --value "10.0.0.1" --verdict malicious
        limacharlie case entity add --case 42 \\
            --type hash --value "d41d8..." --note "In startup folder"
    """
    t = _get_cases(ctx)
    data = t.add_entity(
        case, entity_type, entity_value,
        note=note, verdict=verdict,
    )
    _output(ctx, data)


@entity_group.command("update")
@click.option("--case", required=True, type=int, help="Case number.")
@click.option("--entity-id", required=True, help="Entity ID to update.")
@click.option("--note", default=None, help="Analyst note (max 2048 chars).")
@click.option("--verdict", default=None, type=_VERDICT_CHOICES, help="Verdict assessment.")
@pass_context
def entity_update(ctx, case, entity_id, note, verdict) -> None:
    """Update an entity on a case.

    Example:
        limacharlie case entity update --case 42 \\
            --entity-id <EID> --verdict malicious
    """
    if note is None and verdict is None:
        raise click.UsageError("Provide at least one field to update.")

    t = _get_cases(ctx)
    data = t.update_entity(case, entity_id, note=note, verdict=verdict)
    _output(ctx, data)


@entity_group.command("remove")
@click.option("--case", required=True, type=int, help="Case number.")
@click.option("--entity-id", required=True, help="Entity ID to remove.")
@pass_context
def entity_remove(ctx, case, entity_id) -> None:
    """Remove an entity from a case.

    Example:
        limacharlie case entity remove --case 42 --entity-id <EID>
    """
    t = _get_cases(ctx)
    data = t.remove_entity(case, entity_id)
    _output(ctx, data)


@entity_group.command("search")
@click.option("--type", "entity_type", required=True, type=_ENTITY_TYPE_CHOICES, help="Entity type.")
@click.option("--value", "entity_value", required=True, help="Entity value to search for.")
@pass_context
def entity_search(ctx, entity_type, entity_value) -> None:
    """Search for an entity across all cases.

    Examples:
        limacharlie case entity search --type ip --value "10.0.0.1"
        limacharlie case entity search --type domain --value "evil.com"
    """
    t = _get_cases(ctx)
    data = t.search_entities(entity_type, entity_value)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# telemetry (nested group)
# ---------------------------------------------------------------------------

@group.group("telemetry")
def telemetry_group() -> None:
    """Manage case telemetry references.

    Link LimaCharlie telemetry events to cases by atom+sensor ID
    for investigation context without storing full event payloads.
    """


@telemetry_group.command("list")
@click.option("--case", required=True, type=int, help="Case number.")
@pass_context
def telemetry_list(ctx, case) -> None:
    """List telemetry references on a case.

    Example:
        limacharlie case telemetry list --case 42
    """
    t = _get_cases(ctx)
    data = t.list_telemetry(case)
    _output(ctx, data)


@telemetry_group.command("add")
@click.option("--case", required=True, type=int, help="Case number.")
@click.option("--event", "event_json", required=True,
              help="Full LC event JSON object.")
@click.option("--note", default=None, help="Analyst note (max 2048 chars).")
@click.option("--verdict", default=None, type=_VERDICT_CHOICES, help="Verdict assessment.")
@pass_context
def telemetry_add(ctx, case, event_json, note, verdict) -> None:
    """Link a telemetry event to a case.

    Example:
        limacharlie case telemetry add --case 42 \\
            --event '<full LC event JSON>' --verdict suspicious
    """
    try:
        event = json.loads(event_json)
    except json.JSONDecodeError as exc:
        raise click.BadParameter(
            f"invalid JSON for --event: {exc}",
            param_hint="--event",
        )
    t = _get_cases(ctx)
    data = t.add_telemetry(
        case, event,
        note=note, verdict=verdict,
    )
    _output(ctx, data)


@telemetry_group.command("update")
@click.option("--case", required=True, type=int, help="Case number.")
@click.option("--telemetry-id", required=True, help="Telemetry reference ID.")
@click.option("--note", default=None, help="Analyst note (max 2048 chars).")
@click.option("--verdict", default=None, type=_VERDICT_CHOICES, help="Verdict assessment.")
@pass_context
def telemetry_update(ctx, case, telemetry_id, note, verdict) -> None:
    """Update a telemetry reference on a case.

    Example:
        limacharlie case telemetry update --case 42 \\
            --telemetry-id <TID> --verdict malicious
    """
    if note is None and verdict is None:
        raise click.UsageError("Provide at least one field to update.")

    t = _get_cases(ctx)
    data = t.update_telemetry(case, telemetry_id, note=note, verdict=verdict)
    _output(ctx, data)


@telemetry_group.command("remove")
@click.option("--case", required=True, type=int, help="Case number.")
@click.option("--telemetry-id", required=True, help="Telemetry reference ID.")
@pass_context
def telemetry_remove(ctx, case, telemetry_id) -> None:
    """Remove a telemetry reference from a case.

    Example:
        limacharlie case telemetry remove --case 42 \\
            --telemetry-id <TID>
    """
    t = _get_cases(ctx)
    data = t.remove_telemetry(case, telemetry_id)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# artifact (nested group)
# ---------------------------------------------------------------------------

@group.group("artifact")
def artifact_group() -> None:
    """Manage case forensic artifacts.

    Reference external forensic data (PCAPs, memory dumps, disk
    images, log exports) attached to cases for investigation.
    """


@artifact_group.command("list")
@click.option("--case", required=True, type=int, help="Case number.")
@pass_context
def artifact_list(ctx, case) -> None:
    """List artifacts on a case.

    Example:
        limacharlie case artifact list --case 42
    """
    t = _get_cases(ctx)
    data = t.list_artifacts(case)
    _output(ctx, data)


@artifact_group.command("add")
@click.option("--case", required=True, type=int, help="Case number.")
@click.option("--path", required=True, help="Artifact path or location.")
@click.option("--source", required=True, help="Artifact source identifier.")
@click.option("--type", "artifact_type", default=None,
              help="Artifact type (e.g., pcap, memory_dump, disk_image, log_export).")
@click.option("--note", default=None, help="Analyst note (max 2048 chars).")
@click.option("--verdict", default=None, type=_VERDICT_CHOICES, help="Verdict assessment.")
@pass_context
def artifact_add(ctx, case, path, source, artifact_type, note, verdict) -> None:
    """Add a forensic artifact reference to a case.

    Examples:
        limacharlie case artifact add --case 42 \\
            --path "/captures/incident.pcap" --source "sensor-01" \\
            --type pcap --note "Network capture"
        limacharlie case artifact add --case 42 \\
            --path "/dumps/mem.dmp" --source "edr" \\
            --type memory_dump --verdict suspicious
    """
    t = _get_cases(ctx)
    data = t.add_artifact(
        case, path, source,
        artifact_type=artifact_type, note=note, verdict=verdict,
    )
    _output(ctx, data)


@artifact_group.command("remove")
@click.option("--case", required=True, type=int, help="Case number.")
@click.option("--artifact-id", required=True, help="Artifact ID to remove.")
@pass_context
def artifact_remove(ctx, case, artifact_id) -> None:
    """Remove an artifact from a case.

    Example:
        limacharlie case artifact remove --case 42 \\
            --artifact-id <AID>
    """
    t = _get_cases(ctx)
    data = t.remove_artifact(case, artifact_id)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# detection (nested group)
# ---------------------------------------------------------------------------

@group.group("detection")
def detection_group() -> None:
    """Manage detections linked to cases.

    Link or unlink LimaCharlie detection records to cases for
    tracking which detections triggered an investigation.
    """


@detection_group.command("list")
@click.option("--case", required=True, type=int, help="Case number.")
@pass_context
def detection_list(ctx, case) -> None:
    """List detections linked to a case.

    Example:
        limacharlie case detection list --case 42
    """
    t = _get_cases(ctx)
    data = t.list_detections(case)
    _output(ctx, data)


@detection_group.command("add")
@click.option("--case", required=True, type=int, help="Case number.")
@click.option("--detection", "detection_json", required=True,
              help="Full detection JSON object.")
@pass_context
def detection_add(ctx, case, detection_json) -> None:
    """Link a detection to a case.

    Example:
        limacharlie case detection add --case 42 \\
            --detection '<full detection JSON>'
    """
    try:
        detection = json.loads(detection_json)
    except json.JSONDecodeError as exc:
        raise click.BadParameter(
            f"invalid JSON for --detection: {exc}",
            param_hint="--detection",
        )
    t = _get_cases(ctx)
    data = t.add_detection(case, detection)
    _output(ctx, data)


@detection_group.command("remove")
@click.option("--case", required=True, type=int, help="Case number.")
@click.option("--detection-id", required=True, help="Detection ID to unlink.")
@pass_context
def detection_remove(ctx, case, detection_id) -> None:
    """Remove a detection link from a case.

    Example:
        limacharlie case detection remove --case 42 \\
            --detection-id <DET_ID>
    """
    t = _get_cases(ctx)
    data = t.remove_detection(case, detection_id)
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
        limacharlie case report \\
            --from 2026-01-01T00:00:00Z --to 2026-02-01T00:00:00Z
        limacharlie case report \\
            --from 2026-01-01T00:00:00Z --to 2026-02-01T00:00:00Z \\
            --group-by severity
    """
    t = _get_cases(ctx)
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
    """Get real-time case counts and SLA breach status.

    Example:
        limacharlie case dashboard
    """
    t = _get_cases(ctx)
    data = t.dashboard_counts()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# config-get
# ---------------------------------------------------------------------------

@group.command("config-get")
@pass_context
def config_get(ctx) -> None:
    """Get cases configuration.

    Example:
        limacharlie case config-get
    """
    t = _get_cases(ctx)
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
    """Update cases configuration.

    Provide data via --input-file or stdin.

    Examples:
        limacharlie case config-set --input-file config.yaml
        cat config.json | limacharlie case config-set
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

    t = _get_cases(ctx)
    result = t.set_config(data)
    if not ctx.obj.quiet:
        click.echo("Cases configuration updated.")
    _output(ctx, result)


# ---------------------------------------------------------------------------
# assignees
# ---------------------------------------------------------------------------

@group.command()
@pass_context
def assignees(ctx) -> None:
    """List unique assignee emails.

    Example:
        limacharlie case assignees
    """
    t = _get_cases(ctx)
    data = t.list_assignees()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# orgs
# ---------------------------------------------------------------------------

@group.command()
@pass_context
def orgs(ctx) -> None:
    """List organizations subscribed to ext-cases.

    Returns OIDs the current user can access that have cases enabled.

    Example:
        limacharlie case orgs
    """
    t = _get_cases(ctx)
    data = t.list_orgs()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# tag (nested group)
# ---------------------------------------------------------------------------

@group.group("tag")
def tag_group() -> None:
    """Manage case tags.

    Set, add, or remove tags on cases.  Tags are free-form strings
    used for categorization and filtering.
    """


@tag_group.command("set")
@click.option("--case-number", "case_number", required=True, type=int, help="Case number.")
@click.option("--tag", "-t", "tags", multiple=True, required=True, help="Tag value (repeatable).")
@pass_context
def tag_set(ctx, case_number, tags) -> None:
    """Replace all tags on a case.

    Examples:
        limacharlie case tag set --case-number 42 --tag phishing
        limacharlie case tag set --case-number 42 -t phishing -t urgent
    """
    t = _get_cases(ctx)
    data = t.update_case(case_number, tags=list(tags))
    _output(ctx, data)


@tag_group.command("add")
@click.option("--case-number", "case_number", required=True, type=int, help="Case number.")
@click.option("--tag", "-t", "tags", multiple=True, required=True, help="Tag value to add (repeatable).")
@pass_context
def tag_add(ctx, case_number, tags) -> None:
    """Add tags to a case (merged with existing).

    Examples:
        limacharlie case tag add --case-number 42 --tag new-tag
        limacharlie case tag add --case-number 42 -t phishing -t urgent
    """
    tk = _get_cases(ctx)
    current = tk.get_case(case_number)
    existing = current.get("case", current).get("tags") or []
    seen = {}
    for tag in existing + list(tags):
        key = tag.lower()
        if key not in seen:
            seen[key] = tag
    merged = list(seen.values())
    data = tk.update_case(case_number, tags=merged)
    _output(ctx, data)


@tag_group.command("remove")
@click.option("--case-number", "case_number", required=True, type=int, help="Case number.")
@click.option("--tag", "-t", "tags", multiple=True, required=True, help="Tag value to remove (repeatable).")
@pass_context
def tag_remove(ctx, case_number, tags) -> None:
    """Remove tags from a case.

    Examples:
        limacharlie case tag remove --case-number 42 --tag old-tag
        limacharlie case tag remove --case-number 42 -t phishing -t urgent
    """
    tk = _get_cases(ctx)
    current = tk.get_case(case_number)
    existing = current.get("case", current).get("tags") or []
    to_remove = {t.lower() for t in tags}
    remaining = [t for t in existing if t.lower() not in to_remove]
    data = tk.update_case(case_number, tags=remaining)
    _output(ctx, data)
