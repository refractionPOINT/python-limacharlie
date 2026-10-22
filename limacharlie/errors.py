from __future__ import annotations

"""Custom exception hierarchy for LimaCharlie SDK & CLI v2.

Every exception includes a suggestion message to guide users toward resolution.
Exit codes:
    0 = success
    1 = general error
    2 = auth error
    3 = not found
    4 = validation error
    5 = rate limit error
"""

from typing import Any


class LimaCharlieError(Exception):
    """Base exception for all LimaCharlie SDK errors."""

    exit_code = 1

    def __init__(self, message: str, suggestion: str | None = None, code: int | None = None) -> None:
        self.suggestion = suggestion
        self.status_code = code
        if suggestion:
            full = f"{message}\nSuggestion: {suggestion}"
        else:
            full = message
        super().__init__(full)

    @property
    def raw_message(self) -> str:
        msg = str(self)
        if self.suggestion and msg.endswith(f"\nSuggestion: {self.suggestion}"):
            return msg[: -len(f"\nSuggestion: {self.suggestion}")]
        return msg


class AuthenticationError(LimaCharlieError):
    """Raised when authentication fails (invalid key, expired JWT, missing creds)."""

    exit_code = 2

    def __init__(self, message: str, suggestion: str | None = None, code: int | None = None) -> None:
        if suggestion is None:
            suggestion = (
                "Run 'limacharlie auth login' to configure credentials, "
                "or set LC_OID and LC_API_KEY environment variables."
            )
        super().__init__(message, suggestion=suggestion, code=code)


class NotFoundError(LimaCharlieError):
    """Raised when a requested resource is not found (404)."""

    exit_code = 3

    def __init__(self, message: str, suggestion: str | None = None, code: int | None = None) -> None:
        if suggestion is None:
            suggestion = "Verify the resource name/ID is correct. Use the 'list' command to see available resources."
        super().__init__(message, suggestion=suggestion, code=code or 404)


class ValidationError(LimaCharlieError):
    """Raised when input validation fails."""

    exit_code = 4

    def __init__(self, message: str, suggestion: str | None = None, code: int | None = None) -> None:
        if suggestion is None:
            suggestion = "Check the command help with --help or --explain for parameter requirements."
        super().__init__(message, suggestion=suggestion, code=code)


class RateLimitError(LimaCharlieError):
    """Raised when the API rate limit is hit (429)."""

    exit_code = 5

    def __init__(self, message: str | None = None, retry_after: int | None = None, suggestion: str | None = None, code: int | None = None) -> None:
        self.retry_after = retry_after
        if message is None:
            message = "API rate limit exceeded."
        if suggestion is None:
            if retry_after:
                suggestion = f"Wait {retry_after} seconds and retry, or use --retry for automatic backoff."
            else:
                suggestion = "Wait a moment and retry, or use --retry for automatic backoff."
        super().__init__(message, suggestion=suggestion, code=code or 429)


class PermissionDeniedError(LimaCharlieError):
    """Raised when the user lacks required permissions."""

    exit_code = 2

    def __init__(self, message: str, missing_permissions: list[str] | None = None, suggestion: str | None = None, code: int | None = None) -> None:
        self.missing_permissions = missing_permissions or []
        if suggestion is None:
            if missing_permissions:
                perms = ", ".join(missing_permissions)
                suggestion = (
                    f"Ask your org admin to grant '{perms}' permission, "
                    "or create a new API key with 'limacharlie api-key create'."
                )
            else:
                suggestion = "Ensure your API key has the required permissions."
        super().__init__(message, suggestion=suggestion, code=code or 403)


class ApiError(LimaCharlieError):
    """Raised for general API errors not covered by more specific exceptions."""

    def __init__(self, message: str, status_code: int | None = None, response_body: Any = None, suggestion: str | None = None, code: int | None = None) -> None:
        self.response_body = response_body
        effective_code = code or status_code
        if suggestion is None:
            suggestion = "If this persists, check https://status.limacharlie.io or contact support."
        super().__init__(message, suggestion=suggestion, code=effective_code)

    @property
    def error_code(self) -> str | None:
        """The API's error code (e.g. ``HIVE_LISTING_TOO_LARGE``), if the answer carried one."""
        return api_error_code(self.response_body)

    @property
    def skipped_hives(self) -> dict[str, str]:
        """Hives left out of an ``INCOMPLETE_RESULT`` answer, as hive name -> reason code."""
        if isinstance(self.response_body, dict) and isinstance(self.response_body.get("skipped_hives"), dict):
            return {str(k): str(v) for k, v in self.response_body["skipped_hives"].items()}
        return {}


class SearchError(LimaCharlieError):
    """Raised when a search query fails.

    Includes query_id, region, and oid for troubleshooting. These fields
    are essential when filing support tickets - they allow backend engineers
    to locate the exact query in orchestrator and worker logs.
    """

    exit_code = 1

    def __init__(
        self,
        message: str,
        query_id: str | None = None,
        region: str | None = None,
        oid: str | None = None,
        query: str | None = None,
        suggestion: str | None = None,
        code: int | None = None,
    ) -> None:
        self.query_id = query_id
        self.region = region
        self.oid = oid
        self.query = query

        # Build context suffix for the error message so query_id, region,
        # and oid are always visible in logs and CLI output.
        context_parts: list[str] = []
        if query_id:
            context_parts.append(f"query_id={query_id}")
        if region:
            context_parts.append(f"region={region}")
        if oid:
            context_parts.append(f"oid={oid}")
        if query:
            # Truncate long queries to keep error messages readable.
            display_query = query if len(query) <= 120 else query[:117] + "..."
            context_parts.append(f"query={display_query}")
        context = f" [{', '.join(context_parts)}]" if context_parts else ""

        if suggestion is None:
            suggestion = _search_suggestion(message)
        super().__init__(f"{message}{context}", suggestion=suggestion, code=code)


# Keywords that indicate the search failed due to an expired auth token.
_TOKEN_EXPIRY_KEYWORDS = ("401", "unauthorized", "token expired", "authentication failed", "jwt expired")

_TOKEN_EXPIRY_SUGGESTION = (
    "Your authentication token likely expired during this long-running query.\n"
    "To avoid this, use --token-expiry to set a longer token validity "
    "(e.g. --token-expiry 8 for 8 hours),\n"
    "or set 'search_token_expiry_hours' in ~/.limacharlie."
)

# Keywords that indicate a self-explanatory error where adding a generic
# "if this persists, contact support" suggestion would just be noise.
_SELF_EXPLANATORY_KEYWORDS = (
    "transcode", "syntax", "parse", "no match found", "expected",
    "invalid query", "validation", "quota exceeded", "permission",
)

_SUPPORT_SUGGESTION = (
    "Contact support and include the query_id shown above for faster troubleshooting."
)


def _search_suggestion(message: str) -> str:
    """Pick the most helpful suggestion based on the error message.

    Returns None for self-explanatory errors (syntax, validation) to avoid
    adding noise. Returns a specific suggestion for token expiry errors.
    Returns a generic support suggestion for unexpected server-side failures.
    """
    lower = message.lower()
    if any(kw in lower for kw in _TOKEN_EXPIRY_KEYWORDS):
        return _TOKEN_EXPIRY_SUGGESTION
    if any(kw in lower for kw in _SELF_EXPLANATORY_KEYWORDS):
        return None
    return _SUPPORT_SUGGESTION


class ConfigError(LimaCharlieError):
    """Raised for configuration file errors."""

    def __init__(self, message: str, suggestion: str | None = None, code: int | None = None) -> None:
        if suggestion is None:
            suggestion = "Run 'limacharlie auth login' to set up credentials."
        super().__init__(message, suggestion=suggestion, code=code)


# Where the user-facing explanation of the "too large" and "incomplete" answers lives.
SIZE_LIMITS_DOC_URL = "https://docs.limacharlie.io/8-reference/faq/large-and-incomplete-results/"

HIVE_LISTING_TOO_LARGE = "HIVE_LISTING_TOO_LARGE"
INVALID_CURSOR = "INVALID_CURSOR"
INCOMPLETE_RESULT = "INCOMPLETE_RESULT"
FP_LISTING_TOO_LARGE = "FP_LISTING_TOO_LARGE"


def api_error_code(body: Any) -> str | None:
    """Return the error code of an API answer body, if it carries one.

    The gateway reports it as ``error_code`` or, for errors raised by a
    backend, as the ``lc_error_code:<CODE> - <detail>`` prefix of ``error``.

    Args:
        body: The parsed response body.

    Returns:
        str | None: The code, or None when the body has none.
    """
    if not isinstance(body, dict):
        return None
    code = body.get("error_code")
    if isinstance(code, str) and code:
        return code
    error = body.get("error")
    prefix = "lc_error_code:"
    if isinstance(error, str) and error.startswith(prefix):
        return error[len(prefix):].split(" ", 1)[0] or None
    return None


def _hive_names(skipped: dict[str, str]) -> str:
    return ", ".join(sorted(skipped))


def size_limit_suggestion(status_code: int, body: Any) -> str | None:
    """Say what to do about a "too large" or "incomplete" answer.

    Args:
        status_code: HTTP status code of the answer.
        body: The parsed response body.

    Returns:
        str | None: The advice, with the flag, SDK call or API parameter to use
            and a link to the explanation; None for any other error.
    """
    code = api_error_code(body)
    if code == HIVE_LISTING_TOO_LARGE:
        return (
            "This hive is too big to return in one response, and retrying will not help. "
            "Read it page by page: CLI '--limit 100' (continue with '--cursor <next_cursor>'), "
            "SDK Hive.iter_pages(), API 'limit=100&cursor=<next_cursor>'. "
            "For names and metadata only, use '--metadata-only' (CLI) or 'mtd_only=true' (API). "
            f"See {SIZE_LIMITS_DOC_URL}#hive_listing_too_large"
        )
    if code == INVALID_CURSOR:
        return (
            "The cursor was not accepted: it is not one this listing returned, or it was changed. "
            "Pass the 'next_cursor' of the previous page unchanged, or drop '--cursor' (API 'cursor') "
            "to start again from the first page. "
            f"See {SIZE_LIMITS_DOC_URL}#invalid_cursor"
        )
    if code == INCOMPLETE_RESULT:
        skipped: dict[str, str] = {}
        if isinstance(body, dict) and isinstance(body.get("skipped_hives"), dict):
            skipped = {str(k): str(v) for k, v in body["skipped_hives"].items()}
        which = f" (hives not read: {_hive_names(skipped)})" if skipped else ""
        if status_code == 503:
            return (
                f"Some hives could not be read right now{which}, so the result would be missing records. "
                "Retry in a moment. To accept what could be read instead, pass 'allow_partial=true' (API); "
                "the result is then flagged 'partial: true' and lists 'skipped_hives'. "
                f"See {SIZE_LIMITS_DOC_URL}#incomplete_result"
            )
        return (
            f"Some hives hold more matching records than one answer can carry{which}, so the result "
            "would be missing records. Retrying will not help: reduce the number of records in those "
            "hives, or pass 'allow_partial=true' (API) to accept a partial result. "
            f"See {SIZE_LIMITS_DOC_URL}#incomplete_result"
        )
    if code == FP_LISTING_TOO_LARGE:
        return (
            "The false positive rules of this organization are too many for the legacy "
            "'GET /v1/fp/{oid}' listing. Page through the fp hive instead: CLI "
            "'limacharlie fp list --limit 100', SDK Hive(org, 'fp').iter_pages(), "
            "API 'GET /v1/hive/fp/{oid}?limit=100'. "
            f"See {SIZE_LIMITS_DOC_URL}#fp_listing_too_large"
        )
    return None


def error_from_status_code(status_code: int, body: Any = None) -> LimaCharlieError:
    """Create the appropriate exception from an HTTP status code.

    Args:
        status_code: HTTP status code.
        body: Response body (str or dict).

    Returns:
        A LimaCharlieError subclass instance.
    """
    body_str = str(body) if body else "No response body"

    if status_code == 401:
        return AuthenticationError(
            f"Authentication failed: {body_str}",
            code=status_code,
        )
    if status_code == 403:
        return PermissionDeniedError(
            f"Permission denied: {body_str}",
            code=status_code,
        )
    if status_code == 404:
        return NotFoundError(
            f"Resource not found: {body_str}",
            code=status_code,
        )
    if status_code == 422:
        return ValidationError(
            f"Validation error: {body_str}",
            code=status_code,
        )
    if status_code == 429:
        return RateLimitError(
            f"Rate limit exceeded: {body_str}",
            code=status_code,
        )
    return ApiError(
        f"API error ({status_code}): {body_str}",
        status_code=status_code,
        response_body=body,
        suggestion=size_limit_suggestion(status_code, body),
    )
