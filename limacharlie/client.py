"""HTTP client for LimaCharlie API v2.

Handles JWT generation/refresh, retry with exponential backoff,
rate limit awareness, and request debugging.
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

__version__ = "5.0.1"

ROOT_URL = "https://api.limacharlie.io"
API_VERSION = "v1"
JWT_URL = "https://jwt.limacharlie.io"

HTTP_OK = 200
HTTP_UNAUTHORIZED = 401
HTTP_TOO_MANY_REQUESTS = 429
HTTP_GATEWAY_TIMEOUT = 504


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
    ) -> None:
        """Initialize the client.

        Args:
            oid: Organization ID (UUID string).
            api_key: API key (UUID string).
            uid: User ID for user-scoped API keys.
            environment: Named environment from config file.
            jwt: Pre-generated JWT (skips generation).
            is_retry_quota_errors: Auto-retry on 429 rate limit errors.
            print_debug_fn: Callback for debug messages.
            on_refresh_auth: Callback invoked when JWT is refreshed.
            inv_id: Investigation ID for tracking.
            timeout: Default request timeout in seconds.
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
        self._jwt = jwt
        self._is_retry_quota_errors = is_retry_quota_errors
        self._debug_fn = print_debug_fn
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
            self._refresh_jwt_oauth(effective_oid, expiry)
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

        self._jwt = self._call_jwt_endpoint(auth_data)

        if self._on_refresh_auth is not None:
            self._on_refresh_auth(self)

    def _refresh_jwt_oauth(self, effective_oid: str | None, expiry: int | None) -> None:
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

    def _rest_call(self, url: str, verb: str, params: dict[str, Any] | None = None, alt_root: str | None = None, query_params: dict[str, str] | None = None,
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
            full_url = f"{full_url}?{urlencode(query_params)}"

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

        try:
            if self._ssl_context is not None and full_url.startswith("https"):
                u = urlopen(request, timeout=effective_timeout, context=self._ssl_context)
            else:
                u = urlopen(request, timeout=effective_timeout)

            try:
                data = u.read()
                resp = json.loads(data.decode()) if data else {}
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
                u.close()

            self._debug(f"{verb} {full_url} => 200")
            return (HTTP_OK, resp)

        except HTTPError as e:
            error_body = e.read()
            try:
                resp = json.loads(error_body.decode())
            except Exception:
                resp = error_body.decode() if error_body else ""
            self._debug(f"{verb} {full_url} => {e.code}: {resp}")
            return (e.code, resp)

        except ssl.SSLError as e:
            self._debug(f"SSL error: {e}")
            return (HTTP_GATEWAY_TIMEOUT, {"error": f"SSL error: {e}"})

    def request(self, verb: str, url: str, params: dict[str, Any] | None = None, alt_root: str | None = None, query_params: dict[str, str] | None = None,
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
                    query_params: dict[str, str] | None = None, raw_body: bytes | None = None,
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
