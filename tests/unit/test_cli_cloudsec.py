"""Tests for limacharlie cloudsec CLI commands."""

import json

from unittest.mock import patch, MagicMock

from click.testing import CliRunner

from limacharlie.cli import cli


def _patches():
    return (
        patch("limacharlie.commands.cloudsec.Client"),
        patch("limacharlie.commands.cloudsec.Organization"),
        patch("limacharlie.commands.cloudsec.CloudSec"),
    )


def _invoke(args, mock_cs_cls, return_value=None, stdin=None):
    """Run the CLI with a mocked CloudSec instance."""
    inst = MagicMock()
    mock_cs_cls.return_value = inst
    if return_value is None:
        return_value = {"ok": True}
    # MagicMock: every SDK method returns the same renderable value.
    inst.configure_mock(**{
        f"{name}.return_value": return_value
        for name in [
            "get_overview", "list_changes", "get_risk_trend", "get_scan_status",
            "list_findings", "get_finding_facets", "get_finding",
            "set_finding_status", "bulk_set_finding_status",
            "set_finding_owner", "set_finding_ticket",
            "list_attack_paths", "get_public_access", "get_identity_facets",
            "list_inventory", "get_inventory_facets", "get_data_security_facets",
            "get_resource", "get_graph_neighbors", "list_queries", "run_query",
            "get_compliance", "list_compliance_frameworks",
            "list_compliance_assignments",
            "list_chokepoints", "dismiss_chokepoint", "restore_chokepoint",
            "resolve_sensors", "resolve_assets",
            "list_caasm_assets", "list_caasm_coverage",
            "get_caasm_policy", "set_caasm_policy", "caasm_ingest",
            "test_provider", "get_provider_manifests", "get_fleet_overview",
        ]
    })
    # CSV exports return raw text, not a JSON-renderable object.
    for name in [
        "export_findings_csv", "export_inventory_csv",
        "export_compliance_csv", "export_query_csv",
    ]:
        getattr(inst, name).return_value = "col_a,col_b\n1,2\n"
    runner = CliRunner()
    result = runner.invoke(cli, ["--output", "json"] + args, input=stdin)
    return result, inst


# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------


class TestCloudSecHelp:
    def test_root_help_lists_subcommands(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["cloudsec", "--help"])
        assert result.exit_code == 0
        for cmd in [
            "overview", "changes", "risk-trend", "scan-status", "fleet",
            "finding", "attack-path", "ciem", "inventory", "data-security",
            "resource", "graph", "query", "compliance", "chokepoint",
            "resolve", "caasm", "provider", "export",
        ]:
            assert cmd in result.output

    def test_finding_subgroup_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["cloudsec", "finding", "--help"])
        assert result.exit_code == 0
        for cmd in ["list", "facets", "get", "resolve", "bulk-resolve",
                    "set-owner", "set-ticket"]:
            assert cmd in result.output

    def test_caasm_subgroup_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["cloudsec", "caasm", "--help"])
        assert result.exit_code == 0
        for cmd in ["assets", "coverage", "policy", "ingest"]:
            assert cmd in result.output

    def test_caasm_policy_subgroup_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["cloudsec", "caasm", "policy", "--help"])
        assert result.exit_code == 0
        for cmd in ["get", "set"]:
            assert cmd in result.output

    def test_attack_path_subgroup_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["cloudsec", "attack-path", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output

    def test_ciem_subgroup_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["cloudsec", "ciem", "--help"])
        assert result.exit_code == 0
        for cmd in ["public-access", "facets"]:
            assert cmd in result.output

    def test_inventory_subgroup_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["cloudsec", "inventory", "--help"])
        assert result.exit_code == 0
        for cmd in ["list", "facets"]:
            assert cmd in result.output

    def test_data_security_subgroup_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["cloudsec", "data-security", "--help"])
        assert result.exit_code == 0
        assert "facets" in result.output

    def test_resource_subgroup_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["cloudsec", "resource", "--help"])
        assert result.exit_code == 0
        assert "get" in result.output

    def test_graph_subgroup_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["cloudsec", "graph", "--help"])
        assert result.exit_code == 0
        assert "neighbors" in result.output

    def test_query_subgroup_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["cloudsec", "query", "--help"])
        assert result.exit_code == 0
        for cmd in ["list", "run"]:
            assert cmd in result.output

    def test_compliance_subgroup_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["cloudsec", "compliance", "--help"])
        assert result.exit_code == 0
        for cmd in ["report", "frameworks", "assignments"]:
            assert cmd in result.output

    def test_chokepoint_subgroup_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["cloudsec", "chokepoint", "--help"])
        assert result.exit_code == 0
        for cmd in ["list", "dismiss", "restore"]:
            assert cmd in result.output

    def test_resolve_subgroup_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["cloudsec", "resolve", "--help"])
        assert result.exit_code == 0
        for cmd in ["sensors", "assets"]:
            assert cmd in result.output

    def test_provider_subgroup_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["cloudsec", "provider", "--help"])
        assert result.exit_code == 0
        assert "test" in result.output


# ---------------------------------------------------------------------------
# Top-level reads
# ---------------------------------------------------------------------------


class TestTopLevel:
    def test_overview(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "overview", "--trend-days", "90"], cls,
                return_value={"score": 42},
            )
            assert result.exit_code == 0, result.output
            inst.get_overview.assert_called_once_with(trend_days=90)

    def test_changes(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "changes", "--limit", "5"], cls,
                return_value={"changes": []},
            )
            assert result.exit_code == 0, result.output
            inst.list_changes.assert_called_once_with(limit=5)

    def test_scan_status_forwards_unlisted_provider(self):
        # The provider registry grows server-side; the CLI must not pin it.
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "scan-status", "--provider", "cloudflare"], cls,
                return_value={"status": {}},
            )
            assert result.exit_code == 0, result.output
            inst.get_scan_status.assert_called_once_with(provider="cloudflare")

    def test_scan_status_provider(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "scan-status", "--provider", "aws"], cls,
                return_value={"status": {}},
            )
            assert result.exit_code == 0, result.output
            inst.get_scan_status.assert_called_once_with(provider="aws")


# ---------------------------------------------------------------------------
# finding
# ---------------------------------------------------------------------------


class TestFindingCommands:
    def test_list_repeatable_filters(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                [
                    "cloudsec", "finding", "list",
                    "--severity", "CRITICAL", "--severity", "HIGH",
                    "--class", "toxic_combination",
                    "--kev", "--reachable",
                    "-q", "prod", "--limit", "50",
                ],
                cls,
                return_value={"findings": []},
            )
            assert result.exit_code == 0, result.output
            inst.list_findings.assert_called_once_with(
                severity=["CRITICAL", "HIGH"],
                finding_class=["toxic_combination"],
                status=None,
                account=None,
                reachable=True,
                kev=True,
                q="prod",
                sort=None,
                order=None,
                cursor=None,
                limit=50,
            )

    def test_list_no_kev_flag(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "finding", "list", "--no-kev"], cls,
                return_value={"findings": []},
            )
            assert result.exit_code == 0, result.output
            assert inst.list_findings.call_args[1]["kev"] is False

    def test_get(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "finding", "get", "fnd_abc"], cls,
                return_value={"finding": {}},
            )
            assert result.exit_code == 0, result.output
            inst.get_finding.assert_called_once_with("fnd_abc")

    def test_resolve(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                [
                    "cloudsec", "finding", "resolve", "fnd_abc",
                    "--kind", "accepted", "--reason", "known",
                    "--expires-at", "1767225600",
                ],
                cls,
            )
            assert result.exit_code == 0, result.output
            inst.set_finding_status.assert_called_once_with(
                "fnd_abc", "accepted", reason="known", expires_at=1767225600,
            )

    def test_resolve_requires_kind(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["cloudsec", "finding", "resolve", "fnd_abc"])
        assert result.exit_code != 0

    def test_resolve_rejects_bad_kind(self):
        runner = CliRunner()
        result = runner.invoke(
            cli, ["cloudsec", "finding", "resolve", "fnd_abc", "--kind", "wontfix"],
        )
        assert result.exit_code != 0

    def test_bulk_resolve_rejects_open(self):
        # The bulk API does not accept 'open' (reopen is single-finding only);
        # the CLI must reject it at parse time instead of a server error.
        runner = CliRunner()
        result = runner.invoke(
            cli, ["cloudsec", "finding", "bulk-resolve",
                  "--finding-id", "fnd_a", "--kind", "open"],
        )
        assert result.exit_code != 0
        assert "open" in result.output

    def test_bulk_resolve(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                [
                    "cloudsec", "finding", "bulk-resolve",
                    "--finding-id", "fnd_a", "--finding-id", "fnd_b",
                    "--kind", "mitigated",
                ],
                cls,
                return_value={"updated": 2},
            )
            assert result.exit_code == 0, result.output
            inst.bulk_set_finding_status.assert_called_once_with(
                ["fnd_a", "fnd_b"], "mitigated", reason=None, expires_at=None,
            )

    def test_set_owner(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "finding", "set-owner", "fnd_abc",
                 "--owner", "alice@corp.com"],
                cls,
            )
            assert result.exit_code == 0, result.output
            inst.set_finding_owner.assert_called_once_with("fnd_abc", "alice@corp.com")

    def test_set_owner_clear(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "finding", "set-owner", "fnd_abc", "--clear"], cls,
            )
            assert result.exit_code == 0, result.output
            inst.set_finding_owner.assert_called_once_with("fnd_abc", "")

    def test_set_owner_requires_exactly_one(self):
        runner = CliRunner()
        # Neither flag.
        result = runner.invoke(cli, ["cloudsec", "finding", "set-owner", "fnd_abc"])
        assert result.exit_code != 0
        # Both flags.
        result = runner.invoke(
            cli, ["cloudsec", "finding", "set-owner", "fnd_abc",
                  "--owner", "x", "--clear"],
        )
        assert result.exit_code != 0

    def test_set_ticket_clear(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "finding", "set-ticket", "fnd_abc", "--clear"], cls,
            )
            assert result.exit_code == 0, result.output
            inst.set_finding_ticket.assert_called_once_with("fnd_abc", "")


# ---------------------------------------------------------------------------
# graph / query
# ---------------------------------------------------------------------------


class TestGraphAndQuery:
    def test_neighbors(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "graph", "neighbors", "lcrn:x", "--limit", "500"],
                cls,
                return_value={"graph": {}},
            )
            assert result.exit_code == 0, result.output
            inst.get_graph_neighbors.assert_called_once_with("lcrn:x", limit=500)

    def test_query_run_named(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "query", "run", "--named", "public-buckets"], cls,
                return_value={"rows": []},
            )
            assert result.exit_code == 0, result.output
            inst.run_query.assert_called_once_with(
                named="public-buckets", text=None, query=None, project=None,
            )

    def test_query_run_dsl_with_project(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                [
                    "cloudsec", "query", "run",
                    "--query-json", '{"match": "x"}',
                    "--project", "a, b",
                ],
                cls,
                return_value={"rows": []},
            )
            assert result.exit_code == 0, result.output
            inst.run_query.assert_called_once_with(
                named=None, text=None, query={"match": "x"}, project=["a", "b"],
            )

    def test_query_run_requires_exactly_one_source(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["cloudsec", "query", "run"])
        assert result.exit_code != 0
        result = runner.invoke(
            cli, ["cloudsec", "query", "run", "--named", "n", "--text", "t"],
        )
        assert result.exit_code != 0

    def test_query_run_rejects_bad_json(self):
        runner = CliRunner()
        result = runner.invoke(
            cli, ["cloudsec", "query", "run", "--query-json", "{not json"],
        )
        assert result.exit_code != 0

    def test_query_run_rejects_null_json(self):
        # `--query-json null` parses to None and must not slip past the
        # object check into an empty POST body.
        runner = CliRunner()
        result = runner.invoke(
            cli, ["cloudsec", "query", "run", "--query-json", "null"],
        )
        assert result.exit_code != 0

    def test_query_run_rejects_empty_text(self):
        # An explicit empty string is not a query; fail client-side
        # instead of round-tripping to the server.
        runner = CliRunner()
        result = runner.invoke(
            cli, ["cloudsec", "query", "run", "--text", ""],
        )
        assert result.exit_code != 0

    def test_query_run_rejects_empty_alongside_real_option(self):
        # `--text foo --query-json ""` is an ambiguous invocation: the
        # empty option must not be silently ignored in favor of the other.
        runner = CliRunner()
        result = runner.invoke(
            cli, ["cloudsec", "query", "run", "--text", "foo", "--query-json", ""],
        )
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# resolve
# ---------------------------------------------------------------------------


class TestResolve:
    def test_sensors_bulk(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "resolve", "sensors", "sid-1", "sid-2"], cls,
                return_value={"resolved": []},
            )
            assert result.exit_code == 0, result.output
            inst.resolve_sensors.assert_called_once_with(["sid-1", "sid-2"])

    def test_sensors_requires_at_least_one(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["cloudsec", "resolve", "sensors"])
        assert result.exit_code != 0

    def test_assets(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "resolve", "assets", "lcrn:a"], cls,
                return_value={"resolved": []},
            )
            assert result.exit_code == 0, result.output
            inst.resolve_assets.assert_called_once_with(["lcrn:a"])


# ---------------------------------------------------------------------------
# caasm
# ---------------------------------------------------------------------------


class TestCaasm:
    def test_policy_set_from_json(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            policy = {"expect": [{"label": "edr", "capability": "edr",
                                  "kinds": ["device"]}]}
            result, inst = _invoke(
                ["cloudsec", "caasm", "policy", "set",
                 "--policy-json", json.dumps(policy)],
                cls,
            )
            assert result.exit_code == 0, result.output
            inst.set_caasm_policy.assert_called_once_with(policy)

    def test_policy_set_from_file(self, tmp_path):
        p1, p2, p3 = _patches()
        policy = {"expect": []}
        f = tmp_path / "policy.json"
        f.write_text(json.dumps(policy))
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "caasm", "policy", "set", "--input-file", str(f)],
                cls,
            )
            assert result.exit_code == 0, result.output
            inst.set_caasm_policy.assert_called_once_with(policy)

    def test_policy_set_from_yaml_file(self, tmp_path):
        p1, p2, p3 = _patches()
        f = tmp_path / "policy.yaml"
        f.write_text("expect:\n  - label: edr-on-devices\n    capability: edr\n    kinds: [device]\n")
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "caasm", "policy", "set", "--input-file", str(f)],
                cls,
            )
            assert result.exit_code == 0, result.output
            inst.set_caasm_policy.assert_called_once_with({
                "expect": [{"label": "edr-on-devices", "capability": "edr",
                            "kinds": ["device"]}],
            })

    def test_policy_set_from_stdin(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "caasm", "policy", "set"], cls,
                stdin='{"expect": []}',
            )
            assert result.exit_code == 0, result.output
            inst.set_caasm_policy.assert_called_once_with({"expect": []})

    def test_policy_set_requires_input(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["cloudsec", "caasm", "policy", "set"])
        assert result.exit_code != 0

    def test_policy_set_rejects_null_json(self):
        runner = CliRunner()
        result = runner.invoke(
            cli, ["cloudsec", "caasm", "policy", "set", "--policy-json", "null"],
        )
        assert result.exit_code != 0

    def test_policy_set_malformed_stdin_is_clean_error(self):
        # Piped input that is invalid YAML AND invalid JSON must produce
        # a usage error, not a raw json.JSONDecodeError traceback. (Note
        # '{[unclosed' fails both parsers; something like '{"a": }' is
        # VALID YAML — {'a': None} — and would proceed.)
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, _ = _invoke(
                ["cloudsec", "caasm", "policy", "set"], cls,
                stdin="{[unclosed",
            )
            assert result.exit_code != 0
            assert result.exception is None or isinstance(result.exception, SystemExit)
            assert "neither valid YAML nor JSON" in result.output

    def test_ingest_records_file(self, tmp_path):
        p1, p2, p3 = _patches()
        records = [{"id": "u1"}, {"id": "u2"}]
        f = tmp_path / "records.json"
        f.write_text(json.dumps(records))
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "caasm", "ingest", "--source", "okta",
                 "--records-file", str(f)],
                cls,
                return_value={"result": {}},
            )
            assert result.exit_code == 0, result.output
            inst.caasm_ingest.assert_called_once_with(
                "okta", records=records, record=None, policy=None,
            )

    def test_ingest_single_record(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "caasm", "ingest", "--source", "crowdstrike",
                 "--record-json", '{"device_id": "d1"}'],
                cls,
                return_value={"result": {}},
            )
            assert result.exit_code == 0, result.output
            inst.caasm_ingest.assert_called_once_with(
                "crowdstrike", records=None, record={"device_id": "d1"}, policy=None,
            )

    def test_ingest_forwards_unlisted_source(self):
        # The CAASM source registry grows server-side; the CLI must not pin it.
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "caasm", "ingest", "--source", "new-edr",
                 "--record-json", '{"id": "d1"}'],
                cls,
                return_value={"result": {}},
            )
            assert result.exit_code == 0, result.output
            inst.caasm_ingest.assert_called_once_with(
                "new-edr", records=None, record={"id": "d1"}, policy=None,
            )

    def test_ingest_rejects_non_array_records_file(self, tmp_path):
        f = tmp_path / "records.json"
        f.write_text('{"not": "an array"}')
        runner = CliRunner()
        result = runner.invoke(
            cli, ["cloudsec", "caasm", "ingest", "--source", "okta",
                  "--records-file", str(f)],
        )
        assert result.exit_code != 0

    def test_ingest_rejects_null_records_file(self, tmp_path):
        # A file whose JSON content is `null` must error, not silently
        # produce a records-less ingest.
        f = tmp_path / "records.json"
        f.write_text("null")
        runner = CliRunner()
        result = runner.invoke(
            cli, ["cloudsec", "caasm", "ingest", "--source", "okta",
                  "--records-file", str(f)],
        )
        assert result.exit_code != 0

    def test_ingest_rejects_null_record_json(self):
        runner = CliRunner()
        result = runner.invoke(
            cli, ["cloudsec", "caasm", "ingest", "--source", "okta",
                  "--record-json", "null"],
        )
        assert result.exit_code != 0

    def test_ingest_records_file_accepts_yaml(self, tmp_path):
        p1, p2, p3 = _patches()
        f = tmp_path / "records.yaml"
        f.write_text("- id: u1\n- id: u2\n")
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "caasm", "ingest", "--source", "okta",
                 "--records-file", str(f)],
                cls,
                return_value={"result": {}},
            )
            assert result.exit_code == 0, result.output
            inst.caasm_ingest.assert_called_once_with(
                "okta", records=[{"id": "u1"}, {"id": "u2"}], record=None, policy=None,
            )


# ---------------------------------------------------------------------------
# provider
# ---------------------------------------------------------------------------


class TestProvider:
    def test_test_from_file(self, tmp_path):
        p1, p2, p3 = _patches()
        provider = {"provider_type": "gcp", "credentials": "hive://secret/gcp-sa"}
        f = tmp_path / "provider.json"
        f.write_text(json.dumps(provider))
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "provider", "test", "--input-file", str(f)], cls,
                return_value={"supported": True, "report": {"ok": True}},
            )
            assert result.exit_code == 0, result.output
            inst.test_provider.assert_called_once_with(provider)

    def test_test_requires_input(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["cloudsec", "provider", "test"])
        assert result.exit_code != 0

    def test_test_rejects_non_object(self):
        runner = CliRunner()
        result = runner.invoke(
            cli, ["cloudsec", "provider", "test", "--provider-json", "[1,2]"],
        )
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# fleet
# ---------------------------------------------------------------------------


class TestFleet:
    def test_overview_defaults(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "fleet", "overview"], cls,
                return_value={"orgs": [], "next_cursor": ""},
            )
            assert result.exit_code == 0, result.output
            inst.get_fleet_overview.assert_called_once_with(
                oids=None, group=None, cursor=None, limit=None, trend_days=None,
            )

    def test_overview_selectors(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "fleet", "overview",
                 "--oid", "o1", "--oid", "o2", "--group", "g1",
                 "--trend-days", "90", "--limit", "50", "--cursor", "c1"], cls,
                return_value={"orgs": []},
            )
            assert result.exit_code == 0, result.output
            inst.get_fleet_overview.assert_called_once_with(
                oids=["o1", "o2"], group="g1", cursor="c1", limit=50,
                trend_days=90,
            )


# ---------------------------------------------------------------------------
# provider manifest
# ---------------------------------------------------------------------------


class TestProviderManifest:
    def test_manifest_all(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "provider", "manifest"], cls,
                return_value={"manifests": []},
            )
            assert result.exit_code == 0, result.output
            inst.get_provider_manifests.assert_called_once_with(provider_type=None)

    def test_manifest_single(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "provider", "manifest", "--type", "gcp"], cls,
                return_value={"manifest": {}},
            )
            assert result.exit_code == 0, result.output
            inst.get_provider_manifests.assert_called_once_with(provider_type="gcp")


# ---------------------------------------------------------------------------
# inventory --provider
# ---------------------------------------------------------------------------


class TestInventoryProvider:
    def test_list_forwards_provider(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "inventory", "list", "--provider", "okta"], cls,
                return_value={"resources": []},
            )
            assert result.exit_code == 0, result.output
            inst.list_inventory.assert_called_once_with(
                resource_type=None, provider="okta", account=None,
                region=None, q=None, cursor=None, limit=None,
            )


# ---------------------------------------------------------------------------
# export (CSV)
# ---------------------------------------------------------------------------


class TestExport:
    def test_export_findings_stdout(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "export", "findings",
                 "--severity", "CRITICAL", "--status", "open"], cls,
            )
            assert result.exit_code == 0, result.output
            # Raw CSV on stdout, NOT the JSON renderer.
            assert result.output == "col_a,col_b\n1,2\n"
            inst.export_findings_csv.assert_called_once_with(
                severity=["CRITICAL"], finding_class=None, status=["open"],
                account=None, reachable=None, kev=None, q=None,
                sort=None, order=None,
            )

    def test_export_findings_to_file(self, tmp_path):
        p1, p2, p3 = _patches()
        out = tmp_path / "findings.csv"
        with p1, p2, p3 as cls:
            result, _inst = _invoke(
                ["cloudsec", "export", "findings", "-o", str(out)], cls,
            )
            assert result.exit_code == 0, result.output
            assert out.read_text() == "col_a,col_b\n1,2\n"

    def test_export_inventory(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "export", "inventory", "--provider", "gcp",
                 "--type", "Bucket"], cls,
            )
            assert result.exit_code == 0, result.output
            inst.export_inventory_csv.assert_called_once_with(
                resource_type="Bucket", provider="gcp", account=None,
                region=None, q=None,
            )

    def test_export_compliance(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "export", "compliance", "--framework", "cis-aws"], cls,
            )
            assert result.exit_code == 0, result.output
            inst.export_compliance_csv.assert_called_once_with(
                framework="cis-aws", assignment=None,
            )

    def test_export_query_named(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "export", "query", "--named", "public-buckets"], cls,
            )
            assert result.exit_code == 0, result.output
            inst.export_query_csv.assert_called_once_with(
                named="public-buckets", text=None, query=None, project=None,
            )

    def test_export_query_requires_exactly_one(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["cloudsec", "export", "query"])
        assert result.exit_code != 0
        result = runner.invoke(
            cli, ["cloudsec", "export", "query", "--named", "a", "--text", "b"],
        )
        assert result.exit_code != 0
