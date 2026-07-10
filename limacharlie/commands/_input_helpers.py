"""Shared CLI input-loading helpers.

The canonical YAML-or-JSON input loaders for command modules. Several
older modules (hive, ioc, output_cmd, replay_cmd, usp, dr) carry their
own private copies of this idiom; new code should import from here so
parser and error-message fixes land in one place.

Both loaders raise ``click.BadParameter`` with a clean usage message on
unparseable input instead of letting raw tracebacks reach the user.
"""

from __future__ import annotations

import json
import sys
from typing import Any

import click
import yaml


def load_file(path: str, param_hint: str) -> Any:
    """Read + parse a JSON or YAML file, raising a clean usage error."""
    try:
        with open(path, "r") as f:
            content = f.read()
    except OSError as exc:
        raise click.BadParameter(f"cannot read file: {exc}", param_hint=param_hint)
    return parse_yaml_or_json(content, param_hint)


def load_stdin() -> Any:
    """Parse piped stdin as YAML-or-JSON; ``None`` when stdin is a TTY."""
    if sys.stdin.isatty():
        return None
    return parse_yaml_or_json(sys.stdin.read(), "stdin")


def parse_yaml_or_json(content: str, param_hint: str) -> Any:
    """Parse a string as YAML first (a JSON superset), then JSON.

    Raises ``click.BadParameter`` when the content is neither.
    """
    try:
        return yaml.safe_load(content)
    except Exception:
        pass
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise click.BadParameter(
            f"input is neither valid YAML nor JSON: {exc}", param_hint=param_hint,
        )
