"""Tag commands for LimaCharlie CLI v2.

Commands for listing, adding, removing, and searching by sensor tags.
Tags are lightweight labels attached to sensors for grouping, filtering,
and targeting D&R rules or tasks.
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


def _get_org(ctx: click.Context) -> Organization:
    client = Client(oid=ctx.obj.oid, environment=ctx.obj.environment, print_debug_fn=ctx.obj.debug_fn, debug_full_response=ctx.obj.debug_full, debug_curl=ctx.obj.debug_curl, debug_verbose=ctx.obj.debug_verbose)
    return Organization(client)


def _get_sensor(ctx: click.Context, sid: str) -> Sensor:
    org = _get_org(ctx)
    return Sensor(org, sid)


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------

@click.group("tag")
def group() -> None:
    """Manage sensor tags.

    Tags are lightweight labels attached to sensors.  They enable
    grouping, filtering, and targeting of D&R rules and tasks across
    the fleet.
    """


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

_EXPLAIN_LIST = """\
List tags.  When --sid is provided, lists the tags applied to that
specific sensor.  Without --sid, lists all unique tags in use across the
entire organization.

Tags are case-sensitive strings.  They are commonly used to group
sensors by role (e.g. 'web-server', 'database'), environment
(e.g. 'production', 'staging'), or business unit.

Tags in D&R and sensor selectors:
  - In D&R rule target: '`production` in tags'
  - In sensor list:     limacharlie sensor list --tag production
  - In mass operations: limacharlie tag mass-add --selector 'plat == `windows`' --tag win-fleet

Tags can be applied:
  - At enrollment via installation key --tags
  - Manually via 'limacharlie tag add --sid <SID> --tag <tag>'
  - Temporarily with --ttl (auto-removed after N seconds)
  - In bulk via 'limacharlie tag mass-add'
  - By D&R response actions (action: tag)
"""
register_explain("tag.list", _EXPLAIN_LIST)


@group.command("list")
@click.option("--sid", default=None, help="Sensor ID (UUID).  If omitted, lists all org tags.")
@pass_context
def list_tags(ctx: click.Context, sid: str | None) -> None:
    if sid:
        sensor = _get_sensor(ctx, sid)
        tags = sensor.get_tags()
    else:
        org = _get_org(ctx)
        tags = org.get_all_tags()

    _output(ctx, tags)


# ---------------------------------------------------------------------------
# add
# ---------------------------------------------------------------------------

_EXPLAIN_ADD = """\
Add a tag to a sensor.  Tags take effect immediately and are visible
to D&R rules, sensor selectors, and the web console.  Optionally
set a TTL (time-to-live) in seconds so the tag is automatically
removed after the specified duration.

Temporary tags with TTL are useful for time-limited operations such
as enabling extra logging on a sensor during an investigation.
"""
register_explain("tag.add", _EXPLAIN_ADD)


@group.command()
@click.option("--sid", required=True, help="Sensor ID (UUID).")
@click.option("--tag", required=True, help="Tag string to add.")
@click.option("--ttl", default=None, type=int, help="Time-to-live in seconds (tag auto-removed after).")
@pass_context
def add(ctx: click.Context, sid: str, tag: str, ttl: int | None) -> None:
    sensor = _get_sensor(ctx, sid)
    data = sensor.add_tag(tag, ttl=ttl)
    if not ctx.obj.quiet:
        msg = f"Tag '{tag}' added to sensor {sid}."
        if ttl:
            msg += f" (TTL: {ttl}s)"
        click.echo(msg)


# ---------------------------------------------------------------------------
# remove
# ---------------------------------------------------------------------------

_EXPLAIN_REMOVE = """\
Remove a tag from a sensor.  The tag is removed immediately.  If the
sensor does not have the specified tag, the operation succeeds silently.
"""
register_explain("tag.remove", _EXPLAIN_REMOVE)


@group.command()
@click.option("--sid", required=True, help="Sensor ID (UUID).")
@click.option("--tag", required=True, help="Tag string to remove.")
@pass_context
def remove(ctx: click.Context, sid: str, tag: str) -> None:
    sensor = _get_sensor(ctx, sid)
    sensor.remove_tag(tag)
    if not ctx.obj.quiet:
        click.echo(f"Tag '{tag}' removed from sensor {sid}.")


# ---------------------------------------------------------------------------
# find
# ---------------------------------------------------------------------------

_EXPLAIN_FIND = """\
Find all sensors that have a specific tag.  Returns the SID and basic
info for each matching sensor.  This is a fast index lookup (not a
full fleet scan) and is the recommended way to locate sensors by tag.

Related: 'limacharlie sensor list --tag <tag>' performs a similar
lookup but returns full sensor details.
"""
register_explain("tag.find", _EXPLAIN_FIND)


@group.command()
@click.option("--tag", required=True, help="Tag to search for.")
@pass_context
def find(ctx: click.Context, tag: str) -> None:
    org = _get_org(ctx)
    data = org.find_sensors_by_tag(tag)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# mass-add
# ---------------------------------------------------------------------------

_EXPLAIN_MASS_ADD = """\
Add a tag to all sensors matching a sensor selector expression (bexpr).
This iterates over every sensor that matches the selector and applies
the tag to each one.  Optionally set a TTL so the tag is automatically
removed after the specified duration.

This is useful for bulk operations such as tagging all Windows sensors
as 'windows-fleet', or temporarily tagging a subset of sensors for
an investigation.

The --selector flag uses the same bexpr syntax as 'limacharlie sensor
list --selector'.  Examples: 'plat == `windows`', '`production` in tags'.
"""
register_explain("tag.mass-add", _EXPLAIN_MASS_ADD)


@group.command("mass-add")
@click.option("--selector", required=True, help="Sensor selector expression (bexpr) to match sensors.")
@click.option("--tag", required=True, help="Tag string to add to all matching sensors.")
@click.option("--ttl", default=None, type=int, help="Time-to-live in seconds (tag auto-removed after).")
@pass_context
def mass_add(ctx: click.Context, selector: str, tag: str, ttl: int | None) -> None:
    org = _get_org(ctx)
    data = org.mass_tag(selector, tag, ttl=ttl)
    if not ctx.obj.quiet:
        msg = f"Tag '{tag}' added to {data['tagged']} sensor(s) matching '{selector}'."
        if ttl:
            msg += f" (TTL: {ttl}s)"
        click.echo(msg)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# mass-remove
# ---------------------------------------------------------------------------

_EXPLAIN_MASS_REMOVE = """\
Remove a tag from all sensors matching a sensor selector expression (bexpr).
This iterates over every sensor that matches the selector and removes
the tag from each one.

This is the inverse of 'limacharlie tag mass-add' and is useful for
cleaning up temporary tags applied during investigations or operations.
"""
register_explain("tag.mass-remove", _EXPLAIN_MASS_REMOVE)


@group.command("mass-remove")
@click.option("--selector", required=True, help="Sensor selector expression (bexpr) to match sensors.")
@click.option("--tag", required=True, help="Tag string to remove from all matching sensors.")
@pass_context
def mass_remove(ctx: click.Context, selector: str, tag: str) -> None:
    org = _get_org(ctx)
    data = org.mass_untag(selector, tag)
    if not ctx.obj.quiet:
        click.echo(f"Tag '{tag}' removed from {data['untagged']} sensor(s) matching '{selector}'.")
    _output(ctx, data)
