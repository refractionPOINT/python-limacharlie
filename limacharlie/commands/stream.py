"""Streaming commands for LimaCharlie CLI v2.

Commands for streaming events, detections, and audit logs in
real-time from the LimaCharlie cloud using pull-mode spouts or
push-mode firehose listeners.
"""

from __future__ import annotations

import json

import click

from ..cli import pass_context
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.spout import Spout
from ..sdk.firehose import Firehose
from ..discovery import register_explain


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_org(ctx: click.Context) -> Organization:
    client = Client(oid=ctx.obj.oid, environment=ctx.obj.environment)
    return Organization(client)


def _stream_loop(spout: Spout) -> None:
    """Read from spout queue and print each message until interrupted."""
    try:
        while True:
            data = spout.get(timeout=5)
            if data is not None:
                click.echo(json.dumps(data, default=str))
    except KeyboardInterrupt:
        pass
    finally:
        spout.shutdown()


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------

@click.group("stream")
def group() -> None:
    """Stream events, detections, and audit logs in real-time.

    Opens a pull-mode connection to the LimaCharlie cloud and
    prints data as it arrives.  Press Ctrl+C to stop streaming.
    """


# ---------------------------------------------------------------------------
# events
# ---------------------------------------------------------------------------

_EXPLAIN_EVENTS = """\
Stream sensor events in real-time.  Opens a pull-mode connection
(spout) to stream.limacharlie.io and prints each event as JSON.

Each event has the standard two-level structure:
  routing:  oid, sid, event_type, event_time, hostname, ext_ip, int_ip, tags
  event:    payload fields vary by event_type

Common event types you will see:
  NEW_PROCESS, DNS_REQUEST, NETWORK_CONNECTIONS, FILE_CREATE,
  MODULE_LOAD, CODE_IDENTITY, REGISTRY_WRITE, WEL

Use filters to narrow the stream:
  --tag     Only events from sensors with this tag.
  --sid     Only events from a specific sensor (by SID).
  --inv-id  Only events with a specific investigation ID.

Press Ctrl+C to stop streaming.

Examples:
  limacharlie stream events
  limacharlie stream events --tag server
  limacharlie stream events --sid <sensor-id>
"""
register_explain("stream.events", _EXPLAIN_EVENTS)


@group.command()
@click.option("--tag", default=None, help="Only events from sensors with this tag.")
@click.option("--sid", default=None, help="Only events from this sensor ID.")
@click.option("--inv-id", default=None, help="Only events with this investigation ID.")
@pass_context
def events(ctx: click.Context, tag: str | None, sid: str | None, inv_id: str | None) -> None:
    org = _get_org(ctx)
    spout = Spout(org, "event", tag=tag, sid=sid, inv_id=inv_id)
    if not ctx.obj.quiet:
        click.echo("Streaming events (Ctrl+C to stop)...", err=True)
    _stream_loop(spout)


# ---------------------------------------------------------------------------
# detections
# ---------------------------------------------------------------------------

_EXPLAIN_DETECTIONS = """\
Stream D&R detections in real-time.  Opens a pull-mode connection
(spout) and prints each detection as JSON.

Detection structure:
  cat          - detection name/category
  source       - rule source (dr-general, dr-managed, fp)
  detect_id    - unique detection identifier
  routing      - inherited from triggering event (sid, hostname, etc.)
  detect       - copy of the event data that triggered the detection
  detect_data  - structured IOCs extracted by the rule (optional)
  priority     - detection priority 0-10 (optional)
  source_rule  - name of the D&R rule that generated this

Use filters to narrow the stream:
  --cat  Only detections of a specific category.
  --sid  Only detections from a specific sensor.

Press Ctrl+C to stop streaming.

Examples:
  limacharlie stream detections
  limacharlie stream detections --cat lateral-movement
"""
register_explain("stream.detections", _EXPLAIN_DETECTIONS)


@group.command()
@click.option("--cat", default=None, help="Only detections of this category.")
@click.option("--sid", default=None, help="Only detections from this sensor ID.")
@pass_context
def detections(ctx: click.Context, cat: str | None, sid: str | None) -> None:
    org = _get_org(ctx)
    spout = Spout(org, "detect", cat=cat, sid=sid)
    if not ctx.obj.quiet:
        click.echo("Streaming detections (Ctrl+C to stop)...", err=True)
    _stream_loop(spout)


# ---------------------------------------------------------------------------
# audit
# ---------------------------------------------------------------------------

_EXPLAIN_AUDIT = """\
Stream audit logs in real-time.  Shows all administrative actions
performed on the organization as they happen.

Audit log structure:
  oid    - organization ID
  ts     - ISO 8601 timestamp
  etype  - event type (config_change, api_call, user_action, error)
  msg    - human-readable description
  origin - source of action (api, ui, cli, system)
  ident  - identity performing the action (email or API key name)
  entity - object acted upon (type, name, hive)
  mtd    - action metadata (action type, source IP, user agent)

Press Ctrl+C to stop streaming.

Example:
  limacharlie stream audit
"""
register_explain("stream.audit", _EXPLAIN_AUDIT)


@group.command()
@pass_context
def audit(ctx: click.Context) -> None:
    org = _get_org(ctx)
    spout = Spout(org, "audit")
    if not ctx.obj.quiet:
        click.echo("Streaming audit logs (Ctrl+C to stop)...", err=True)
    _stream_loop(spout)


# ---------------------------------------------------------------------------
# firehose
# ---------------------------------------------------------------------------

_EXPLAIN_FIREHOSE = """\
Start a push-mode firehose listener.  Creates a TLS server that
LimaCharlie connects to and pushes data in real-time.  This is the
inverse of pull-mode spouts: instead of polling, LC pushes data to
your server.

The firehose auto-registers itself as an output in LimaCharlie and
cleans up on shutdown.  Data arrives in the same JSON structures as
described in 'stream events' / 'stream detections' / 'stream audit'.

Parameters:
  --listen       Interface and port to bind (e.g., "0.0.0.0:4444").
  --data-type    Stream type: event (default), detect, or audit.
  --name         Output name registered in LC (default: cli-firehose).
  --public-dest  Public IP:port for LC to connect to (auto-detected
                 if omitted, but set this if behind NAT/firewall).
  --tls-cert/--tls-key  PEM certificate and key files.  If omitted,
                 a self-signed certificate is generated automatically.

Press Ctrl+C to stop and de-register the output.

Examples:
  limacharlie stream firehose --listen 0.0.0.0:4444
  limacharlie stream firehose --listen 0.0.0.0:443 --tls-cert cert.pem --tls-key key.pem
  limacharlie stream firehose --listen 0.0.0.0:4444 --data-type detect
"""
register_explain("stream.firehose", _EXPLAIN_FIREHOSE)


def _firehose_loop(fh: Firehose) -> None:
    """Read from firehose queue and print each message until interrupted."""
    try:
        while True:
            data = fh.get(timeout=5)
            if data is not None:
                click.echo(json.dumps(data, default=str))
    except KeyboardInterrupt:
        pass
    finally:
        fh.shutdown()


@group.command()
@click.option("--listen", required=True, help="Interface and port to listen on (e.g., 0.0.0.0:4444).")
@click.option("--tls-cert", default=None, type=click.Path(exists=True), help="Path to PEM TLS certificate file.")
@click.option("--tls-key", default=None, type=click.Path(exists=True), help="Path to PEM TLS key file.")
@click.option(
    "--data-type", default="event",
    type=click.Choice(["event", "detect", "audit"], case_sensitive=False),
    help="Type of data to receive (default: event).",
)
@click.option("--name", default=None, help="Name to register as an Output in LimaCharlie (auto-generated if omitted).")
@click.option("--public-dest", default=None, help="Public IP:port for LC to connect to (auto-detected if omitted).")
@pass_context
def firehose(ctx: click.Context, listen: str, tls_cert: str | None, tls_key: str | None, data_type: str, name: str | None, public_dest: str | None) -> None:
    org = _get_org(ctx)
    # Use a default name based on CLI if not specified.
    fh_name = name or "cli-firehose"
    fh = Firehose(
        org,
        listen,
        data_type,
        public_dest=public_dest,
        name=fh_name,
        ssl_cert=tls_cert,
        ssl_key=tls_key,
        is_delete_on_failure=True,
    )
    if not ctx.obj.quiet:
        click.echo(f"Firehose listening on {listen} for {data_type} data (Ctrl+C to stop)...", err=True)
    _firehose_loop(fh)
