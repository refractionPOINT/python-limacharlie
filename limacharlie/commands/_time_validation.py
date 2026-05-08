"""Shared validation for epoch timestamp CLI parameters."""

from __future__ import annotations

import click

# Unix seconds won't reach 10^12 until year ~33658.
# Millisecond timestamps are currently ~1.7×10^12, so any value
# above 10^12 is unambiguously milliseconds.
_MAX_EPOCH_SECONDS = 1_000_000_000_000


def validate_epoch_seconds(value: int | None, param_name: str) -> None:
    """Raise ``click.BadParameter`` if *value* looks like milliseconds."""
    if value is not None and value > _MAX_EPOCH_SECONDS:
        raise click.BadParameter(
            f"Value {value} looks like milliseconds. "
            f"This parameter expects Unix seconds (10 digits, e.g. {value // 1000}).",
            param_hint=f"'--{param_name}'",
        )
