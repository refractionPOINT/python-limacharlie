"""Raw API command for LimaCharlie CLI v2.

Provides a generic escape-hatch for making authenticated HTTP requests
to any LimaCharlie API endpoint, similar to ``gh api``.
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any
from urllib.parse import quote

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
    "jwt": "https://jwt.limacharlie.io",
    "stream": "https://stream-tmp.limacharlie.io",
    "downloads": "https://downloads.limacharlie.io",
    "cases": "https://cases.limacharlie.io",
}

# Compat shim: the legacy billing.limacharlie.io host is retired and its
# endpoints have been folded into lc_api under api.limacharlie.io/v1/.
# --target billing continues to accept the old relative paths and rewrites
# them to the new lc_api routes. Paths with no legacy counterpart (e.g.
# /v1/orgs/{oid}/billing/sku, which never existed on the old host) are
# passed through as-is.
_BILLING_PATH_REWRITES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^orgs/([^/]+)/status$"), r"orgs/\1/billing/status"),
    (re.compile(r"^orgs/([^/]+)/details$"), r"orgs/\1/billing/details"),
    (re.compile(r"^orgs/([^/]+)/invoice_url/(\d{4})/(\d{1,2})$"), r"orgs/\1/billing/invoice/\2/\3"),
    (re.compile(r"^user/self/plans$"), "plans"),
]


def _rewrite_billing_endpoint(endpoint: str) -> str:
    """Rewrite a legacy billing-service relative path to its lc_api equivalent."""
    for pattern, replacement in _BILLING_PATH_REWRITES:
        rewritten, n = pattern.subn(replacement, endpoint)
        if n:
            return rewritten
    return endpoint


# ---------------------------------------------------------------------------
# Field parsing helpers
# ---------------------------------------------------------------------------

def _parse_raw_field(spec: str) -> tuple[str, str]:
    """Parse a -f key=value spec into (key, value) string pair."""
    if "=" not in spec:
        raise click.BadParameter(f"Expected key=value, got: {spec}")
    key, value = spec.split("=", 1)
    return (key, value)


def _read_stdin() -> str:
    """Read stdin, guarding against accidental reads from a terminal."""
    if sys.stdin.isatty():
        click.echo(
            "Reading from terminal stdin. Provide input and press "
            "Ctrl-D (EOF) to continue, or Ctrl-C to cancel.",
            err=True,
        )
    return sys.stdin.read()


def _safe_read_file(path: str) -> str:
    """Read a file with basic path-safety checks.

    Resolves symlinks and verifies the target is a regular file.
    """
    resolved = os.path.realpath(path)
    if not os.path.isfile(resolved):
        raise click.BadParameter(f"Not a regular file: {path} (resolved to {resolved})")
    with open(resolved, "r") as f:
        return f.read()


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
            return (key, _read_stdin())
        return (key, _safe_read_file(path))

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

_EXPLAIN_API = """\
Make authenticated HTTP requests to any LimaCharlie API endpoint.

This is an escape-hatch command for accessing endpoints that are not yet
wrapped by dedicated CLI commands, for scripting, or for debugging.

The positional ENDPOINT argument is a relative API path.  Use {oid} as a
placeholder and it will be replaced with the resolved organization ID:

    limacharlie api orgs/{oid}/sensors

Request body fields can be provided via -f (string) or -F (typed) flags.
Multiple flags build a form-encoded body (the default for LimaCharlie APIs).
Use --json to send a JSON body instead.  -F coerces bools, ints, and supports
@file for reading values from files.  Alternatively, use --input to send
a raw body from a file or stdin.

Target aliases: api (default), jwt, stream, downloads, cases.
The deprecated 'billing' alias is still accepted; legacy billing-service
paths (orgs/{oid}/status, user/self/plans, invoice_url/...) are rewritten
to their new /v1/ counterparts on api.limacharlie.io.
Any other value is treated as a raw https:// URL.

Non-200 responses are NOT errors: the raw response body is printed and the
exit code reflects the HTTP status (0 for 2xx, 4 for 4xx, 5 for 5xx).
"""
register_explain("api", _EXPLAIN_API)


@click.command("api")
@click.argument("endpoint")
@click.option("-X", "--method", default=None, help="HTTP method (default: GET, or POST if body provided).")
@click.option("-f", "--raw-field", multiple=True, help="String field as key=value (form-encoded body, or query param for GET).")
@click.option("-F", "--field", multiple=True, help="Typed field as key=value. Coerces bools/ints. @file reads from file.")
@click.option("--json", "use_json", is_flag=True, help="Send fields as JSON body instead of form-encoded.")
@click.option("--input", "input_file", default=None, help="Request body from file (use '-' for stdin).")
@click.option("--content-type", "content_type_override", default=None, help="Content-Type for --input body (default: auto-detect).")
@click.option("--target", default="api", help="API host alias or URL (aliases: api, jwt, stream, downloads, cases; billing is a deprecated alias that rewrites legacy paths to api).")
@click.option("-i", "--include", "include_status", is_flag=True, help="Show HTTP status code in output.")
@click.option("--silent", is_flag=True, help="Suppress response body.")
@click.option("--no-auth", is_flag=True, help="Skip authentication.")
@click.option("-H", "--header", multiple=True, help="Additional header as 'Key: Value'.")
@pass_context
def cmd(ctx: click.Context, endpoint: str, method: str | None, raw_field: tuple[str, ...],
        field: tuple[str, ...], use_json: bool, input_file: str | None,
        content_type_override: str | None, target: str,
        include_status: bool, silent: bool, no_auth: bool, header: tuple[str, ...]) -> None:
    # --- Validate mutual exclusivity ---
    if input_file and (raw_field or field):
        raise click.UsageError("--input cannot be combined with -f/--raw-field or -F/--field.")
    if content_type_override and not input_file:
        raise click.UsageError("--content-type can only be used with --input.")

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
    # The legacy "billing" alias is a compat shim: rewrite the endpoint and
    # route through api.limacharlie.io/v1/ like the default "api" target.
    if target == "billing":
        endpoint = _rewrite_billing_endpoint(endpoint)
        alt_root = None
    elif target == "api":
        alt_root = None
    elif target in _TARGETS:
        alt_root = _TARGETS[target]
    elif target.startswith("https://") or target.startswith("http://"):
        alt_root = target
    else:
        alt_root = f"https://{target}"

    # --- Create client ---
    client = Client(oid=ctx.obj.oid, environment=ctx.obj.environment, print_debug_fn=ctx.obj.debug_fn, debug_full_response=ctx.obj.debug_full, debug_curl=ctx.obj.debug_curl, debug_verbose=ctx.obj.debug_verbose)

    # --- Expand {oid} placeholder ---
    if "{oid}" in endpoint:
        oid = client.oid
        if oid is None:
            raise click.UsageError(
                "Endpoint contains {oid} but no organization ID is configured.\n"
                "Set a default org with 'limacharlie auth use-org <OID>' or pass --oid."
            )
        endpoint = endpoint.replace("{oid}", quote(oid, safe=""))

    # --- Parse extra headers ---
    extra_headers: dict[str, str] = {}
    for h in header:
        k, v = _parse_header(h)
        extra_headers[k] = v

    # --- Build request kwargs ---
    query_params: dict[str, str] | None = None
    raw_body: bytes | None = None
    content_type: str | None = None
    params: dict[str, Any] | None = None

    if input_file is not None:
        # Raw body from file or stdin
        if input_file == "-":
            body_text = _read_stdin()
        else:
            body_text = _safe_read_file(input_file)
        raw_body = body_text.encode("utf-8")
        # Content type: explicit override > auto-detect
        if content_type_override:
            content_type = content_type_override
        else:
            stripped = body_text.lstrip()
            if stripped.startswith("{") or stripped.startswith("["):
                content_type = "application/json"
            else:
                content_type = "application/octet-stream"
    elif fields:
        if effective_method == "GET":
            # Fields go to query params for GET
            query_params = {k: str(v) for k, v in fields.items()}
        elif use_json:
            # --json: send as JSON body (preserves typed values from -F)
            raw_body = json.dumps(fields).encode("utf-8")
            content_type = "application/json"
        else:
            # Default: form-encoded body (LC API convention)
            params = {k: str(v) for k, v in fields.items()}

    # --- Make the request ---
    status, data = client.raw_request(
        effective_method,
        endpoint,
        params=params,
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
