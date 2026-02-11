"""Streaming commands for LimaCharlie CLI v2.

Commands for streaming events, detections, and audit logs in
real-time from the LimaCharlie cloud using pull-mode spouts.
"""

import json
import signal
import sys

import click

from ..cli import pass_context
from ..config import resolve_credentials
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.spout import Spout
from ..discovery import register_explain


# ---------------------------------------------------------------------------
# Explain texts
# ---------------------------------------------------------------------------

_EXPLAIN_EVENTS = """\
Stream sensor events in real-time.  Opens a pull-mode connection
to stream.limacharlie.io and prints each event as it arrives.

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

_EXPLAIN_DETECTIONS = """\
Stream detections in real-time.  Opens a pull-mode connection
and prints each detection as it arrives.

Use filters to narrow the stream:
  --cat  Only detections of a specific category.
  --sid  Only detections from a specific sensor.

Press Ctrl+C to stop streaming.

Examples:
  limacharlie stream detections
  limacharlie stream detections --cat lateral-movement
"""

_EXPLAIN_AUDIT = """\
Stream audit logs in real-time.  Shows all administrative actions
performed on the organization as they happen.

Press Ctrl+C to stop streaming.

Example:
  limacharlie stream audit
"""

register_explain("stream.events", _EXPLAIN_EVENTS)
register_explain("stream.detections", _EXPLAIN_DETECTIONS)
register_explain("stream.audit", _EXPLAIN_AUDIT)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_explain_callback(text):
    def callback(ctx, param, value):
        if value:
            click.echo(text.strip())
            ctx.exit()
    return callback


def _get_org(ctx):
    creds = resolve_credentials(oid=ctx.obj.oid, environment=ctx.obj.environment)
    client = Client(oid=creds["oid"], api_key=creds.get("api_key"), uid=creds.get("uid"))
    return Organization(client)


def _stream_loop(spout):
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
def group():
    """Stream events, detections, and audit logs in real-time.

    Opens a pull-mode connection to the LimaCharlie cloud and
    prints data as it arrives.  Press Ctrl+C to stop streaming.
    """


# ---------------------------------------------------------------------------
# events
# ---------------------------------------------------------------------------

@group.command()
@click.option("--tag", default=None, help="Only events from sensors with this tag.")
@click.option("--sid", default=None, help="Only events from this sensor ID.")
@click.option("--inv-id", default=None, help="Only events with this investigation ID.")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_EVENTS),
    help="Show detailed explanation of this command.",
)
@pass_context
def events(ctx, tag, sid, inv_id):
    """Stream sensor events in real-time.

    Examples:
        limacharlie stream events
        limacharlie stream events --tag server
        limacharlie stream events --sid <sensor-id>
    """
    org = _get_org(ctx)
    spout = Spout(org, "event", tag=tag, sid=sid, inv_id=inv_id)
    if not ctx.obj.quiet:
        click.echo("Streaming events (Ctrl+C to stop)...", err=True)
    _stream_loop(spout)


# ---------------------------------------------------------------------------
# detections
# ---------------------------------------------------------------------------

@group.command()
@click.option("--cat", default=None, help="Only detections of this category.")
@click.option("--sid", default=None, help="Only detections from this sensor ID.")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_DETECTIONS),
    help="Show detailed explanation of this command.",
)
@pass_context
def detections(ctx, cat, sid):
    """Stream detections in real-time.

    Examples:
        limacharlie stream detections
        limacharlie stream detections --cat lateral-movement
    """
    org = _get_org(ctx)
    spout = Spout(org, "detect", cat=cat, sid=sid)
    if not ctx.obj.quiet:
        click.echo("Streaming detections (Ctrl+C to stop)...", err=True)
    _stream_loop(spout)


# ---------------------------------------------------------------------------
# audit
# ---------------------------------------------------------------------------

@group.command()
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_AUDIT),
    help="Show detailed explanation of this command.",
)
@pass_context
def audit(ctx):
    """Stream audit logs in real-time.

    Example:
        limacharlie stream audit
    """
    org = _get_org(ctx)
    spout = Spout(org, "audit")
    if not ctx.obj.quiet:
        click.echo("Streaming audit logs (Ctrl+C to stop)...", err=True)
    _stream_loop(spout)
