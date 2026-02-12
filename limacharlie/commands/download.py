"""Download commands for LimaCharlie CLI v2.

Commands for downloading sensor (EDR) installers and adapter binaries
for all supported platforms and architectures.
"""

import os
import sys

import click

from ..cli import pass_context
from ..output import format_output, detect_output_format
from ..discovery import register_explain
from ..sdk.downloads import (
    SENSOR_TARGETS,
    ADAPTER_TARGETS,
    download_binary,
    list_sensor_targets,
    list_adapter_targets,
)


# ---------------------------------------------------------------------------
# Default filenames
# ---------------------------------------------------------------------------

_SENSOR_FILENAMES = {
    ("windows", "64"): "lc_sensor_64.exe",
    ("windows", "32"): "lc_sensor_32.exe",
    ("windows", "arm64"): "lc_sensor_arm64.exe",
    ("windows", "msi64"): "lc_sensor_64.msi",
    ("windows", "msi32"): "lc_sensor_32.msi",
    ("linux", "64"): "lc_sensor_64",
    ("linux", "deb64"): "lc_sensor_64.deb",
    ("linux", "debarm64"): "lc_sensor_arm64.deb",
    ("linux", "alpine64"): "lc_sensor_alpine64",
    ("mac", "64"): "lc_sensor_64",
    ("mac", "arm64"): "lc_sensor_arm64",
    ("chrome", ""): "lc_sensor_chrome",
}

_ADAPTER_FILENAMES = {
    ("linux", "64"): "lc_adapter_linux_64",
    ("linux", "arm"): "lc_adapter_linux_arm",
    ("linux", "arm64"): "lc_adapter_linux_arm64",
    ("windows", "64"): "lc_adapter_windows_64.exe",
    ("mac", "64"): "lc_adapter_mac_64",
    ("mac", "arm64"): "lc_adapter_mac_arm64",
    ("aix", "ppc64"): "lc_adapter_aix_ppc64",
    ("freebsd", "64"): "lc_adapter_freebsd_64",
    ("openbsd", "64"): "lc_adapter_openbsd_64",
    ("netbsd", "64"): "lc_adapter_netbsd_64",
    ("solaris", "64"): "lc_adapter_solaris_64",
}


# ---------------------------------------------------------------------------
# Explain texts
# ---------------------------------------------------------------------------

_EXPLAIN_SENSOR = """\
Download a sensor (EDR agent) installer for a specific platform and
architecture.  Sensors are the endpoint agents that collect telemetry
and respond to tasks from the LimaCharlie cloud.

The downloaded binary can be installed on an endpoint using an
installation key:
  ./lc_sensor_64 -i YOUR_INSTALLATION_KEY

Supported platforms: windows, linux, mac, chrome
Supported architectures vary by platform. Use --list to see all
available combinations.

Examples:
  limacharlie download sensor --platform linux --arch 64
  limacharlie download sensor --platform windows --arch msi64 -o ./sensor.msi
  limacharlie download sensor --platform mac --arch arm64
  limacharlie download sensor --list
"""

_EXPLAIN_ADAPTER = """\
Download an adapter (USP) binary for a specific platform and
architecture.  Adapters allow LimaCharlie to ingest data from sources
beyond the native sensor agent using the Universal Sensor Protocol.

Supported platforms: linux, windows, mac, aix, freebsd, openbsd,
netbsd, solaris

Examples:
  limacharlie download adapter --platform linux --arch 64
  limacharlie download adapter --platform mac --arch arm64 -o ./lc_adapter
  limacharlie download adapter --list
"""

_EXPLAIN_LIST = """\
List all available download targets for sensors and adapters.  Shows
every supported (platform, architecture) combination and its download
URL.

Examples:
  limacharlie download list
  limacharlie download list --output json
"""

register_explain("download.sensor", _EXPLAIN_SENSOR)
register_explain("download.adapter", _EXPLAIN_ADAPTER)
register_explain("download.list", _EXPLAIN_LIST)


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


def _download_and_save(ctx, kind, platform, arch, output_path):
    """Download a binary and write it to disk or stdout."""
    filenames = _SENSOR_FILENAMES if kind == "sensor" else _ADAPTER_FILENAMES

    if not ctx.obj.quiet:
        click.echo(f"Downloading {kind} for {platform}/{arch}...", err=True)

    data = download_binary(kind, platform, arch)

    if output_path is None:
        # Default filename in the current directory
        output_path = filenames.get((platform, arch), f"lc_{kind}_{platform}_{arch}")

    if output_path == "-":
        sys.stdout.buffer.write(data)
        return

    with open(output_path, "wb") as f:
        f.write(data)

    # Make executable on unix-like systems (not for .msi/.deb/.exe)
    if not output_path.endswith((".msi", ".deb", ".exe")):
        try:
            os.chmod(output_path, 0o755)
        except OSError:
            pass

    if not ctx.obj.quiet:
        size_mb = len(data) / (1024 * 1024)
        click.echo(f"Saved to {output_path} ({size_mb:.1f} MB)", err=True)


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------

@click.group("download")
def group():
    """Download sensor installers and adapter binaries.

    Download pre-built binaries for deploying LimaCharlie sensors (EDR
    agents) and adapters (USP) across all supported platforms.
    """


# ---------------------------------------------------------------------------
# download sensor
# ---------------------------------------------------------------------------

@group.command("sensor")
@click.option(
    "--platform", "platform",
    type=click.Choice(sorted({p for p, _ in SENSOR_TARGETS}), case_sensitive=False),
    default=None,
    help="Target platform.",
)
@click.option(
    "--arch", "arch",
    default=None,
    help="Target architecture (e.g. 64, arm64, msi64, deb64).",
)
@click.option(
    "-o", "--output-path", default=None,
    type=click.Path(),
    help="Path to save the file. Use '-' for stdout. Defaults to a sensible filename.",
)
@click.option(
    "--list", "show_list", is_flag=True, default=False,
    help="List available sensor platforms and architectures.",
)
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_SENSOR),
    help="Show detailed explanation of this command.",
)
@pass_context
def sensor(ctx, platform, arch, output_path, show_list):
    """Download a sensor (EDR) installer.

    Downloads the sensor agent binary for a given platform and
    architecture from downloads.limacharlie.io.

    Examples:
        limacharlie download sensor --list
        limacharlie download sensor --platform linux --arch 64
        limacharlie download sensor --platform windows --arch msi64 -o ./sensor.msi
        limacharlie download sensor --platform mac --arch arm64
    """
    if show_list:
        _output(ctx, list_sensor_targets())
        return

    if platform is None:
        click.echo(
            "Error: --platform is required (or use --list to see options).",
            err=True,
        )
        ctx.exit(4)
        return

    # For chrome, arch is not needed
    if platform == "chrome":
        arch = arch or ""
    elif arch is None:
        click.echo(
            "Error: --arch is required (or use --list to see options).",
            err=True,
        )
        ctx.exit(4)
        return

    if (platform, arch) not in SENSOR_TARGETS:
        valid_arches = sorted(a for p, a in SENSOR_TARGETS if p == platform)
        click.echo(
            f"Error: Invalid architecture '{arch}' for platform '{platform}'.\n"
            f"Valid architectures: {', '.join(repr(a) for a in valid_arches)}",
            err=True,
        )
        ctx.exit(4)
        return

    _download_and_save(ctx, "sensor", platform, arch, output_path)


# ---------------------------------------------------------------------------
# download adapter
# ---------------------------------------------------------------------------

@group.command("adapter")
@click.option(
    "--platform", "platform",
    type=click.Choice(sorted({p for p, _ in ADAPTER_TARGETS}), case_sensitive=False),
    default=None,
    help="Target platform.",
)
@click.option(
    "--arch", "arch",
    default=None,
    help="Target architecture (e.g. 64, arm, arm64, ppc64).",
)
@click.option(
    "-o", "--output-path", default=None,
    type=click.Path(),
    help="Path to save the file. Use '-' for stdout. Defaults to a sensible filename.",
)
@click.option(
    "--list", "show_list", is_flag=True, default=False,
    help="List available adapter platforms and architectures.",
)
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_ADAPTER),
    help="Show detailed explanation of this command.",
)
@pass_context
def adapter(ctx, platform, arch, output_path, show_list):
    """Download an adapter (USP) binary.

    Downloads the adapter binary for a given platform and architecture
    from downloads.limacharlie.io.

    Examples:
        limacharlie download adapter --list
        limacharlie download adapter --platform linux --arch 64
        limacharlie download adapter --platform mac --arch arm64 -o ./lc_adapter
    """
    if show_list:
        _output(ctx, list_adapter_targets())
        return

    if platform is None:
        click.echo(
            "Error: --platform is required (or use --list to see options).",
            err=True,
        )
        ctx.exit(4)
        return

    if arch is None:
        click.echo(
            "Error: --arch is required (or use --list to see options).",
            err=True,
        )
        ctx.exit(4)
        return

    if (platform, arch) not in ADAPTER_TARGETS:
        valid_arches = sorted(a for p, a in ADAPTER_TARGETS if p == platform)
        click.echo(
            f"Error: Invalid architecture '{arch}' for platform '{platform}'.\n"
            f"Valid architectures: {', '.join(repr(a) for a in valid_arches)}",
            err=True,
        )
        ctx.exit(4)
        return

    _download_and_save(ctx, "adapter", platform, arch, output_path)


# ---------------------------------------------------------------------------
# download list
# ---------------------------------------------------------------------------

@group.command("list")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_LIST),
    help="Show detailed explanation of this command.",
)
@pass_context
def list_targets(ctx):
    """List all available download targets.

    Shows every supported (platform, architecture) combination for both
    sensors and adapters.

    Example:
        limacharlie download list
    """
    sensors = list_sensor_targets()
    adapters = list_adapter_targets()

    for item in sensors:
        item["type"] = "sensor"
    for item in adapters:
        item["type"] = "adapter"

    _output(ctx, sensors + adapters)
