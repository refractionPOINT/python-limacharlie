"""Network policy commands for LimaCharlie CLI v2.

Commands for isolating sensors from the network and checking isolation
status.  Network isolation prevents a compromised endpoint from
communicating with anything other than the LimaCharlie cloud, cutting
off lateral movement and data exfiltration.
"""

import click

from ..cli import pass_context
from ..config import resolve_credentials
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.sensor import Sensor
from ..output import format_output, detect_output_format
from ..discovery import register_explain


# ---------------------------------------------------------------------------
# Explain texts
# ---------------------------------------------------------------------------

_EXPLAIN_ISOLATE = """\
Network-isolate a sensor so it can only communicate with the LimaCharlie
cloud.  All other network traffic (outbound and inbound) is blocked at
the endpoint.  This is a critical incident-response action that prevents
lateral movement and data exfiltration from a potentially compromised
host.

While isolated, the sensor remains manageable via LimaCharlie tasking.
You can still collect memory dumps, run YARA scans, or kill processes
on the isolated endpoint.

Use 'limacharlie net-policy rejoin --sid <SID>' to restore network
connectivity when the investigation is complete.

This is a disruptive operation: the endpoint will lose all network
connectivity except to LimaCharlie.  The --confirm flag is not
required but be certain before executing.
"""

_EXPLAIN_REJOIN = """\
Remove network isolation from a sensor, restoring full network
connectivity.  This should be done only after the incident has been
contained and the endpoint has been verified as clean.

If the sensor is not currently isolated, this command has no effect.
"""

_EXPLAIN_STATUS = """\
Check whether a specific sensor is currently network-isolated.  Returns
a boolean indicating the isolation state.  Use this to verify isolation
was applied correctly, or to check status before taking further action.
"""

_EXPLAIN_SEAL = """\
Seal a sensor so that its configuration is locked and cannot be changed
remotely.  This is a protective measure that prevents tampering with
the sensor configuration on a compromised endpoint.

While sealed, the sensor continues to operate normally but rejects any
configuration changes.  Use 'limacharlie net-policy unseal --sid <SID>'
to restore the ability to modify the sensor configuration.

This is a disruptive operation: the endpoint will reject configuration
changes.  The --confirm flag is required to proceed.
"""

_EXPLAIN_UNSEAL = """\
Remove the seal from a sensor, restoring the ability to modify its
configuration remotely.  This should be done only after the threat
has been mitigated and the endpoint has been verified as clean.

If the sensor is not currently sealed, this command has no effect.
The --confirm flag is required to proceed.
"""

register_explain("net-policy.isolate", _EXPLAIN_ISOLATE)
register_explain("net-policy.rejoin", _EXPLAIN_REJOIN)
register_explain("net-policy.status", _EXPLAIN_STATUS)
register_explain("net-policy.seal", _EXPLAIN_SEAL)
register_explain("net-policy.unseal", _EXPLAIN_UNSEAL)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_explain_callback(text):
    def callback(ctx, param, value):
        if value:
            click.echo(text.strip())
            ctx.exit()
    return callback


def _output(ctx, data):
    fmt = ctx.obj.output_format or detect_output_format()
    if not ctx.obj.quiet:
        click.echo(format_output(data, fmt))


def _get_sensor(ctx, sid):
    creds = resolve_credentials(oid=ctx.obj.oid, environment=ctx.obj.environment)
    client = Client(oid=creds["oid"], api_key=creds.get("api_key"), uid=creds.get("uid"))
    org = Organization(client)
    return Sensor(org, sid)


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------

@click.group("net-policy")
def group():
    """Manage sensor network isolation.

    Network isolation prevents an endpoint from communicating with
    anything other than the LimaCharlie cloud.  This is a key
    incident-response capability for containing compromised hosts.
    """


# ---------------------------------------------------------------------------
# isolate
# ---------------------------------------------------------------------------

@group.command()
@click.option("--sid", required=True, help="Sensor ID (UUID) to isolate.")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_ISOLATE),
    help="Show detailed explanation of this command.",
)
@pass_context
def isolate(ctx, sid):
    """Network-isolate a sensor (block all non-LC traffic).

    Example:
        limacharlie net-policy isolate --sid <SID>
    """
    sensor = _get_sensor(ctx, sid)
    data = sensor.isolate()
    if not ctx.obj.quiet:
        click.echo(f"Sensor {sid} is now network-isolated.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# rejoin
# ---------------------------------------------------------------------------

@group.command()
@click.option("--sid", required=True, help="Sensor ID (UUID) to rejoin.")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_REJOIN),
    help="Show detailed explanation of this command.",
)
@pass_context
def rejoin(ctx, sid):
    """Remove network isolation from a sensor.

    Example:
        limacharlie net-policy rejoin --sid <SID>
    """
    sensor = _get_sensor(ctx, sid)
    data = sensor.rejoin()
    if not ctx.obj.quiet:
        click.echo(f"Sensor {sid} network isolation removed.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

@group.command()
@click.option("--sid", required=True, help="Sensor ID (UUID).")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_STATUS),
    help="Show detailed explanation of this command.",
)
@pass_context
def status(ctx, sid):
    """Check the network isolation status of a sensor.

    Example:
        limacharlie net-policy status --sid <SID>
    """
    sensor = _get_sensor(ctx, sid)
    is_isolated = sensor.is_isolated()
    _output(ctx, {"sid": sid, "is_isolated": is_isolated})


# ---------------------------------------------------------------------------
# seal
# ---------------------------------------------------------------------------

@group.command()
@click.option("--sid", required=True, help="Sensor ID (UUID) to seal.")
@click.option("--confirm", is_flag=True, default=False, help="Confirm seal operation (required).")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_SEAL),
    help="Show detailed explanation of this command.",
)
@pass_context
def seal(ctx, sid, confirm):
    """Seal a sensor (lock its configuration).

    This is a disruptive operation.  Pass --confirm to proceed.

    Example:
        limacharlie net-policy seal --sid <SID> --confirm
    """
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

@group.command()
@click.option("--sid", required=True, help="Sensor ID (UUID) to unseal.")
@click.option("--confirm", is_flag=True, default=False, help="Confirm unseal operation (required).")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_UNSEAL),
    help="Show detailed explanation of this command.",
)
@pass_context
def unseal(ctx, sid, confirm):
    """Remove the seal from a sensor (unlock its configuration).

    This is a disruptive operation.  Pass --confirm to proceed.

    Example:
        limacharlie net-policy unseal --sid <SID> --confirm
    """
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
