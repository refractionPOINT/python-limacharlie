"""Shared CLI output helpers for LimaCharlie command modules."""

from __future__ import annotations

from typing import Any

import click

from ..output import detect_output_format, format_output


def command_output(ctx: click.Context, data: Any) -> None:
    """Format and echo data according to the CLI's output settings.

    Respects the --quiet flag and the configured output format
    (json, yaml, table, etc.). Used by all command modules to
    produce consistent output.

    Args:
        ctx: Click context carrying obj.output_format and obj.quiet.
        data: The data structure to format and display.
    """
    fmt = ctx.obj.output_format or detect_output_format()
    if not ctx.obj.quiet:
        click.echo(format_output(data, fmt))
