"""Streaming commands for LimaCharlie CLI v2.

Commands for streaming events, detections, and audit logs in
real-time from the LimaCharlie cloud using pull-mode spouts or
push-mode firehose listeners.
"""

from __future__ import annotations

from typing import Any, Callable

import json

import click

from ..cli import pass_context
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.spout import Spout
from ..sdk.firehose import Firehose
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

_EXPLAIN_FIREHOSE = """\
Start a push-mode firehose listener.  Creates a TLS server that
LimaCharlie connects to and pushes data (events, detections, or
audit logs) in real-time.

The --listen parameter specifies the interface and port to bind to
(e.g., "0.0.0.0:4444").  If no TLS certificate is provided, a
self-signed certificate is generated automatically.

The firehose auto-registers itself as an output in LimaCharlie.
Press Ctrl+C to stop.

Examples:
  limacharlie stream firehose --listen 0.0.0.0:4444
  limacharlie stream firehose --listen 0.0.0.0:443 --tls-cert cert.pem --tls-key key.pem
  limacharlie stream firehose --listen 0.0.0.0:4444 --data-type detect
"""

register_explain("stream.events", _EXPLAIN_EVENTS)
register_explain("stream.detections", _EXPLAIN_DETECTIONS)
register_explain("stream.audit", _EXPLAIN_AUDIT)
register_explain("stream.firehose", _EXPLAIN_FIREHOSE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_explain_callback(text: str) -> Callable[..., None]:
    def callback(ctx: click.Context, param: click.Parameter, value: Any) -> None:
        if value:
            click.echo(text.strip())
            ctx.exit()
    return callback


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
def events(ctx: click.Context, tag: str | None, sid: str | None, inv_id: str | None) -> None:
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
def detections(ctx: click.Context, cat: str | None, sid: str | None) -> None:
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
def audit(ctx: click.Context) -> None:
    """Stream audit logs in real-time.

    Example:
        limacharlie stream audit
    """
    org = _get_org(ctx)
    spout = Spout(org, "audit")
    if not ctx.obj.quiet:
        click.echo("Streaming audit logs (Ctrl+C to stop)...", err=True)
    _stream_loop(spout)


# ---------------------------------------------------------------------------
# firehose
# ---------------------------------------------------------------------------

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
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_FIREHOSE),
    help="Show detailed explanation of this command.",
)
@pass_context
def firehose(ctx: click.Context, listen: str, tls_cert: str | None, tls_key: str | None, data_type: str, name: str | None, public_dest: str | None) -> None:
    """Start a push-mode firehose listener.

    Creates a TLS server that LimaCharlie connects to and pushes
    data in real-time.  Press Ctrl+C to stop.

    Examples:
        limacharlie stream firehose --listen 0.0.0.0:4444
        limacharlie stream firehose --listen 0.0.0.0:443 \\
            --tls-cert cert.pem --tls-key key.pem
    """
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
