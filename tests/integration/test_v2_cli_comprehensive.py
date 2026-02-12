"""Comprehensive CLI integration tests for LimaCharlie CLI v2.

Tests all CLI command groups through Click's CliRunner, verifying that the
CLI layer (argument parsing, credential resolution, output formatting, exit
codes) works end-to-end against the live API.

Run with:
    pytest tests/integration/test_v2_cli_comprehensive.py \
        --oid <OID> --key <KEY> -v
"""

import json
import os
import sys
import time
import uuid

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from click.testing import CliRunner
from limacharlie.cli import cli

TEST_PREFIX = "test-cli-v2-"


def _unique(base=""):
    return f"{TEST_PREFIX}{base}{uuid.uuid4().hex[:8]}"


def _invoke(oid, key, args, expect_success=True):
    """Invoke the CLI with JSON output and return (result, parsed_json).

    Sets LC_API_KEY in the env and passes --oid and --output json as
    global options so that every command resolves credentials correctly.
    """
    runner = CliRunner(env={"LC_API_KEY": key})
    full_args = ["--oid", oid, "--output", "json"] + args
    catch = not expect_success
    result = runner.invoke(cli, full_args, catch_exceptions=catch)
    if expect_success:
        assert result.exit_code == 0, (
            f"CLI exited with {result.exit_code}.\n"
            f"args: {full_args}\n"
            f"output:\n{result.output}"
        )
    # Try to parse JSON from the output (some commands emit non-JSON text too)
    parsed = None
    output = result.output.strip()
    if output:
        # Some commands print a status line then JSON — try to find JSON
        for line in output.split("\n"):
            line = line.strip()
            if line.startswith("{") or line.startswith("["):
                try:
                    parsed = json.loads(line)
                    break
                except json.JSONDecodeError:
                    pass
        # If single-line JSON parsing failed, try the whole output
        if parsed is None:
            try:
                parsed = json.loads(output)
            except json.JSONDecodeError:
                pass
    return result, parsed


# ============================================================================
# Auth commands
# ============================================================================

class TestCliAuth:
    def test_whoami(self, oid, key):
        result, data = _invoke(oid, key, ["auth", "whoami"])
        assert data is not None
        assert isinstance(data, dict)

    def test_test(self, oid, key):
        runner = CliRunner(env={"LC_API_KEY": key})
        result = runner.invoke(cli, ["--oid", oid, "auth", "test"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "successful" in result.output.lower()

    def test_list_envs(self, oid, key):
        """list-envs should succeed (may return empty or list)."""
        runner = CliRunner(env={"LC_API_KEY": key})
        result = runner.invoke(cli, ["--oid", oid, "auth", "list-envs"], catch_exceptions=False)
        assert result.exit_code == 0


# ============================================================================
# Organization commands
# ============================================================================

class TestCliOrg:
    def test_info(self, oid, key):
        result, data = _invoke(oid, key, ["org", "info"])
        assert data is not None
        assert isinstance(data, dict)
        assert data.get("oid") == oid

    def test_urls(self, oid, key):
        result, data = _invoke(oid, key, ["org", "urls"])
        assert data is not None
        assert isinstance(data, dict)
        assert len(data) > 0

    def test_errors(self, oid, key):
        result, _ = _invoke(oid, key, ["org", "errors"])
        assert result.exit_code == 0

    def test_stats(self, oid, key):
        result, data = _invoke(oid, key, ["org", "stats"])
        assert data is not None
        assert isinstance(data, dict)

    def test_schema(self, oid, key):
        result, data = _invoke(oid, key, ["org", "schema"])
        assert data is not None
        assert isinstance(data, dict)

    def test_list(self, oid, key):
        """org list requires user credentials (not API key); verify it runs without crash."""
        result, data = _invoke(oid, key, ["org", "list"], expect_success=False)
        # With API key auth, this may fail since it requires user-level JWT.
        # We just verify the CLI doesn't crash unexpectedly.
        assert result.exit_code in (0, 1)


# ============================================================================
# Sensor commands (read-only — test org may have no sensors)
# ============================================================================

class TestCliSensor:
    def test_list(self, oid, key):
        result, _ = _invoke(oid, key, ["sensor", "list"])
        assert result.exit_code == 0


# ============================================================================
# Tag commands (read-only)
# ============================================================================

class TestCliTag:
    def test_list_org_tags(self, oid, key):
        result, _ = _invoke(oid, key, ["tag", "list"])
        assert result.exit_code == 0


# ============================================================================
# D&R Rule commands (CRUD)
# ============================================================================

class TestCliDR:
    def test_list(self, oid, key):
        result, data = _invoke(oid, key, ["dr", "list"])
        assert data is not None
        assert isinstance(data, dict)

    def test_crud(self, oid, key, tmp_path):
        name = _unique("rule-")
        rule_file = tmp_path / "rule.yaml"
        rule_file.write_text(json.dumps({
            "detect": {
                "op": "is",
                "event": "NEW_PROCESS",
                "path": "event/FILE_PATH",
                "value": "test-never-match.exe",
            },
            "respond": [{"action": "report", "name": name}],
        }))

        try:
            # Create via hive set
            result, _ = _invoke(oid, key, [
                "dr", "set", "--key", name,
                "--input-file", str(rule_file),
            ])
            assert result.exit_code == 0

            # Get
            result, data = _invoke(oid, key, ["dr", "get", "--key", name])
            assert data is not None

            # List and verify present
            result, data = _invoke(oid, key, ["dr", "list"])
            assert name in data
        finally:
            # Delete
            _invoke(oid, key, ["dr", "delete", "--key", name, "--confirm"])

        # Verify gone
        result, data = _invoke(oid, key, ["dr", "list"])
        assert name not in data

    def test_delete_without_confirm_fails(self, oid, key):
        """Deleting without --confirm should fail."""
        runner = CliRunner(env={"LC_API_KEY": key})
        result = runner.invoke(
            cli,
            ["--oid", oid, "dr", "delete", "--key", "nonexistent"],
        )
        # Should fail because --confirm is missing
        assert result.exit_code != 0


# ============================================================================
# False Positive commands (CRUD)
# ============================================================================

class TestCliFP:
    def test_list(self, oid, key):
        result, data = _invoke(oid, key, ["fp", "list"])
        assert data is not None
        assert isinstance(data, dict)

    def test_crud(self, oid, key, tmp_path):
        name = _unique("fp-")
        fp_file = tmp_path / "fp.yaml"
        fp_file.write_text(json.dumps({
            "op": "is",
            "path": "detect/event/FILE_PATH",
            "value": "test-never-match.exe",
        }))

        try:
            # Create via hive set
            result, _ = _invoke(oid, key, [
                "fp", "set", "--key", name, "--input-file", str(fp_file),
            ])
            assert result.exit_code == 0

            # Get
            result, data = _invoke(oid, key, ["fp", "get", "--key", name])
            assert data is not None

            # List and verify present
            result, data = _invoke(oid, key, ["fp", "list"])
            assert name in data
        finally:
            _invoke(oid, key, ["fp", "delete", "--key", name, "--confirm"])

        # Verify gone
        result, data = _invoke(oid, key, ["fp", "list"])
        assert name not in data


# ============================================================================
# Search commands
# ============================================================================

class TestCliSearch:
    def test_validate(self, oid, key):
        result, _ = _invoke(oid, key, [
            "search", "validate", "--query", "event_type = 'NEW_PROCESS'",
        ])
        assert result.exit_code == 0


# ============================================================================
# API Key commands (CRUD)
# ============================================================================

class TestCliApiKey:
    def test_list(self, oid, key):
        result, _ = _invoke(oid, key, ["api-key", "list"])
        assert result.exit_code == 0

    def test_crud(self, oid, key):
        name = _unique("apikey-")
        created_hash = None

        try:
            # Create
            result, data = _invoke(oid, key, [
                "api-key", "create", "--name", name, "--permissions", "org.get",
            ])
            assert result.exit_code == 0
            # Extract key hash from output for cleanup
            if data and isinstance(data, dict):
                created_hash = data.get("key_hash") or data.get("hash")

            # List — just verify it works after creation
            result, _ = _invoke(oid, key, ["api-key", "list"])
            assert result.exit_code == 0
        finally:
            if created_hash:
                _invoke(oid, key, [
                    "api-key", "delete", "--key-hash", created_hash, "--confirm",
                ])


# ============================================================================
# Installation Key commands (CRUD)
# ============================================================================

class TestCliInstallationKey:
    def test_list(self, oid, key):
        result, _ = _invoke(oid, key, ["installation-key", "list"])
        assert result.exit_code == 0

    def test_crud(self, oid, key):
        desc = _unique("instkey-")
        created_iid = None

        try:
            # Create
            result, data = _invoke(oid, key, [
                "installation-key", "create", "--description", desc,
            ])
            assert result.exit_code == 0
            if data and isinstance(data, dict):
                created_iid = data.get("iid")

            # List
            result, _ = _invoke(oid, key, ["installation-key", "list"])
            assert result.exit_code == 0
        finally:
            if created_iid:
                _invoke(oid, key, [
                    "installation-key", "delete", "--iid", created_iid, "--confirm",
                ])


# ============================================================================
# Ingestion Key commands (CRUD)
# ============================================================================

class TestCliIngestionKey:
    def test_list(self, oid, key):
        result, _ = _invoke(oid, key, ["ingestion-key", "list"])
        assert result.exit_code == 0

    def test_crud(self, oid, key):
        name = _unique("ingkey-")

        try:
            # Create
            result, _ = _invoke(oid, key, [
                "ingestion-key", "create", "--name", name,
            ])
            assert result.exit_code == 0

            # List
            result, _ = _invoke(oid, key, ["ingestion-key", "list"])
            assert result.exit_code == 0
        finally:
            _invoke(oid, key, [
                "ingestion-key", "delete", "--name", name, "--confirm",
            ])


# ============================================================================
# Secret commands (hive shortcut, CRUD)
# ============================================================================

class TestCliSecret:
    def test_list(self, oid, key):
        result, _ = _invoke(oid, key, ["secret", "list"], expect_success=False)
        # Secret hive requires secret.get.mtd permission which test key may lack.
        assert result.exit_code in (0, 1)

    def test_crud(self, oid, key, tmp_path):
        name = _unique("secret-")
        secret_file = tmp_path / "secret.json"
        secret_file.write_text(json.dumps({"data": {"value": "test-secret-data"}}))

        # Set — may fail due to missing permissions
        result, _ = _invoke(oid, key, [
            "secret", "set", "--key", name, "--input-file", str(secret_file),
        ], expect_success=False)
        if result.exit_code != 0:
            pytest.skip("secret hive requires secret.set permission")

        try:
            time.sleep(2)

            # Get
            result, data = _invoke(oid, key, ["secret", "get", "--key", name])
            assert result.exit_code == 0

            # List
            result, data = _invoke(oid, key, ["secret", "list"])
            assert result.exit_code == 0
            if isinstance(data, dict):
                assert name in data
        finally:
            _invoke(oid, key, ["secret", "delete", "--key", name, "--confirm"],
                    expect_success=False)


# ============================================================================
# Lookup commands (hive shortcut, CRUD)
# ============================================================================

class TestCliLookup:
    def test_list(self, oid, key):
        result, _ = _invoke(oid, key, ["lookup", "list"], expect_success=False)
        # Lookup hive requires lookup.get.mtd permission which test key may lack.
        assert result.exit_code in (0, 1)

    def test_crud(self, oid, key, tmp_path):
        name = _unique("lookup-")
        lookup_file = tmp_path / "lookup.json"
        lookup_file.write_text(json.dumps({"data": {"key1": "value1", "key2": "value2"}}))

        # Set — may fail due to missing permissions
        result, _ = _invoke(oid, key, [
            "lookup", "set", "--key", name, "--input-file", str(lookup_file),
        ], expect_success=False)
        if result.exit_code != 0:
            pytest.skip("lookup hive requires lookup.set permission")

        try:
            time.sleep(2)

            # Get
            result, data = _invoke(oid, key, ["lookup", "get", "--key", name])
            assert result.exit_code == 0

            # List
            result, data = _invoke(oid, key, ["lookup", "list"])
            assert result.exit_code == 0
            if isinstance(data, dict):
                assert name in data
        finally:
            _invoke(oid, key, ["lookup", "delete", "--key", name, "--confirm"],
                    expect_success=False)


# ============================================================================
# Output commands (CRUD)
# ============================================================================

class TestCliOutput:
    def test_list(self, oid, key):
        result, _ = _invoke(oid, key, ["output", "list"])
        assert result.exit_code == 0


# ============================================================================
# Billing commands
# ============================================================================

class TestCliBilling:
    def test_status(self, oid, key):
        result, data = _invoke(oid, key, ["billing", "status"])
        assert data is not None
        assert isinstance(data, dict)

    def test_plans(self, oid, key):
        """billing plans requires user auth; just verify it doesn't crash."""
        result, _ = _invoke(oid, key, ["billing", "plans"], expect_success=False)
        assert result.exit_code in (0, 1)

    def test_skus(self, oid, key):
        """billing skus may require user auth or not exist; verify no crash."""
        result, _ = _invoke(oid, key, ["billing", "skus"], expect_success=False)
        assert result.exit_code in (0, 1)


# ============================================================================
# User commands
# ============================================================================

class TestCliUser:
    def test_list(self, oid, key):
        result, _ = _invoke(oid, key, ["user", "list"])
        assert result.exit_code == 0

    def test_permissions_list(self, oid, key):
        result, _ = _invoke(oid, key, ["user", "permissions", "list"])
        assert result.exit_code == 0


# ============================================================================
# Group commands
# ============================================================================

class TestCliGroup:
    def test_list(self, oid, key):
        """group list requires user credentials; verify it doesn't crash."""
        result, _ = _invoke(oid, key, ["group", "list"], expect_success=False)
        assert result.exit_code in (0, 1)


# ============================================================================
# Extension commands
# ============================================================================

class TestCliExtension:
    def test_list(self, oid, key):
        result, _ = _invoke(oid, key, ["extension", "list"])
        assert result.exit_code == 0

    def test_list_available(self, oid, key):
        """list-available requires user auth; verify no crash."""
        result, _ = _invoke(oid, key, ["extension", "list-available"], expect_success=False)
        assert result.exit_code in (0, 1)

    def test_config_list(self, oid, key):
        """config-list may require specific permissions; verify no crash."""
        result, _ = _invoke(oid, key, ["extension", "config-list"], expect_success=False)
        assert result.exit_code in (0, 1)


# ============================================================================
# Artifact commands
# ============================================================================

class TestCliArtifact:
    def test_list(self, oid, key):
        result, _ = _invoke(oid, key, ["artifact", "list"])
        assert result.exit_code == 0


# ============================================================================
# Investigation commands (CRUD)
# ============================================================================

class TestCliInvestigation:
    def test_list(self, oid, key):
        result, _ = _invoke(oid, key, ["investigation", "list"], expect_success=False)
        # Investigation API may not be available for all orgs (404).
        assert result.exit_code in (0, 1)


# ============================================================================
# Integrity commands (CRUD)
# ============================================================================

class TestCliIntegrity:
    def test_list(self, oid, key):
        result, _ = _invoke(oid, key, ["integrity", "list"])
        assert result.exit_code == 0

    def test_crud(self, oid, key):
        name = _unique("integrity-")

        try:
            # Create
            result, _ = _invoke(oid, key, [
                "integrity", "create", "--name", name,
                "--patterns", "/tmp/test-cli-v2-*",
            ])
            assert result.exit_code == 0

            # List
            result, _ = _invoke(oid, key, ["integrity", "list"])
            assert result.exit_code == 0

            # Get
            result, _ = _invoke(oid, key, ["integrity", "get", "--name", name])
            assert result.exit_code == 0
        finally:
            _invoke(oid, key, [
                "integrity", "delete", "--name", name, "--confirm",
            ])


# ============================================================================
# Logging commands (CRUD)
# ============================================================================

class TestCliLogging:
    def test_list(self, oid, key):
        result, _ = _invoke(oid, key, ["logging", "list"])
        assert result.exit_code == 0

    def test_crud(self, oid, key):
        name = _unique("logging-")

        try:
            # Create
            result, _ = _invoke(oid, key, [
                "logging", "create", "--name", name, "--patterns", "*.exe",
            ])
            assert result.exit_code == 0

            # List
            result, _ = _invoke(oid, key, ["logging", "list"])
            assert result.exit_code == 0

            # Get
            result, _ = _invoke(oid, key, ["logging", "get", "--name", name])
            assert result.exit_code == 0
        finally:
            _invoke(oid, key, [
                "logging", "delete", "--name", name, "--confirm",
            ])


# ============================================================================
# YARA commands (read-only)
# ============================================================================

class TestCliYara:
    def test_rules_list(self, oid, key):
        result, _ = _invoke(oid, key, ["yara", "rules-list"])
        assert result.exit_code == 0

    def test_sources_list(self, oid, key):
        result, _ = _invoke(oid, key, ["yara", "sources-list"])
        assert result.exit_code == 0


# ============================================================================
# Job commands (read-only)
# ============================================================================

class TestCliJob:
    def test_list(self, oid, key):
        result, _ = _invoke(oid, key, ["job", "list"])
        assert result.exit_code == 0


# ============================================================================
# AI commands
# ============================================================================

class TestCliAI:
    def test_generate_rule(self, oid, key):
        """AI endpoints may not be available; verify no crash."""
        result, data = _invoke(oid, key, [
            "ai", "generate-rule", "--prompt", "detect any process named notepad.exe",
        ], expect_success=False)
        assert result.exit_code in (0, 1)

    def test_generate_query(self, oid, key):
        """AI endpoints may not be available; verify no crash."""
        result, data = _invoke(oid, key, [
            "ai", "generate-query", "--prompt", "find all DNS requests",
        ], expect_success=False)
        assert result.exit_code in (0, 1)


# ============================================================================
# Schema commands
# ============================================================================

class TestCliSchema:
    def test_list(self, oid, key):
        result, _ = _invoke(oid, key, ["schema", "list"])
        assert result.exit_code == 0


# ============================================================================
# Audit commands
# ============================================================================

class TestCliAudit:
    def test_list(self, oid, key):
        now = int(time.time())
        one_day_ago = now - 86400
        result, _ = _invoke(oid, key, [
            "audit", "list", "--start", str(one_day_ago), "--end", str(now),
        ])
        assert result.exit_code == 0


# ============================================================================
# Detection commands
# ============================================================================

class TestCliDetection:
    def test_list(self, oid, key):
        now = int(time.time())
        one_hour_ago = now - 3600
        result, _ = _invoke(oid, key, [
            "detection", "list", "--start", str(one_hour_ago), "--end", str(now),
        ])
        assert result.exit_code == 0


# ============================================================================
# Event commands (read-only, no sensor needed)
# ============================================================================

class TestCliEvent:
    def test_types(self, oid, key):
        result, _ = _invoke(oid, key, ["event", "types"])
        assert result.exit_code == 0


# ============================================================================
# Hive commands (CRUD via direct hive group)
# ============================================================================

class TestCliHive:
    def test_list(self, oid, key):
        """Hive list with secret requires secret.get.mtd; try fp instead."""
        result, _ = _invoke(oid, key, ["hive", "list", "--hive-name", "fp"])
        assert result.exit_code == 0


# ============================================================================
# Payload commands (read-only)
# ============================================================================

class TestCliPayload:
    def test_list(self, oid, key):
        result, _ = _invoke(oid, key, ["payload", "list"])
        assert result.exit_code == 0


# ============================================================================
# IOC commands
# ============================================================================

class TestCliIOC:
    def test_search(self, oid, key):
        result, _ = _invoke(oid, key, [
            "ioc", "search", "--type", "domain", "--value", "example.com",
        ])
        assert result.exit_code == 0

    def test_hosts(self, oid, key):
        result, _ = _invoke(oid, key, [
            "ioc", "hosts", "--hostname", "nonexistent-test-host-12345",
        ])
        assert result.exit_code == 0


# ============================================================================
# Sync commands (read-only fetch)
# ============================================================================

class TestCliSync:
    def test_pull(self, oid, key, tmp_path):
        config_file = tmp_path / "sync-config.yaml"
        result, _ = _invoke(oid, key, [
            "sync", "pull", "--config-file", str(config_file), "--rules",
        ])
        assert result.exit_code == 0
        assert config_file.exists()


# ============================================================================
# CLI global behavior
# ============================================================================

class TestCliGlobal:
    def test_help(self, oid, key):
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Usage" in result.output

    def test_version(self, oid, key):
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "2.0.0" in result.output

    def test_invalid_command(self, oid, key):
        runner = CliRunner(env={"LC_API_KEY": key})
        result = runner.invoke(cli, ["--oid", oid, "nonexistent-command"])
        assert result.exit_code != 0

    def test_quiet_mode_suppresses_output(self, oid, key):
        runner = CliRunner(env={"LC_API_KEY": key})
        result = runner.invoke(
            cli,
            ["--oid", oid, "--quiet", "auth", "test"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        # Quiet mode should suppress the "Authentication successful" message
        assert result.output.strip() == ""

    def test_json_output_is_valid_json(self, oid, key):
        """Verify --output json produces parseable JSON."""
        result, data = _invoke(oid, key, ["org", "info"])
        assert data is not None
        assert isinstance(data, dict)

    def test_explain_flag(self, oid, key):
        """Verify --explain prints help text and exits."""
        runner = CliRunner(env={"LC_API_KEY": key})
        result = runner.invoke(
            cli,
            ["--oid", oid, "dr", "list", "--explain"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert len(result.output) > 50  # Explain text should be substantial


# ============================================================================
# Exfil commands (CRUD)
# ============================================================================

class TestCliExfil:
    def test_list(self, oid, key):
        result, _ = _invoke(oid, key, ["exfil", "list"])
        assert result.exit_code == 0

    def test_event_crud(self, oid, key):
        name = _unique("exfil-")

        try:
            # Create event rule
            result, _ = _invoke(oid, key, [
                "exfil", "create-event", "--name", name,
                "--events", "DNS_REQUEST",
            ])
            assert result.exit_code == 0

            time.sleep(2)

            # List
            result, _ = _invoke(oid, key, ["exfil", "list"])
            assert result.exit_code == 0
        finally:
            _invoke(oid, key, [
                "exfil", "delete", "--name", name, "--confirm",
            ])
