"""Tests for the 'limacharlie api' command."""

import json
import os
import tempfile
from unittest.mock import patch, MagicMock

from click.testing import CliRunner

from limacharlie.cli import cli


_MOCK_OID = "aaaa-bbbb-cccc-dddd"


def _patch_client(status=200, data=None):
    """Return a patch context manager that mocks Client for api_cmd.

    The mock client's ``raw_request`` returns (status, data).
    ``oid`` is set to _MOCK_OID.
    """
    if data is None:
        data = {"ok": True}

    mock_client = MagicMock()
    mock_client.oid = _MOCK_OID
    mock_client.raw_request.return_value = (status, data)
    return patch("limacharlie.commands.api_cmd.Client", return_value=mock_client)


class TestApiHelp:
    def test_help_output(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["api", "--help"])
        assert result.exit_code == 0
        assert "ENDPOINT" in result.output
        assert "--method" in result.output
        assert "--target" in result.output
        assert "--no-auth" in result.output
        assert "--silent" in result.output
        assert "--include" in result.output
        assert "--raw-field" in result.output
        assert "--field" in result.output
        assert "--input" in result.output
        assert "--header" in result.output


class TestEndpointPlaceholder:
    def test_oid_placeholder_expansion(self):
        with _patch_client() as mock_cls:
            runner = CliRunner()
            result = runner.invoke(cli, ["api", "orgs/{oid}/sensors"])
            assert result.exit_code == 0
            mock_client = mock_cls.return_value
            args, kwargs = mock_client.raw_request.call_args
            assert args[1] == f"orgs/{_MOCK_OID}/sensors"

    def test_literal_oid_passthrough(self):
        with _patch_client() as mock_cls:
            runner = CliRunner()
            result = runner.invoke(cli, ["api", "orgs/1234-5678/sensors"])
            assert result.exit_code == 0
            args, _ = mock_cls.return_value.raw_request.call_args
            assert args[1] == "orgs/1234-5678/sensors"

    def test_oid_placeholder_without_oid_configured(self):
        mock_client = MagicMock()
        mock_client.oid = None
        with patch("limacharlie.commands.api_cmd.Client", return_value=mock_client):
            runner = CliRunner()
            result = runner.invoke(cli, ["api", "orgs/{oid}/sensors"])
            assert result.exit_code != 0
            assert "{oid}" in result.output


class TestTargetResolution:
    def test_default_target_uses_no_alt_root(self):
        with _patch_client() as mock_cls:
            runner = CliRunner()
            result = runner.invoke(cli, ["api", "sensors"])
            assert result.exit_code == 0
            _, kwargs = mock_cls.return_value.raw_request.call_args
            assert kwargs.get("alt_root") is None

    def test_billing_target(self):
        with _patch_client() as mock_cls:
            runner = CliRunner()
            result = runner.invoke(cli, ["api", "--target", "billing", "orgs/{oid}/status"])
            assert result.exit_code == 0
            _, kwargs = mock_cls.return_value.raw_request.call_args
            assert kwargs["alt_root"] == "https://billing.limacharlie.io"

    def test_raw_url_target(self):
        with _patch_client() as mock_cls:
            runner = CliRunner()
            result = runner.invoke(cli, ["api", "--target", "https://custom.example.com", "endpoint"])
            assert result.exit_code == 0
            _, kwargs = mock_cls.return_value.raw_request.call_args
            assert kwargs["alt_root"] == "https://custom.example.com"

    def test_bare_hostname_target(self):
        with _patch_client() as mock_cls:
            runner = CliRunner()
            result = runner.invoke(cli, ["api", "--target", "ticketing.limacharlie.io", "tickets"])
            assert result.exit_code == 0
            _, kwargs = mock_cls.return_value.raw_request.call_args
            assert kwargs["alt_root"] == "https://ticketing.limacharlie.io"


class TestRawFieldParsing:
    def test_single_raw_field(self):
        with _patch_client() as mock_cls:
            runner = CliRunner()
            result = runner.invoke(cli, ["api", "endpoint", "-f", "name=test"])
            assert result.exit_code == 0
            _, kwargs = mock_cls.return_value.raw_request.call_args
            body = json.loads(kwargs["raw_body"].decode())
            assert body == {"name": "test"}

    def test_multiple_raw_fields(self):
        with _patch_client() as mock_cls:
            runner = CliRunner()
            result = runner.invoke(cli, ["api", "endpoint", "-f", "a=1", "-f", "b=2"])
            assert result.exit_code == 0
            _, kwargs = mock_cls.return_value.raw_request.call_args
            body = json.loads(kwargs["raw_body"].decode())
            assert body == {"a": "1", "b": "2"}

    def test_raw_field_content_type_is_json(self):
        with _patch_client() as mock_cls:
            runner = CliRunner()
            result = runner.invoke(cli, ["api", "endpoint", "-f", "k=v"])
            assert result.exit_code == 0
            _, kwargs = mock_cls.return_value.raw_request.call_args
            assert kwargs["content_type"] == "application/json"


class TestTypedFieldParsing:
    def test_bool_coercion(self):
        with _patch_client() as mock_cls:
            runner = CliRunner()
            result = runner.invoke(cli, ["api", "endpoint", "-F", "enabled=true", "-F", "verbose=false"])
            assert result.exit_code == 0
            _, kwargs = mock_cls.return_value.raw_request.call_args
            body = json.loads(kwargs["raw_body"].decode())
            assert body["enabled"] is True
            assert body["verbose"] is False

    def test_int_coercion(self):
        with _patch_client() as mock_cls:
            runner = CliRunner()
            result = runner.invoke(cli, ["api", "endpoint", "-F", "limit=42"])
            assert result.exit_code == 0
            _, kwargs = mock_cls.return_value.raw_request.call_args
            body = json.loads(kwargs["raw_body"].decode())
            assert body["limit"] == 42
            assert isinstance(body["limit"], int)

    def test_float_coercion(self):
        with _patch_client() as mock_cls:
            runner = CliRunner()
            result = runner.invoke(cli, ["api", "endpoint", "-F", "rate=3.14"])
            assert result.exit_code == 0
            _, kwargs = mock_cls.return_value.raw_request.call_args
            body = json.loads(kwargs["raw_body"].decode())
            assert body["rate"] == 3.14

    def test_at_file_reads_contents(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("file-contents-here")
            f.flush()
            tmppath = f.name
        try:
            with _patch_client() as mock_cls:
                runner = CliRunner()
                result = runner.invoke(cli, ["api", "endpoint", "-F", f"data=@{tmppath}"])
                assert result.exit_code == 0
                _, kwargs = mock_cls.return_value.raw_request.call_args
                body = json.loads(kwargs["raw_body"].decode())
                assert body["data"] == "file-contents-here"
        finally:
            os.unlink(tmppath)

    def test_mixed_f_and_F(self):
        with _patch_client() as mock_cls:
            runner = CliRunner()
            result = runner.invoke(cli, ["api", "endpoint", "-f", "name=test", "-F", "count=5"])
            assert result.exit_code == 0
            _, kwargs = mock_cls.return_value.raw_request.call_args
            body = json.loads(kwargs["raw_body"].decode())
            assert body["name"] == "test"
            assert body["count"] == 5


class TestMethodDetection:
    def test_default_get(self):
        with _patch_client() as mock_cls:
            runner = CliRunner()
            result = runner.invoke(cli, ["api", "endpoint"])
            assert result.exit_code == 0
            args, _ = mock_cls.return_value.raw_request.call_args
            assert args[0] == "GET"

    def test_auto_post_with_body(self):
        with _patch_client() as mock_cls:
            runner = CliRunner()
            result = runner.invoke(cli, ["api", "endpoint", "-f", "k=v"])
            assert result.exit_code == 0
            args, _ = mock_cls.return_value.raw_request.call_args
            assert args[0] == "POST"

    def test_explicit_method(self):
        with _patch_client() as mock_cls:
            runner = CliRunner()
            result = runner.invoke(cli, ["api", "endpoint", "-X", "DELETE"])
            assert result.exit_code == 0
            args, _ = mock_cls.return_value.raw_request.call_args
            assert args[0] == "DELETE"

    def test_explicit_get_with_fields_uses_query_params(self):
        with _patch_client() as mock_cls:
            runner = CliRunner()
            result = runner.invoke(cli, ["api", "endpoint", "-X", "GET", "-f", "limit=10"])
            assert result.exit_code == 0
            _, kwargs = mock_cls.return_value.raw_request.call_args
            assert kwargs["query_params"] == {"limit": "10"}
            assert kwargs.get("raw_body") is None


class TestInputFile:
    def test_input_from_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"key": "value"}, f)
            f.flush()
            tmppath = f.name
        try:
            with _patch_client() as mock_cls:
                runner = CliRunner()
                result = runner.invoke(cli, ["api", "endpoint", "--input", tmppath])
                assert result.exit_code == 0
                _, kwargs = mock_cls.return_value.raw_request.call_args
                body = json.loads(kwargs["raw_body"].decode())
                assert body == {"key": "value"}
                assert kwargs["content_type"] == "application/json"
        finally:
            os.unlink(tmppath)

    def test_input_from_stdin(self):
        with _patch_client() as mock_cls:
            runner = CliRunner()
            result = runner.invoke(cli, ["api", "endpoint", "--input", "-"], input='{"stdin": true}')
            assert result.exit_code == 0
            _, kwargs = mock_cls.return_value.raw_request.call_args
            body = json.loads(kwargs["raw_body"].decode())
            assert body == {"stdin": True}

    def test_input_non_json_content_type(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("plain text body")
            f.flush()
            tmppath = f.name
        try:
            with _patch_client() as mock_cls:
                runner = CliRunner()
                result = runner.invoke(cli, ["api", "endpoint", "--input", tmppath])
                assert result.exit_code == 0
                _, kwargs = mock_cls.return_value.raw_request.call_args
                assert kwargs["content_type"] == "application/octet-stream"
        finally:
            os.unlink(tmppath)


class TestMutualExclusivity:
    def test_input_with_raw_field_rejected(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["api", "endpoint", "--input", "-", "-f", "k=v"], input="body")
        assert result.exit_code != 0
        assert "--input" in result.output

    def test_input_with_typed_field_rejected(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["api", "endpoint", "--input", "-", "-F", "k=v"], input="body")
        assert result.exit_code != 0
        assert "--input" in result.output


class TestIncludeStatus:
    def test_include_status_flag(self):
        with _patch_client(status=200):
            runner = CliRunner()
            result = runner.invoke(cli, ["api", "endpoint", "-i"])
            assert result.exit_code == 0
            assert "HTTP 200" in result.output

    def test_include_status_with_error(self):
        with _patch_client(status=404, data={"error": "not found"}):
            runner = CliRunner()
            result = runner.invoke(cli, ["api", "endpoint", "-i"])
            assert "HTTP 404" in result.output


class TestSilentFlag:
    def test_silent_suppresses_body(self):
        with _patch_client(status=200, data={"secret": "data"}):
            runner = CliRunner()
            result = runner.invoke(cli, ["api", "endpoint", "--silent"])
            assert result.exit_code == 0
            assert "secret" not in result.output
            assert "data" not in result.output


class TestExitCodes:
    def test_200_exit_code_0(self):
        with _patch_client(status=200):
            runner = CliRunner()
            result = runner.invoke(cli, ["api", "endpoint"])
            assert result.exit_code == 0

    def test_404_exit_code_4(self):
        with _patch_client(status=404, data={"error": "not found"}):
            runner = CliRunner()
            result = runner.invoke(cli, ["api", "endpoint"])
            assert result.exit_code == 4

    def test_500_exit_code_5(self):
        with _patch_client(status=500, data={"error": "internal"}):
            runner = CliRunner()
            result = runner.invoke(cli, ["api", "endpoint"])
            assert result.exit_code == 5

    def test_201_exit_code_0(self):
        with _patch_client(status=201, data={"created": True}):
            runner = CliRunner()
            result = runner.invoke(cli, ["api", "endpoint"])
            assert result.exit_code == 0

    def test_403_exit_code_4(self):
        with _patch_client(status=403, data={"error": "forbidden"}):
            runner = CliRunner()
            result = runner.invoke(cli, ["api", "endpoint"])
            assert result.exit_code == 4


class TestNoAuth:
    def test_no_auth_passthrough(self):
        with _patch_client() as mock_cls:
            runner = CliRunner()
            result = runner.invoke(cli, ["api", "endpoint", "--no-auth"])
            assert result.exit_code == 0
            _, kwargs = mock_cls.return_value.raw_request.call_args
            assert kwargs["is_no_auth"] is True

    def test_default_has_auth(self):
        with _patch_client() as mock_cls:
            runner = CliRunner()
            result = runner.invoke(cli, ["api", "endpoint"])
            assert result.exit_code == 0
            _, kwargs = mock_cls.return_value.raw_request.call_args
            assert kwargs["is_no_auth"] is False


class TestCustomHeaders:
    def test_single_header(self):
        with _patch_client() as mock_cls:
            runner = CliRunner()
            result = runner.invoke(cli, ["api", "endpoint", "-H", "X-Custom: myval"])
            assert result.exit_code == 0
            _, kwargs = mock_cls.return_value.raw_request.call_args
            assert kwargs["extra_headers"] == {"X-Custom": "myval"}

    def test_multiple_headers(self):
        with _patch_client() as mock_cls:
            runner = CliRunner()
            result = runner.invoke(cli, ["api", "endpoint", "-H", "X-A: 1", "-H", "X-B: 2"])
            assert result.exit_code == 0
            _, kwargs = mock_cls.return_value.raw_request.call_args
            assert kwargs["extra_headers"] == {"X-A": "1", "X-B": "2"}

    def test_no_headers_passes_none(self):
        with _patch_client() as mock_cls:
            runner = CliRunner()
            result = runner.invoke(cli, ["api", "endpoint"])
            assert result.exit_code == 0
            _, kwargs = mock_cls.return_value.raw_request.call_args
            assert kwargs["extra_headers"] is None


class TestOutputIntegration:
    def test_json_output_format(self):
        with _patch_client(data={"name": "test-org"}):
            runner = CliRunner()
            result = runner.invoke(cli, ["--output", "json", "api", "endpoint"])
            assert result.exit_code == 0
            parsed = json.loads(result.output)
            assert parsed["name"] == "test-org"

    def test_include_and_json_output(self):
        with _patch_client(status=200, data={"items": [1, 2]}):
            runner = CliRunner()
            result = runner.invoke(cli, ["--output", "json", "api", "endpoint", "-i"])
            assert result.exit_code == 0
            lines = result.output.strip().split("\n")
            assert lines[0] == "HTTP 200"
            # Remaining lines should be valid JSON
            body = "\n".join(lines[1:])
            parsed = json.loads(body)
            assert parsed["items"] == [1, 2]
