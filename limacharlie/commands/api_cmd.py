"""Raw API command for LimaCharlie CLI v2.

Provides a generic escape-hatch for making authenticated HTTP requests
to any LimaCharlie API endpoint, similar to ``gh api``.
"""

from __future__ import annotations

import json
import sys
from typing import Any

import click

from ..cli import pass_context
from ..client import Client
from ..output import format_output, detect_output_format
from ..discovery import register_explain


# ---------------------------------------------------------------------------
# Target aliases
# ---------------------------------------------------------------------------

_TARGETS = {
    "api": "https://api.limacharlie.io",
    "billing": "https://billing.limacharlie.io",
    "jwt": "https://jwt.limacharlie.io",
    "stream": "https://stream-tmp.limacharlie.io",
    "downloads": "https://downloads.limacharlie.io",
}


# ---------------------------------------------------------------------------
# Explain text
# ---------------------------------------------------------------------------

_EXPLAIN_API = """\
Make authenticated HTTP requests to any LimaCharlie API endpoint.

This is an escape-hatch command for accessing endpoints that are not yet
wrapped by dedicated CLI commands, for scripting, or for debugging.

The positional ENDPOINT argument is a relative API path.  Use {oid} as a
placeholder and it will be replaced with the resolved organization ID:

    limacharlie api orgs/{oid}/sensors

Request body fields can be provided via -f (string) or -F (typed) flags.
Multiple flags build a JSON object.  -F coerces bools, ints, and supports
@file for reading values from files.  Alternatively, use --input to send
a raw body from a file or stdin.

Target aliases: api (default), billing, jwt, stream, downloads.
Any other value is treated as a raw https:// URL.

Non-200 responses are NOT errors: the raw response body is printed and the
exit code reflects the HTTP status (0 for 2xx, 4 for 4xx, 5 for 5xx).
"""

register_explain("api", _EXPLAIN_API)


# ---------------------------------------------------------------------------
# Field parsing helpers
# ---------------------------------------------------------------------------

def _parse_raw_field(spec: str) -> tuple[str, str]:
    """Parse a -f key=value spec into (key, value) string pair."""
    if "=" not in spec:
        raise click.BadParameter(f"Expected key=value, got: {spec}")
    key, value = spec.split("=", 1)
    return (key, value)


def _parse_typed_field(spec: str) -> tuple[str, Any]:
    """Parse a -F key=value spec with type coercion.

    Coercion rules:
      true/false -> bool
      numeric strings -> int or float
      @path -> file contents (string)
      @- -> stdin contents (string)
      everything else -> string
    """
    if "=" not in spec:
        raise click.BadParameter(f"Expected key=value, got: {spec}")
    key, raw = spec.split("=", 1)

    # Boolean coercion
    if raw.lower() == "true":
        return (key, True)
    if raw.lower() == "false":
        return (key, False)

    # File reference
    if raw.startswith("@"):
        path = raw[1:]
        if path == "-":
            return (key, sys.stdin.read())
        with open(path, "r") as f:
            return (key, f.read())

    # Numeric coercion
    try:
        return (key, int(raw))
    except ValueError:
        pass
    try:
        return (key, float(raw))
    except ValueError:
        pass

    return (key, raw)


def _parse_header(spec: str) -> tuple[str, str]:
    """Parse a -H 'Key: Value' spec into (key, value)."""
    if ":" not in spec:
        raise click.BadParameter(f"Expected 'Key: Value', got: {spec}")
    key, value = spec.split(":", 1)
    return (key.strip(), value.strip())


def _exit_code_for_status(status: int) -> int:
    """Map HTTP status to CLI exit code."""
    if 200 <= status < 300:
        return 0
    if 400 <= status < 500:
        return 4
    if 500 <= status < 600:
        return 5
    return 1


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------

@click.command("api")
@click.argument("endpoint")
@click.option("-X", "--method", default=None, help="HTTP method (default: GET, or POST if body provided).")
@click.option("-f", "--raw-field", multiple=True, help="String field as key=value (JSON body, or query param for GET).")
@click.option("-F", "--field", multiple=True, help="Typed field as key=value. Coerces bools/ints. @file reads from file.")
@click.option("--input", "input_file", default=None, help="Request body from file (use '-' for stdin).")
@click.option("--target", default="api", help="API host alias or URL (aliases: api, billing, jwt, stream, downloads).")
@click.option("-i", "--include", "include_status", is_flag=True, help="Show HTTP status code in output.")
@click.option("--silent", is_flag=True, help="Suppress response body.")
@click.option("--no-auth", is_flag=True, help="Skip authentication.")
@click.option("-H", "--header", multiple=True, help="Additional header as 'Key: Value'.")
@pass_context
def cmd(ctx: click.Context, endpoint: str, method: str | None, raw_field: tuple[str, ...],
        field: tuple[str, ...], input_file: str | None, target: str,
        include_status: bool, silent: bool, no_auth: bool, header: tuple[str, ...]) -> None:
    """Make an authenticated API request to any LimaCharlie endpoint.

    ENDPOINT is a relative API path.  Use {oid} as a placeholder for the
    organization ID.

    \b
    Examples:
        limacharlie api orgs/{oid}/sensors
        limacharlie api orgs/{oid}/sensors -X POST -F hostname=test
        limacharlie api --target billing orgs/{oid}/status
        limacharlie api orgs/{oid}/sensors --no-auth
    """
    # --- Validate mutual exclusivity ---
    if input_file and (raw_field or field):
        raise click.UsageError("--input cannot be combined with -f/--raw-field or -F/--field.")

    # --- Build fields dict from -f and -F ---
    fields: dict[str, Any] = {}
    for spec in raw_field:
        k, v = _parse_raw_field(spec)
        fields[k] = v
    for spec in field:
        k, v = _parse_typed_field(spec)
        fields[k] = v

    has_body = bool(fields) or input_file is not None

    # --- Determine HTTP method ---
    if method is None:
        effective_method = "POST" if has_body else "GET"
    else:
        effective_method = method.upper()

    # --- Resolve target ---
    if target in _TARGETS:
        target_url = _TARGETS[target]
    elif target.startswith("https://") or target.startswith("http://"):
        target_url = target
    else:
        target_url = f"https://{target}"

    # For the default "api" target, use alt_root=None so _rest_call
    # builds ROOT_URL/v1/<endpoint>.  For everything else, use alt_root.
    alt_root = None if target == "api" else target_url

    # --- Create client ---
    client = Client(oid=ctx.obj.oid, environment=ctx.obj.environment)

    # --- Expand {oid} placeholder ---
    if "{oid}" in endpoint:
        oid = client.oid
        if oid is None:
            raise click.UsageError(
                "Endpoint contains {oid} but no organization ID is configured.\n"
                "Set a default org with 'limacharlie auth use-org <OID>' or pass --oid."
            )
        endpoint = endpoint.replace("{oid}", oid)

    # --- Parse extra headers ---
    extra_headers: dict[str, str] = {}
    for h in header:
        k, v = _parse_header(h)
        extra_headers[k] = v

    # --- Build request kwargs ---
    query_params: dict[str, str] | None = None
    raw_body: bytes | None = None
    content_type: str | None = None

    if input_file is not None:
        # Raw body from file or stdin
        if input_file == "-":
            body_text = sys.stdin.read()
        else:
            with open(input_file, "r") as f:
                body_text = f.read()
        raw_body = body_text.encode("utf-8")
        # Auto-detect content type
        stripped = body_text.lstrip()
        if stripped.startswith("{") or stripped.startswith("["):
            content_type = "application/json"
        else:
            content_type = "application/octet-stream"
    elif fields:
        if effective_method == "GET":
            # Fields go to query params for GET
            query_params = {k: str(v) for k, v in fields.items()}
        else:
            # Fields go to JSON body
            raw_body = json.dumps(fields).encode("utf-8")
            content_type = "application/json"

    # --- Make the request ---
    status, data = client.raw_request(
        effective_method,
        endpoint,
        alt_root=alt_root,
        query_params=query_params,
        raw_body=raw_body,
        content_type=content_type,
        is_no_auth=no_auth,
        extra_headers=extra_headers or None,
    )

    # --- Output ---
    if include_status:
        click.echo(f"HTTP {status}")

    if not silent and data is not None:
        fmt = ctx.obj.output_format or detect_output_format()
        if not ctx.obj.quiet:
            click.echo(format_output(data, fmt))

    ctx.exit(_exit_code_for_status(status))
