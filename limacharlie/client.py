"""HTTP client for LimaCharlie API v2.

Handles JWT generation/refresh, retry with exponential backoff,
rate limit awareness, and request debugging.

When ``print_debug_fn`` is supplied, every HTTP request/response is
logged to stderr in a format similar to Apache libcloud's debug output:
method, URL, request headers (Authorization value masked), request body,
response status, response headers, and response body (truncated to
DEBUG_RESPONSE_BODY_LIMIT chars unless ``debug_full_response=True``).
"""

from __future__ import annotations

import base64
import json
import ssl
import sys
import time
import uuid
import zlib
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.parse import quote as urlescape
from urllib.parse import urlencode
from urllib.request import Request as URLRequest
from urllib.request import urlopen

from .config import resolve_credentials
from .errors import (
    ApiError,
    AuthenticationError,
    LimaCharlieError,
    RateLimitError,
    error_from_status_code,
)
from .user_agent_utils import build_user_agent

try:
    from ._version import version as __version__
except ImportError:
    __version__ = "0.0.0.dev0"

ROOT_URL = "https://api.limacharlie.io"
API_VERSION = "v1"
JWT_URL = "https://jwt.limacharlie.io"

HTTP_OK = 200
HTTP_UNAUTHORIZED = 401
HTTP_TOO_MANY_REQUESTS = 429
HTTP_GATEWAY_TIMEOUT = 504

# Default limit for response body in debug output. Bodies longer than
# this are truncated with a "[truncated]" marker. Use debug_full_response=True
# on the Client (or --debug-full on the CLI) to disable truncation.
DEBUG_RESPONSE_BODY_LIMIT = 2048

# Headers whose values are masked in debug output to avoid leaking secrets.
_SENSITIVE_HEADERS = frozenset({"authorization", "x-api-key", "cookie", "set-cookie"})


def _create_ssl_context() -> ssl.SSLContext | None:
    """Create an SSL context with OpenSSL 3.0+ compatibility."""
    try:
        ctx = ssl.create_default_context()
        if hasattr(ssl, "OP_IGNORE_UNEXPECTED_EOF"):
            ctx.options |= ssl.OP_IGNORE_UNEXPECTED_EOF
        return ctx
    except Exception:
        try:
            return ssl.create_default_context()
        except Exception:
            return None


def _build_user_agent() -> str:
    return build_user_agent("lc-cli", __version__)


class Client:
    """HTTP client for LimaCharlie API.

    Handles authentication (JWT generation/refresh), retry logic with
    exponential backoff, and rate limit awareness.

    Usage:
        client = Client(oid="...", api_key="...")
        data = client.request("GET", "sensors")

    Or as context manager:
        with Client(oid="...", api_key="...") as client:
            data = client.request("GET", "sensors")

    Credential resolution order:
        explicit params > env vars > config file
    """

    def __init__(
        self,
        oid: str | None = None,
        api_key: str | None = None,
        uid: str | None = None,
        environment: str | None = None,
        jwt: str | None = None,
        is_retry_quota_errors: bool = False,
        print_debug_fn: Callable[[str], None] | None = None,
        on_refresh_auth: Callable[[Client], None] | None = None,
        inv_id: str | None = None,
        timeout: int = 600,
        debug_full_response: bool = False,
        debug_curl: bool = False,
        debug_verbose: bool = True,
    ) -> None:
        """Initialize the client.

        Args:
            oid: Organization ID (UUID string).
            api_key: API key (UUID string).
            uid: User ID for user-scoped API keys.
            environment: Named environment from config file.
            jwt: Pre-generated JWT (skips generation).
            is_retry_quota_errors: Auto-retry on 429 rate limit errors.
            print_debug_fn: Callback for debug messages. When set, every
                HTTP request/response is logged with headers and body.
            on_refresh_auth: Callback invoked when JWT is refreshed.
            inv_id: Investigation ID for tracking.
            timeout: Default request timeout in seconds.
            debug_full_response: When True, do not truncate response bodies
                in debug output. Default False (truncate to
                DEBUG_RESPONSE_BODY_LIMIT chars).
            debug_curl: When True, print a reproducible curl command for
                each request to stderr. Sensitive header values are masked
                with a $LC_TOKEN placeholder.
            debug_verbose: When True (default), print verbose request/response
                details. Set to False when only curl output is desired
                (--debug-curl without --debug).
        """
        creds = resolve_credentials(
            oid=oid,
            api_key=api_key,
            uid=uid,
            environment=environment,
        )

        self._oid = creds["oid"]
        self._uid = creds["uid"]
        self._api_key = creds["api_key"]
        self._oauth_creds = creds["oauth"]
        self._environment = environment
        self._debug_fn = print_debug_fn
        self._jwt = jwt
        if self._jwt is None:
            from .jwt_cache import get_cached_jwt, _get_cache_path, _decode_jwt_exp

            # Mirror the auth path selection in refresh_jwt: if oauth_creds
            # is set, OAuth path is used regardless of api_key. Pass
            # credentials accordingly so the cache key matches what
            # _refresh_jwt_oauth / refresh_jwt will write.
            if self._oauth_creds is not None:
                cache_api_key = None
                cache_oauth = self._oauth_creds
            else:
                cache_api_key = self._api_key
                cache_oauth = None
            self._debug(f"JWT cache: checking {_get_cache_path()}")
            self._jwt = get_cached_jwt(
                self._oid, cache_api_key, cache_oauth, self._uid,
            )
            if self._jwt is not None:
                exp = _decode_jwt_exp(self._jwt)
                remaining = int(exp - time.time()) if exp else 0
                self._debug(
                    f"JWT cache: hit, reusing cached token "
                    f"(expires in {remaining}s, {remaining // 60}m)"
                )
            else:
                self._debug("JWT cache: miss, will fetch fresh token on first request")
        else:
            self._debug("JWT: using pre-generated token, skipping cache")
        self._is_retry_quota_errors = is_retry_quota_errors
        self._debug_full_response = debug_full_response
        self._debug_curl = debug_curl
        self._debug_curl_only = debug_curl and not debug_verbose
        self._on_refresh_auth = on_refresh_auth
        self._inv_id = inv_id
        self._timeout = timeout
        self._ssl_context = _create_ssl_context()
        self._user_agent = _build_user_agent()

    @property
    def oid(self) -> str | None:
        """The organization ID this client is authenticated to."""
        return self._oid

    @property
    def uid(self) -> str | None:
        """The user ID for user-scoped API keys, or None."""
        return self._uid

    def __enter__(self) -> Client:
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: Any) -> bool:
        return False

    def _debug(self, msg: str) -> None:
        if self._debug_fn is not None:
            from datetime import datetime, timezone

            ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
            self._debug_fn(f"{ts}: {msg}")

    @staticmethod
    def _mask_headers(headers: dict[str, str] | list[tuple[str, str]]) -> list[tuple[str, str]]:
        """Return headers with sensitive values masked for debug output."""
        items = headers.items() if isinstance(headers, dict) else headers
        masked = []
        for name, value in items:
            if name.lower() in _SENSITIVE_HEADERS:
                # Show first 12 chars so you can identify which token it is.
                visible = value[:12] if len(value) > 12 else value
                masked.append((name, f"{visible}...REDACTED"))
            else:
                masked.append((name, value))
        return masked

    def _debug_request(self, verb: str, url: str, headers: dict[str, str], body: bytes | None) -> None:
        """Log full request details in libcloud-style debug format."""
        if self._debug_fn is None or self._debug_curl_only:
            return
        lines = [f"--- request {verb} {url} ---"]
        for name, value in self._mask_headers(headers):
            lines.append(f"  {name}: {value}")
        if body and verb in ("POST", "PUT", "PATCH"):
            try:
                body_str = body.decode("utf-8", errors="replace")
            except Exception:
                body_str = f"<binary {len(body)} bytes>"
            # Truncate request body too if very large.
            if not self._debug_full_response and len(body_str) > DEBUG_RESPONSE_BODY_LIMIT:
                body_str = body_str[:DEBUG_RESPONSE_BODY_LIMIT] + f"... [truncated, {len(body)} bytes total]"
            lines.append(f"  body: {body_str}")
        self._debug("\n".join(lines))

    def _debug_response(self, status: int, resp_headers: list[tuple[str, str]], body_str: str) -> None:
        """Log full response details in libcloud-style debug format."""
        if self._debug_fn is None or self._debug_curl_only:
            return

        lines = [f"--- response {status} ---"]
        for name, value in self._mask_headers(resp_headers):
            lines.append(f"  {name}: {value}")
        if body_str:
            if not self._debug_full_response and len(body_str) > DEBUG_RESPONSE_BODY_LIMIT:
                lines.append(f"  body: {body_str[:DEBUG_RESPONSE_BODY_LIMIT]}... [truncated, {len(body_str)} chars total, use --debug-full to see all]")
            else:
                lines.append(f"  body: {body_str}")
        self._debug("\n".join(lines))

    def _debug_curl_cmd(self, verb: str, url: str, headers: dict[str, str], body: bytes | None) -> None:
        """Print a reproducible curl command for the request.

        Outputs an actual runnable curl command with real header values
        (including auth tokens) so the user can copy-paste and reproduce
        the exact request. Uses shlex.quote() from the Python standard
        library for shell-safe argument escaping.

        Since this includes real tokens, the output is intended for local
        debugging - not for sharing in tickets.

        Inspired by Apache libcloud's LoggingConnection._log_curl()
        (Apache 2.0 license).
        """
        import shlex

        if self._debug_fn is None or not self._debug_curl:
            return

        parts = ["curl -i --compressed"]

        if verb == "HEAD":
            parts.append("--head")
        elif verb != "GET":
            parts.append(f"-X {verb}")

        for name, value in headers.items():
            parts.append(f"-H {shlex.quote(f'{name}: {value}')}")

        if body and verb in ("POST", "PUT", "PATCH"):
            try:
                body_str = body.decode("utf-8", errors="replace")
                parts.append(f"--data-binary {shlex.quote(body_str)}")
            except Exception:
                parts.append(f"--data-binary '<binary {len(body)} bytes>'")

        parts.append(shlex.quote(url))
        self._debug(" \\\n  ".join(parts))

    @staticmethod
    def unwrap(data: str, is_raw: bool = False) -> Any:
        """Decompress gzip+base64 encoded data from the API.

        Used when is_compressed=true is set on requests. The API returns
        data as base64-encoded gzip-compressed JSON.

        Args:
            data: Base64-encoded gzip-compressed string.
            is_raw: If True, return raw bytes instead of parsed JSON.

        Returns:
            Parsed JSON object or raw bytes.
        """
        if is_raw:
            return zlib.decompress(base64.b64decode(data), 16 + zlib.MAX_WBITS)
        else:
            return json.loads(zlib.decompress(base64.b64decode(data), 16 + zlib.MAX_WBITS).decode())

    def get_jwt(self, expiry_hours: float | None = None) -> str:
        """Generate a JWT token with optional custom expiry.

        Useful for long-running operations like search queries that may
        run for several hours. By default, JWTs expire after ~1 hour.
        For operations that take longer, specify a custom expiry in hours.

        If the currently cached JWT already has enough remaining TTL to
        cover the requested expiry_hours, it is reused instead of
        generating a new one. This avoids unnecessary JWT requests when
        running multiple search commands in sequence.

        Args:
            expiry_hours: Token validity duration in hours. If None, uses
                the default expiry (~1 hour). For long-running search
                queries, use 4-8 hours depending on expected duration.

        Returns:
            The JWT token string.

        Raises:
            AuthenticationError: If token generation fails.
            ValidationError: If expiry_hours is not positive.
        """
        import time as time_module
        from .errors import ValidationError

        expiry_ts: int | None = None
        if expiry_hours is not None:
            if expiry_hours <= 0:
                raise ValidationError(
                    f"Token expiry must be positive, got {expiry_hours} hours.",
                    suggestion="Use a positive number of hours (e.g. --token-expiry 8).",
                )
            expiry_ts = int(time_module.time()) + int(expiry_hours * 3600)

        # If we already have a JWT (from cache or prior call), check if it
        # has enough remaining TTL for the requested expiry. If so, reuse it.
        if self._jwt is not None and expiry_hours is not None:
            from .jwt_cache import _decode_jwt_exp

            current_exp = _decode_jwt_exp(self._jwt)
            if current_exp is not None:
                remaining_hours = (current_exp - time_module.time()) / 3600
                if remaining_hours >= expiry_hours:
                    self._debug(
                        f"JWT: reusing current token "
                        f"({remaining_hours:.1f}h remaining >= {expiry_hours}h requested)"
                    )
                    return self._jwt
                self._debug(
                    f"JWT: current token has {remaining_hours:.1f}h remaining, "
                    f"need {expiry_hours}h, fetching new one"
                )

        self.refresh_jwt(expiry=expiry_ts)

        if self._jwt is None:
            from .errors import AuthenticationError
            raise AuthenticationError("Failed to generate JWT token.")

        # Cache the long-lived JWT so subsequent CLI invocations reuse it.
        # Mirror auth path selection: OAuth takes priority over api_key.
        if expiry_ts is not None:
            from .jwt_cache import put_cached_jwt

            self._debug(
                f"JWT cache: writing long-lived token to disk "
                f"(requested {expiry_hours}h expiry)"
            )
            if self._oauth_creds is not None:
                put_cached_jwt(
                    self._jwt, self._oid, None, self._oauth_creds, self._uid
                )
            else:
                put_cached_jwt(
                    self._jwt, self._oid, self._api_key, None, self._uid
                )

        return self._jwt

    def refresh_jwt(self, expiry: int | None = None, oid_override: str | None = None) -> None:
        """Generate or refresh a JWT token.

        Args:
            expiry: Optional expiry time for the JWT.
            oid_override: Optional OID override. Pass '-' for minimal JWT
                         (UID only, no org permissions).
        """
        effective_oid = oid_override if oid_override is not None else self._oid

        # Early check: if no OID is available and this isn't a user-scoped
        # operation (oid_override="-"), provide a clear error message instead
        # of letting the JWT endpoint return a confusing "unknown api key".
        if effective_oid is None:
            raise AuthenticationError(
                "No organization ID (OID) configured.",
                suggestion=(
                    "Set a default org with 'limacharlie auth use-org <OID>',\n"
                    "pass '--oid <OID>' as a global flag (e.g. 'limacharlie --oid <OID> <command>'),\n"
                    "or set the LC_OID environment variable.\n"
                    "To find your OID, run 'limacharlie auth list-orgs'."
                ),
            )

        # Check if we're using OAuth
        if self._oauth_creds is not None:
            self._refresh_jwt_oauth(effective_oid, expiry, oid_override)
            return

        # Traditional API key flow
        if self._api_key is None:
            raise AuthenticationError("No API key or OAuth credentials set.")

        auth_data = {"secret": self._api_key}
        if self._uid is not None:
            auth_data["uid"] = self._uid
        if effective_oid is not None:
            auth_data["oid"] = effective_oid
        if expiry is not None:
            auth_data["expiry"] = int(expiry)

        self._debug(
            f"JWT request: oid={effective_oid}, uid={'set' if self._uid else 'not set'}, "
            f"key={self._api_key[:8]}..."
        )

        self._jwt = self._call_jwt_endpoint(auth_data)
        self._debug("JWT: fetched fresh token from jwt.limacharlie.io")

        if expiry is None and oid_override is None:
            from .jwt_cache import put_cached_jwt, _decode_jwt_exp

            exp = _decode_jwt_exp(self._jwt)
            remaining = int(exp - time.time()) if exp else 0
            self._debug(
                f"JWT cache: writing token to disk "
                f"(expires in {remaining}s, {remaining // 60}m)"
            )
            put_cached_jwt(
                self._jwt, effective_oid, self._api_key, self._oauth_creds, self._uid
            )
        else:
            self._debug(
                f"JWT cache: skipping cache write "
                f"(expiry={'set' if expiry else 'None'}, "
                f"oid_override={'set' if oid_override else 'None'})"
            )

        if self._on_refresh_auth is not None:
            self._on_refresh_auth(self)

    def _refresh_jwt_oauth(self, effective_oid: str | None, expiry: int | None, oid_override: str | None = None) -> None:
        """Refresh JWT using OAuth credentials."""
        from .oauth_simple import SimpleOAuthManager

        oauth_manager = SimpleOAuthManager()
        updated_creds = oauth_manager.ensure_valid_token(dict(self._oauth_creds))
        if updated_creds is None:
            raise AuthenticationError("Failed to refresh OAuth token.")

        if updated_creds != self._oauth_creds:
            self._oauth_creds = updated_creds
            # Persist updated OAuth tokens to config file.
            try:
                from .config import write_credentials, is_ephemeral
                if not is_ephemeral():
                    write_credentials(
                        self._environment or "default",
                        oid=None,
                        api_key=None,
                        oauth_creds=updated_creds,
                    )
            except Exception:
                pass  # Best-effort persistence

        auth_data = {"fb_auth": self._oauth_creds["id_token"]}
        if effective_oid is not None:
            auth_data["oid"] = effective_oid
        if expiry is not None:
            auth_data["expiry"] = int(expiry)

        self._jwt = self._call_jwt_endpoint(auth_data)
        self._debug("JWT: fetched fresh OAuth token from jwt.limacharlie.io")

        if expiry is None and oid_override is None:
            from .jwt_cache import put_cached_jwt, _decode_jwt_exp

            exp = _decode_jwt_exp(self._jwt)
            remaining = int(exp - time.time()) if exp else 0
            self._debug(
                f"JWT cache: writing OAuth token to disk "
                f"(expires in {remaining}s, {remaining // 60}m)"
            )
            put_cached_jwt(
                self._jwt, effective_oid, None, self._oauth_creds, self._uid
            )
        else:
            self._debug(
                f"JWT cache: skipping cache write "
                f"(expiry={'set' if expiry else 'None'}, "
                f"oid_override={'set' if oid_override else 'None'})"
            )

        if self._on_refresh_auth is not None:
            self._on_refresh_auth(self)

    def _call_jwt_endpoint(self, auth_data: dict[str, Any]) -> str:
        """Call the JWT endpoint and return the JWT string."""
        try:
            request = URLRequest(
                JWT_URL,
                urlencode(auth_data).encode(),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            request.get_method = lambda: "POST"

            if self._ssl_context is not None:
                u = urlopen(request, context=self._ssl_context)
            else:
                u = urlopen(request)

            try:
                data = json.loads(u.read().decode())
                return data["jwt"]
            finally:
                u.close()
        except HTTPError as e:
            code = e.code
            error_body = e.read().decode() if hasattr(e, "read") else str(e)
            raise AuthenticationError(
                f"Failed to get JWT: {error_body}",
                code=code,
            )
        except Exception as e:
            raise AuthenticationError(f"Failed to get JWT: {e}")

    def _rest_call(self, url: str, verb: str, params: dict[str, Any] | None = None, alt_root: str | None = None, query_params: dict[str, Any] | list[tuple[str, str]] | None = None,
                   raw_body: bytes | None = None, content_type: str | None = None, is_no_auth: bool = False, timeout: int | None = None,
                   extra_headers: dict[str, str] | None = None) -> tuple[int, Any]:
        """Make a single HTTP request to the API.

        Returns:
            tuple: (status_code, response_data)
        """
        params = params or {}
        headers = {}
        if extra_headers:
            headers.update(extra_headers)

        if not is_no_auth and self._jwt:
            headers["Authorization"] = f"Bearer {self._jwt}"

        # Build URL
        if alt_root is None:
            full_url = f"{ROOT_URL}/{API_VERSION}/{url}"
        else:
            full_url = f"{alt_root}/{url}" if url else alt_root

        if query_params:
            # doseq so sequence values expand to repeated keys
            # (?severity=HIGH&severity=LOW) instead of a Python list repr.
            full_url = f"{full_url}?{urlencode(query_params, doseq=True)}"

        # Build request body
        if raw_body is not None:
            body = raw_body
        else:
            body = urlencode(params, doseq=True).encode()

        request = URLRequest(full_url, body, headers=headers)
        request.get_method = lambda: verb
        request.add_header("User-Agent", self._user_agent)
        if content_type is not None:
            request.add_header("Content-Type", content_type)

        effective_timeout = timeout or self._timeout

        # Log request details (headers include User-Agent added above).
        all_headers = dict(request.headers)
        all_headers.update(request.unredirected_hdrs)
        self._debug_request(verb, full_url, all_headers, body)
        self._debug_curl_cmd(verb, full_url, all_headers, body)

        try:
            if self._ssl_context is not None and full_url.startswith("https"):
                u = urlopen(request, timeout=effective_timeout, context=self._ssl_context)
            else:
                u = urlopen(request, timeout=effective_timeout)

            data = None
            data_str = ""
            try:
                data = u.read()
                data_str = data.decode() if data else ""
                resp = json.loads(data_str) if data_str else {}
            except ValueError:
                resp = {}
            finally:
                # Check rate limit headers
                resp_headers = u.getheaders() if hasattr(u, "getheaders") else []
                quota_limit = None
                quota_period = None
                for h_name, h_val in resp_headers:
                    if h_name == "X-RateLimit-Quota":
                        quota_limit = int(h_val)
                    elif h_name == "X-RateLimit-Period":
                        quota_period = int(h_val)
                if quota_limit is not None or quota_period is not None:
                    self._debug(
                        f"Rate limit warning: quota={quota_limit}, period={quota_period}s"
                    )
                self._debug_response(HTTP_OK, resp_headers, data_str)
                u.close()

            return (HTTP_OK, resp)

        except HTTPError as e:
            error_body = e.read()
            error_str = error_body.decode() if error_body else ""
            try:
                resp = json.loads(error_str)
            except Exception:
                resp = error_str
            resp_headers = e.headers.items() if hasattr(e, "headers") else []
            self._debug_response(e.code, list(resp_headers), error_str)
            return (e.code, resp)

        except ssl.SSLError as e:
            self._debug(f"SSL error: {e}")
            return (HTTP_GATEWAY_TIMEOUT, {"error": f"SSL error: {e}"})

    def request(self, verb: str, url: str, params: dict[str, Any] | None = None, alt_root: str | None = None, query_params: dict[str, Any] | list[tuple[str, str]] | None = None,
                raw_body: bytes | None = None, content_type: str | None = None, is_no_auth: bool = False,
                max_retries: int = 3, timeout: int | None = None, extra_headers: dict[str, str] | None = None) -> dict[str, Any]:
        """Make an API request with retry logic and JWT management.

        Args:
            verb: HTTP method (GET, POST, DELETE, etc.).
            url: API endpoint path (relative to ROOT_URL/v1/).
            params: Form-encoded body parameters.
            alt_root: Override the base URL entirely.
            query_params: URL query parameters.
            raw_body: Raw body bytes (overrides params).
            content_type: Content-Type header override.
            is_no_auth: Skip authorization header.
            max_retries: Maximum number of retry attempts.
            timeout: Request timeout in seconds.
            extra_headers: Additional HTTP headers to include.

        Returns:
            dict: Parsed JSON response.

        Raises:
            AuthenticationError: on 401 after JWT refresh.
            RateLimitError: on 429 when retry is not enabled.
            ApiError: on other non-200 responses after retries.
        """
        has_auth_refreshed = False

        # Prime JWT if needed
        if not is_no_auth and self._jwt is None:
            if self._on_refresh_auth is not None:
                self._on_refresh_auth(self)
            else:
                self.refresh_jwt()

        retries = 0
        while retries < max_retries:
            retries += 1

            code, data = self._rest_call(
                url, verb, params=params, alt_root=alt_root,
                query_params=query_params, raw_body=raw_body,
                content_type=content_type, is_no_auth=is_no_auth,
                timeout=timeout, extra_headers=extra_headers,
            )

            if code == HTTP_OK:
                return data

            if code == HTTP_UNAUTHORIZED:
                if has_auth_refreshed:
                    break
                if not is_no_auth:
                    has_auth_refreshed = True
                    self._debug("JWT cache: 401 received, invalidating cached token")
                    from .jwt_cache import invalidate_cached_jwt

                    # Mirror auth path selection: OAuth takes priority
                    if self._oauth_creds is not None:
                        invalidate_cached_jwt(
                            self._oid, None, self._oauth_creds, self._uid
                        )
                    else:
                        invalidate_cached_jwt(
                            self._oid, self._api_key, None, self._uid
                        )
                    if self._on_refresh_auth is not None:
                        self._on_refresh_auth(self)
                    else:
                        if self._jwt is not None and self._api_key is None and self._oauth_creds is None:
                            raise AuthenticationError(
                                "Auth error and no API key available to refresh JWT.",
                                code=code,
                            )
                        self.refresh_jwt()
                    continue
                break

            if code == HTTP_TOO_MANY_REQUESTS:
                if self._is_retry_quota_errors:
                    wait = min(10 * (2 ** (retries - 1)), 60)
                    self._debug(f"Rate limited, waiting {wait}s before retry...")
                    time.sleep(wait)
                    continue
                raise RateLimitError(
                    f"Rate limit exceeded: {data}",
                    code=code,
                )

            if code == HTTP_GATEWAY_TIMEOUT:
                if retries < max_retries:
                    wait = 2 ** (retries - 1)
                    self._debug(f"Gateway timeout, retrying in {wait}s...")
                    time.sleep(wait)
                    continue
                break

            # Non-retriable error
            break

        # If we got here, we exhausted retries or hit a non-retriable error
        if code != HTTP_OK:
            raise error_from_status_code(code, data)

        return data

    def raw_request(self, verb: str, url: str, params: dict[str, Any] | None = None, alt_root: str | None = None,
                    query_params: dict[str, Any] | list[tuple[str, str]] | None = None, raw_body: bytes | None = None,
                    content_type: str | None = None, is_no_auth: bool = False,
                    extra_headers: dict[str, str] | None = None) -> tuple[int, Any]:
        """Make a raw API request, returning (status_code, response_data).

        Unlike ``request()``, this method does not raise on non-200 responses.
        It handles JWT priming and a single 401 retry, but otherwise returns
        whatever the server sent.

        Args:
            verb: HTTP method (GET, POST, DELETE, etc.).
            url: API endpoint path (relative to ROOT_URL/v1/).
            params: Form-encoded body parameters.
            alt_root: Override the base URL entirely.
            query_params: URL query parameters.
            raw_body: Raw body bytes (overrides params).
            content_type: Content-Type header override.
            is_no_auth: Skip authorization header.
            extra_headers: Additional HTTP headers to include.

        Returns:
            tuple: (status_code, response_data).
        """
        # Prime JWT if needed.
        if not is_no_auth and self._jwt is None:
            if self._on_refresh_auth is not None:
                self._on_refresh_auth(self)
            else:
                self.refresh_jwt()

        code, data = self._rest_call(
            url, verb, params=params, alt_root=alt_root,
            query_params=query_params, raw_body=raw_body,
            content_type=content_type, is_no_auth=is_no_auth,
            extra_headers=extra_headers,
        )

        # Single 401 retry with JWT refresh.
        if code == HTTP_UNAUTHORIZED and not is_no_auth:
            self._debug("JWT cache: 401 received (raw_request), invalidating cached token")
            from .jwt_cache import invalidate_cached_jwt

            # Mirror auth path selection: OAuth takes priority
            if self._oauth_creds is not None:
                invalidate_cached_jwt(
                    self._oid, None, self._oauth_creds, self._uid
                )
            else:
                invalidate_cached_jwt(
                    self._oid, self._api_key, None, self._uid
                )
            if self._on_refresh_auth is not None:
                self._on_refresh_auth(self)
            else:
                if self._api_key is not None or self._oauth_creds is not None:
                    self.refresh_jwt()
            code, data = self._rest_call(
                url, verb, params=params, alt_root=alt_root,
                query_params=query_params, raw_body=raw_body,
                content_type=content_type, is_no_auth=is_no_auth,
                extra_headers=extra_headers,
            )

        return (code, data)
