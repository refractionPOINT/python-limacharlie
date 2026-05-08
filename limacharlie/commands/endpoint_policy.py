"""Endpoint policy commands for LimaCharlie CLI v2.

Commands for isolating sensors from the network, checking isolation
status, and sealing/unsealing sensor configuration.  Network isolation
prevents a compromised endpoint from communicating with anything other
than the LimaCharlie cloud, cutting off lateral movement and data
exfiltration.
"""

from __future__ import annotations

from typing import Any

import click

from ..cli import pass_context
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.sensor import Sensor
from ..output import format_output, detect_output_format
from ..discovery import register_explain


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _output(ctx: click.Context, data: Any) -> None:
    fmt = ctx.obj.output_format or detect_output_format()
    if not ctx.obj.quiet:
        click.echo(format_output(data, fmt))


def _get_sensor(ctx: click.Context, sid: str) -> Sensor:
    client = Client(oid=ctx.obj.oid, environment=ctx.obj.environment, print_debug_fn=ctx.obj.debug_fn, debug_full_response=ctx.obj.debug_full, debug_curl=ctx.obj.debug_curl, debug_verbose=ctx.obj.debug_verbose)
    org = Organization(client)
    return Sensor(org, sid)


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------

@click.group("endpoint-policy")
def group() -> None:
    """Manage sensor network isolation.

    Network isolation prevents an endpoint from communicating with
    anything other than the LimaCharlie cloud.  This is a key
    incident-response capability for containing compromised hosts.
    """


# ---------------------------------------------------------------------------
# isolate
# ---------------------------------------------------------------------------

_EXPLAIN_ISOLATE = """\
Network-isolate a sensor so it can only communicate with the LimaCharlie
cloud.  All other network traffic (outbound and inbound) is blocked at
the kernel level on the endpoint.  This is a critical incident-response
action that prevents lateral movement and data exfiltration from a
potentially compromised host.

While isolated, the sensor remains fully manageable via LimaCharlie
tasking.  You can still:
  - Collect files and memory dumps
  - Run YARA scans
  - Kill or suspend processes
  - List processes, services, and network connections
  - Deploy payloads

The underlying sensor command is 'segregate_network'.  Use
'limacharlie endpoint-policy rejoin --sid <SID>' (rejoin_network)
to restore connectivity when the investigation is complete.

This is a disruptive operation: the endpoint will lose all network
connectivity except to LimaCharlie.
"""
register_explain("endpoint-policy.isolate", _EXPLAIN_ISOLATE)


@group.command()
@click.option("--sid", required=True, help="Sensor ID (UUID) to isolate.")
@pass_context
def isolate(ctx: click.Context, sid: str) -> None:
    sensor = _get_sensor(ctx, sid)
    data = sensor.isolate()
    if not ctx.obj.quiet:
        click.echo(f"Sensor {sid} is now network-isolated.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# rejoin
# ---------------------------------------------------------------------------

_EXPLAIN_REJOIN = """\
Remove network isolation from a sensor, restoring full network
connectivity.  This should be done only after the incident has been
contained and the endpoint has been verified as clean.

If the sensor is not currently isolated, this command has no effect.
"""
register_explain("endpoint-policy.rejoin", _EXPLAIN_REJOIN)


@group.command()
@click.option("--sid", required=True, help="Sensor ID (UUID) to rejoin.")
@pass_context
def rejoin(ctx: click.Context, sid: str) -> None:
    sensor = _get_sensor(ctx, sid)
    data = sensor.rejoin()
    if not ctx.obj.quiet:
        click.echo(f"Sensor {sid} network isolation removed.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

_EXPLAIN_STATUS = """\
Check whether a specific sensor is currently network-isolated.  Returns
a boolean indicating the isolation state.  Use this to verify isolation
was applied correctly, or to check status before taking further action.
"""
register_explain("endpoint-policy.status", _EXPLAIN_STATUS)


@group.command()
@click.option("--sid", required=True, help="Sensor ID (UUID).")
@pass_context
def status(ctx: click.Context, sid: str) -> None:
    sensor = _get_sensor(ctx, sid)
    is_isolated = sensor.is_isolated()
    _output(ctx, {"sid": sid, "is_isolated": is_isolated})


# ---------------------------------------------------------------------------
# seal
# ---------------------------------------------------------------------------

_EXPLAIN_SEAL = """\
Seal a sensor so that its configuration is locked and cannot be changed
remotely.  This is a protective measure that prevents tampering with
the sensor configuration on a compromised endpoint.

While sealed, the sensor continues to operate normally (collecting
telemetry, executing D&R rules) but rejects configuration changes
such as tag modifications, exfil rule changes, and FIM updates.
Tasking commands (os_processes, file_get, etc.) still work.

Use 'limacharlie endpoint-policy unseal --sid <SID>' to restore the
ability to modify the sensor configuration.

The --confirm flag is required to proceed.
"""
register_explain("endpoint-policy.seal", _EXPLAIN_SEAL)


@group.command()
@click.option("--sid", required=True, help="Sensor ID (UUID) to seal.")
@click.option("--confirm", is_flag=True, default=False, help="Confirm seal operation (required).")
@pass_context
def seal(ctx: click.Context, sid: str, confirm: bool) -> None:
    if not confirm:
        click.echo(
            "Error: Disruptive operation requires --confirm flag.\n"
            "Suggestion: Re-run with --confirm to seal the sensor.",
            err=True,
        )
        ctx.exit(4)
        return

    sensor = _get_sensor(ctx, sid)
    data = sensor.seal()
    if not ctx.obj.quiet:
        click.echo(f"Sensor {sid} is now sealed.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# unseal
# ---------------------------------------------------------------------------

_EXPLAIN_UNSEAL = """\
Remove the seal from a sensor, restoring the ability to modify its
configuration remotely.  This should be done only after the threat
has been mitigated and the endpoint has been verified as clean.

If the sensor is not currently sealed, this command has no effect.
The --confirm flag is required to proceed.
"""
register_explain("endpoint-policy.unseal", _EXPLAIN_UNSEAL)


@group.command()
@click.option("--sid", required=True, help="Sensor ID (UUID) to unseal.")
@click.option("--confirm", is_flag=True, default=False, help="Confirm unseal operation (required).")
@pass_context
def unseal(ctx: click.Context, sid: str, confirm: bool) -> None:
    if not confirm:
        click.echo(
            "Error: Disruptive operation requires --confirm flag.\n"
            "Suggestion: Re-run with --confirm to unseal the sensor.",
            err=True,
        )
        ctx.exit(4)
        return

    sensor = _get_sensor(ctx, sid)
    data = sensor.unseal()
    if not ctx.obj.quiet:
        click.echo(f"Sensor {sid} seal removed.")
    _output(ctx, data)
