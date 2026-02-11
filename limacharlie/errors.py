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


class LimaCharlieError(Exception):
    """Base exception for all LimaCharlie SDK errors."""

    exit_code = 1

    def __init__(self, message, suggestion=None, code=None):
        self.suggestion = suggestion
        self.status_code = code
        if suggestion:
            full = f"{message}\nSuggestion: {suggestion}"
        else:
            full = message
        super().__init__(full)

    @property
    def raw_message(self):
        msg = str(self)
        if self.suggestion and msg.endswith(f"\nSuggestion: {self.suggestion}"):
            return msg[: -len(f"\nSuggestion: {self.suggestion}")]
        return msg


class AuthenticationError(LimaCharlieError):
    """Raised when authentication fails (invalid key, expired JWT, missing creds)."""

    exit_code = 2

    def __init__(self, message, suggestion=None, code=None):
        if suggestion is None:
            suggestion = (
                "Run 'limacharlie auth login' to configure credentials, "
                "or set LC_OID and LC_API_KEY environment variables."
            )
        super().__init__(message, suggestion=suggestion, code=code)


class NotFoundError(LimaCharlieError):
    """Raised when a requested resource is not found (404)."""

    exit_code = 3

    def __init__(self, message, suggestion=None, code=None):
        if suggestion is None:
            suggestion = "Verify the resource name/ID is correct. Use the 'list' command to see available resources."
        super().__init__(message, suggestion=suggestion, code=code or 404)


class ValidationError(LimaCharlieError):
    """Raised when input validation fails."""

    exit_code = 4

    def __init__(self, message, suggestion=None, code=None):
        if suggestion is None:
            suggestion = "Check the command help with --help or --explain for parameter requirements."
        super().__init__(message, suggestion=suggestion, code=code)


class RateLimitError(LimaCharlieError):
    """Raised when the API rate limit is hit (429)."""

    exit_code = 5

    def __init__(self, message=None, retry_after=None, suggestion=None, code=None):
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

    def __init__(self, message, missing_permissions=None, suggestion=None, code=None):
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

    def __init__(self, message, status_code=None, response_body=None, suggestion=None, code=None):
        self.response_body = response_body
        effective_code = code or status_code
        if suggestion is None:
            suggestion = "If this persists, check https://status.limacharlie.io or contact support."
        super().__init__(message, suggestion=suggestion, code=effective_code)


class ConfigError(LimaCharlieError):
    """Raised for configuration file errors."""

    def __init__(self, message, suggestion=None, code=None):
        if suggestion is None:
            suggestion = "Run 'limacharlie auth login' to set up credentials."
        super().__init__(message, suggestion=suggestion, code=code)


def error_from_status_code(status_code, body=None):
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
    )
