"""Tests for download commands and SDK."""

import os
import tempfile
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner

from limacharlie.cli import cli
from limacharlie.sdk.downloads import (
    SENSOR_TARGETS,
    ADAPTER_TARGETS,
    list_sensor_targets,
    list_adapter_targets,
    download_binary,
    DOWNLOADS_URL,
)


# ---------------------------------------------------------------------------
# SDK unit tests
# ---------------------------------------------------------------------------

class TestListTargets:
    def test_list_sensor_targets_returns_list(self):
        targets = list_sensor_targets()
        assert isinstance(targets, list)
        assert len(targets) > 0

    def test_list_sensor_targets_structure(self):
        targets = list_sensor_targets()
        for t in targets:
            assert "platform" in t
            assert "arch" in t
            assert "url" in t
            assert t["url"].startswith(DOWNLOADS_URL)

    def test_list_sensor_targets_covers_all(self):
        targets = list_sensor_targets()
        pairs = {(t["platform"], t["arch"]) for t in targets}
        for key in SENSOR_TARGETS:
            assert key in pairs

    def test_list_adapter_targets_returns_list(self):
        targets = list_adapter_targets()
        assert isinstance(targets, list)
        assert len(targets) > 0

    def test_list_adapter_targets_structure(self):
        targets = list_adapter_targets()
        for t in targets:
            assert "platform" in t
            assert "arch" in t
            assert "url" in t
            assert t["url"].startswith(DOWNLOADS_URL)

    def test_list_adapter_targets_covers_all(self):
        targets = list_adapter_targets()
        pairs = {(t["platform"], t["arch"]) for t in targets}
        for key in ADAPTER_TARGETS:
            assert key in pairs


class TestSensorTargetMatrix:
    def test_windows_targets(self):
        assert ("windows", "64") in SENSOR_TARGETS
        assert ("windows", "32") in SENSOR_TARGETS
        assert ("windows", "arm64") in SENSOR_TARGETS
        assert ("windows", "msi64") in SENSOR_TARGETS
        assert ("windows", "msi32") in SENSOR_TARGETS

    def test_linux_targets(self):
        assert ("linux", "64") in SENSOR_TARGETS
        assert ("linux", "deb64") in SENSOR_TARGETS
        assert ("linux", "debarm64") in SENSOR_TARGETS
        assert ("linux", "alpine64") in SENSOR_TARGETS

    def test_mac_targets(self):
        assert ("mac", "64") in SENSOR_TARGETS
        assert ("mac", "arm64") in SENSOR_TARGETS

    def test_chrome_target(self):
        assert ("chrome", "") in SENSOR_TARGETS


class TestAdapterTargetMatrix:
    def test_linux_targets(self):
        assert ("linux", "64") in ADAPTER_TARGETS
        assert ("linux", "arm") in ADAPTER_TARGETS
        assert ("linux", "arm64") in ADAPTER_TARGETS

    def test_windows_targets(self):
        assert ("windows", "64") in ADAPTER_TARGETS

    def test_mac_targets(self):
        assert ("mac", "64") in ADAPTER_TARGETS
        assert ("mac", "arm64") in ADAPTER_TARGETS

    def test_unix_targets(self):
        assert ("aix", "ppc64") in ADAPTER_TARGETS
        assert ("freebsd", "64") in ADAPTER_TARGETS
        assert ("openbsd", "64") in ADAPTER_TARGETS
        assert ("netbsd", "64") in ADAPTER_TARGETS
        assert ("solaris", "64") in ADAPTER_TARGETS


class TestDownloadBinary:
    def test_invalid_sensor_target_raises(self):
        with pytest.raises(ValueError, match="Unknown sensor target"):
            download_binary("sensor", "plan9", "mips")

    def test_invalid_adapter_target_raises(self):
        with pytest.raises(ValueError, match="Unknown adapter target"):
            download_binary("adapter", "plan9", "mips")

    @patch("limacharlie.sdk.downloads.urlopen")
    def test_successful_sensor_download(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"\x00BINARY_CONTENT"
        mock_resp.close.return_value = None
        mock_urlopen.return_value = mock_resp

        data = download_binary("sensor", "linux", "64")
        assert data == b"\x00BINARY_CONTENT"

        # Verify the URL was correct
        call_args = mock_urlopen.call_args
        request_obj = call_args[0][0] if call_args[0] else call_args[1].get("url")
        if hasattr(request_obj, "full_url"):
            assert "sensor/linux/64" in request_obj.full_url
        mock_resp.close.assert_called_once()

    @patch("limacharlie.sdk.downloads.urlopen")
    def test_successful_adapter_download(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"\x00ADAPTER_BINARY"
        mock_resp.close.return_value = None
        mock_urlopen.return_value = mock_resp

        data = download_binary("adapter", "mac", "arm64")
        assert data == b"\x00ADAPTER_BINARY"
        mock_resp.close.assert_called_once()

    @patch("limacharlie.sdk.downloads.urlopen")
    def test_http_error_raises_runtime_error(self, mock_urlopen):
        from urllib.error import HTTPError
        mock_urlopen.side_effect = HTTPError(
            url="https://downloads.limacharlie.io/sensor/linux/64",
            code=404,
            msg="Not Found",
            hdrs={},
            fp=None,
        )
        with pytest.raises(RuntimeError, match="HTTP 404"):
            download_binary("sensor", "linux", "64")


# ---------------------------------------------------------------------------
# CLI unit tests
# ---------------------------------------------------------------------------

class TestDownloadCLI:
    """Test CLI commands without making real HTTP requests."""

    def test_download_group_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["download", "--help"])
        assert result.exit_code == 0
        assert "sensor" in result.output
        assert "adapter" in result.output

    def test_download_sensor_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["download", "sensor", "--help"])
        assert result.exit_code == 0
        assert "--platform" in result.output
        assert "--arch" in result.output
        assert "--list" in result.output
        assert "--output-path" in result.output

    def test_download_adapter_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["download", "adapter", "--help"])
        assert result.exit_code == 0
        assert "--platform" in result.output
        assert "--arch" in result.output
        assert "--list" in result.output

    def test_download_list_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["download", "list", "--help"])
        assert result.exit_code == 0

    def test_download_sensor_list_flag(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--output", "json", "download", "sensor", "--list"])
        assert result.exit_code == 0
        assert "linux" in result.output
        assert "windows" in result.output
        assert "mac" in result.output

    def test_download_adapter_list_flag(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--output", "json", "download", "adapter", "--list"])
        assert result.exit_code == 0
        assert "linux" in result.output
        assert "freebsd" in result.output

    def test_download_list_command(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--output", "json", "download", "list"])
        assert result.exit_code == 0
        assert "sensor" in result.output
        assert "adapter" in result.output

    def test_download_sensor_no_platform_errors(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["download", "sensor"])
        assert result.exit_code != 0

    def test_download_sensor_no_arch_errors(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["download", "sensor", "--platform", "linux"])
        assert result.exit_code != 0

    def test_download_adapter_no_platform_errors(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["download", "adapter"])
        assert result.exit_code != 0

    def test_download_adapter_no_arch_errors(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["download", "adapter", "--platform", "linux"])
        assert result.exit_code != 0

    def test_download_sensor_invalid_arch_errors(self):
        runner = CliRunner()
        result = runner.invoke(cli, [
            "download", "sensor",
            "--platform", "linux", "--arch", "sparc",
        ])
        assert result.exit_code != 0
        assert "Invalid architecture" in result.output or "Error" in result.output

    def test_download_adapter_invalid_arch_errors(self):
        runner = CliRunner()
        result = runner.invoke(cli, [
            "download", "adapter",
            "--platform", "linux", "--arch", "sparc",
        ])
        assert result.exit_code != 0

    def test_download_sensor_explain(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["download", "sensor", "--explain"])
        assert result.exit_code == 0
        assert "sensor" in result.output.lower()
        assert "installation key" in result.output.lower() or "installation_key" in result.output.lower()

    def test_download_adapter_explain(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["download", "adapter", "--explain"])
        assert result.exit_code == 0
        assert "adapter" in result.output.lower()

    def test_download_list_explain(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["download", "list", "--explain"])
        assert result.exit_code == 0

    @patch("limacharlie.commands.download.download_binary")
    def test_download_sensor_saves_file(self, mock_download):
        mock_download.return_value = b"\x7fELF_FAKE_BINARY"
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "sensor_test")
            result = runner.invoke(cli, [
                "download", "sensor",
                "--platform", "linux", "--arch", "64",
                "-o", out_path,
            ])
            assert result.exit_code == 0
            assert os.path.exists(out_path)
            with open(out_path, "rb") as f:
                assert f.read() == b"\x7fELF_FAKE_BINARY"
            # Check it's executable
            assert os.access(out_path, os.X_OK)

        mock_download.assert_called_once_with("sensor", "linux", "64")

    @patch("limacharlie.commands.download.download_binary")
    def test_download_adapter_saves_file(self, mock_download):
        mock_download.return_value = b"\x7fELF_ADAPTER"
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "adapter_test")
            result = runner.invoke(cli, [
                "download", "adapter",
                "--platform", "linux", "--arch", "64",
                "-o", out_path,
            ])
            assert result.exit_code == 0
            assert os.path.exists(out_path)
            with open(out_path, "rb") as f:
                assert f.read() == b"\x7fELF_ADAPTER"

        mock_download.assert_called_once_with("adapter", "linux", "64")

    @patch("limacharlie.commands.download.download_binary")
    def test_download_sensor_default_filename(self, mock_download):
        mock_download.return_value = b"BINARY"
        runner = CliRunner()

        with runner.isolated_filesystem():
            result = runner.invoke(cli, [
                "download", "sensor",
                "--platform", "linux", "--arch", "64",
            ])
            assert result.exit_code == 0
            assert os.path.exists("lc_sensor_64")

    @patch("limacharlie.commands.download.download_binary")
    def test_download_sensor_windows_msi(self, mock_download):
        mock_download.return_value = b"MSI_CONTENT"
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "sensor.msi")
            result = runner.invoke(cli, [
                "download", "sensor",
                "--platform", "windows", "--arch", "msi64",
                "-o", out_path,
            ])
            assert result.exit_code == 0
            assert os.path.exists(out_path)
            # MSI should NOT be marked executable
            mode = os.stat(out_path).st_mode
            assert not (mode & 0o111)

    @patch("limacharlie.commands.download.download_binary")
    def test_download_sensor_quiet_mode(self, mock_download):
        mock_download.return_value = b"BINARY"
        runner = CliRunner()

        with runner.isolated_filesystem():
            result = runner.invoke(cli, [
                "--quiet", "download", "sensor",
                "--platform", "linux", "--arch", "64",
            ])
            assert result.exit_code == 0
            # In quiet mode, no progress messages
            assert result.output == ""

    @patch("limacharlie.commands.download.download_binary")
    def test_download_sensor_chrome_no_arch_needed(self, mock_download):
        mock_download.return_value = b"CHROME_EXT"
        runner = CliRunner()

        with runner.isolated_filesystem():
            result = runner.invoke(cli, [
                "download", "sensor",
                "--platform", "chrome",
            ])
            assert result.exit_code == 0

        mock_download.assert_called_once_with("sensor", "chrome", "")

    @patch("limacharlie.commands.download.download_binary")
    def test_download_to_stdout(self, mock_download):
        mock_download.return_value = b"STDOUT_BINARY"
        runner = CliRunner()

        result = runner.invoke(cli, [
            "download", "sensor",
            "--platform", "linux", "--arch", "64",
            "-o", "-",
        ])
        assert result.exit_code == 0
