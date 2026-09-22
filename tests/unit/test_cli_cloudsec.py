"""Tests for limacharlie cloudsec CLI commands."""

import json
import os
import subprocess

import pytest

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
            "get_topology", "get_free_tier",
            "list_findings", "get_finding_facets", "get_finding_classes",
            "get_finding", "list_finding_causes", "check_finding_runtime",
            "set_finding_status", "bulk_set_finding_status",
            "set_finding_owner", "set_finding_ticket",
            "list_attack_paths", "get_public_access", "get_identity_facets",
            "get_identity", "list_identity_access",
            "list_inventory", "get_inventory_facets", "get_data_security_facets",
            "list_data_stores",
            "get_resource", "get_graph_neighbors", "list_queries", "run_query",
            "get_compliance", "list_compliance_frameworks",
            "list_compliance_assignments",
            "list_chokepoints", "dismiss_chokepoint", "restore_chokepoint",
            "resolve_sensors", "resolve_assets",
            "list_caasm_assets", "list_caasm_coverage",
            "get_caasm_policy", "set_caasm_policy", "caasm_ingest",
            "test_provider", "get_provider_manifests", "get_fleet_overview",
            "get_policy_vocabulary", "suggest_policy_values",
            "simulate_resource_match", "simulate_finding_match",
            "list_code_repos", "get_code_status", "get_code_sbom",
            "rescan_code_repo", "autofix_code_finding",
            "ingest_code_results", "push_code_provenance", "list_code_provenance",
            "get_code_capabilities", "get_code_fixes", "iter_code_fixes",
            "check_pull_request", "configure_code_webhook",
            "list_image_repos", "iter_image_repos", "get_image_repo_facets",
            "list_container_images", "iter_container_images",
            "get_container_image",
            "create_compliance_run", "list_compliance_runs",
            "list_compliance_attestations", "create_compliance_attestation",
            "list_compliance_events", "export_compliance_run",
            "list_compliance_schedules", "set_compliance_schedule",
            "get_azure_scope_hierarchy",
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
            "overview", "changes", "risk-trend", "scan-status", "topology",
            "free-tier", "fleet", "finding", "attack-path", "ciem", "inventory",
            "data-security", "resource", "graph", "query", "compliance",
            "chokepoint", "resolve", "caasm", "code", "provider", "policy",
            "simulate", "export",
        ]:
            assert cmd in result.output

    def test_finding_subgroup_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["cloudsec", "finding", "--help"])
        assert result.exit_code == 0
        for cmd in ["list", "facets", "causes", "classes", "get", "runtime-check",
                    "resolve", "bulk-resolve", "set-owner", "set-ticket"]:
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
        # Asserted against the registered command NAMES, not the help text:
        # "identity" is a substring of "identities", so a substring check
        # could not tell the singular point-lookup from the plural list.
        group = cli.commands["cloudsec"].commands["ciem"]
        assert set(group.commands) == {
            "public-access", "facets", "identity", "identities",
        }

    def test_policy_subgroup_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["cloudsec", "policy", "--help"])
        assert result.exit_code == 0
        for cmd in ["vocabulary", "suggest"]:
            assert cmd in result.output

    def test_simulate_subgroup_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["cloudsec", "simulate", "--help"])
        assert result.exit_code == 0
        for cmd in ["resources", "findings"]:
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
        for cmd in ["facets", "stores"]:
            assert cmd in result.output

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
    def test_source_selector_forwards_on_list_and_facets(self):
        """--source reaches BOTH routes, because a rail whose counts are
        filtered differently from the list beside it is worse than no rail.
        """
        for argv, method in [
            (["cloudsec", "finding", "list", "--source", "hosted"], "list_findings"),
            (["cloudsec", "finding", "facets", "--source", "ingest"], "get_finding_facets"),
        ]:
            p1, p2, p3 = _patches()
            with p1, p2, p3 as cls:
                result, inst = _invoke(argv, cls, return_value={"findings": []})
                assert result.exit_code == 0, result.output
                kwargs = getattr(inst, method).call_args.kwargs
                assert kwargs["source"] == argv[-1], f"{method} got {kwargs['source']!r}"

    def test_source_omitted_is_unconstrained(self):
        """No --source must send None, not a value the backend would read as
        an unrecognised producer and match nothing against.
        """
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "finding", "list"], cls, return_value={"findings": []},
            )
            assert result.exit_code == 0, result.output
            assert inst.list_findings.call_args.kwargs["source"] is None

    def test_source_rejects_a_value_outside_the_vocabulary(self):
        """The vocabulary is CLOSED and the failure is local.

        The gateway forwards an unknown value verbatim on purpose (so it can
        never widen the read), which means a typo would come back as an empty
        worklist after a round trip. Click can tell the caller what the four
        words are before that happens, so it does.
        """
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "finding", "list", "--source", "hosetd"], cls,
                return_value={"findings": []},
            )
            assert result.exit_code != 0
            assert "hosetd" in result.output
            inst.list_findings.assert_not_called()

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
                has_iac_origin=None, iac_attribution=None,
                severity=["CRITICAL", "HIGH"],
                finding_class=["toxic_combination"],
                status=None,
                account=None,
                repo=None,
                image_urn=None,
                fix_state=None,
                exploit_band=None,
                grain=None,
                cause=None,
                source=None,
                owner=None,
                sla=None,
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
                ["cloudsec", "query", "run", "--named", "public_data_stores"], cls,
                return_value={"rows": []},
            )
            assert result.exit_code == 0, result.output
            inst.run_query.assert_called_once_with(
                named="public_data_stores", text=None, query=None, project=None,
            )

    def test_query_run_dsl_with_project(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                [
                    "cloudsec", "query", "run",
                    "--query-json", '{"match": "x"}',
                    "--project", "graph",
                ],
                cls,
                return_value={"rows": []},
            )
            assert result.exit_code == 0, result.output
            inst.run_query.assert_called_once_with(
                named=None, text=None, query={"match": "x"}, project="graph",
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

    def test_test_with_a_gitlab_record(self):
        """The gitlab_namespace/credentials shape flows through untouched —
        this command is provider-agnostic, so a GitLab record needs no
        special handling to already work."""
        p1, p2, p3 = _patches()
        provider = {
            "provider_type": "gitlab",
            "gitlab_namespace": "acme/platform",
            "credentials": "hive://secret/gitlab-token",
        }
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "provider", "test", "--provider-json", json.dumps(provider)],
                cls, return_value={"supported": True, "report": {"ok": True}},
            )
            assert result.exit_code == 0, result.output
            inst.test_provider.assert_called_once_with(provider)

    def test_test_with_a_bitbucket_record(self):
        p1, p2, p3 = _patches()
        provider = {
            "provider_type": "bitbucket",
            "bitbucket_workspace": "acme",
            "credentials": "hive://secret/bitbucket-token",
        }
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "provider", "test", "--provider-json", json.dumps(provider)],
                cls, return_value={"supported": True, "report": {"ok": True}},
            )
            assert result.exit_code == 0, result.output
            inst.test_provider.assert_called_once_with(provider)

    def test_explain_documents_gitlab_and_bitbucket_record_shapes(self):
        """The ticket this parity work closes found gitlab/bitbucket
        connections undiscoverable from the CLI: 'hive set --hive-name
        cloudsec_provider' always worked for them, but nothing in the CLI's
        own text said what fields to send or that GitLab additionally needs
        group-level (not per-project) access. Pin that text so it cannot
        silently rot back to undiscoverable, and pin the CURRENT rule
        (a broad token is accepted; only a missing scope is refused) rather
        than the reverted one."""
        from limacharlie.discovery import get_explain

        explain = get_explain("cloudsec.provider.test") or ""
        assert "gitlab_namespace" in explain
        assert "bitbucket_workspace" in explain
        assert "Reporter" in explain, "the group-level membership requirement must be named"
        assert "namespace_membership" in explain
        assert "MISSING" in explain and "accepted" in explain, (
            "must describe the CURRENT rule (broad token accepted, missing scope "
            "refused) and not the reverted ceiling-refusal rule"
        )


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
                has_iac_origin=None,
                resource_type=None, provider="okta", account=None,
                region=None, q=None, account_empty=None,
                cursor=None, limit=None,
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
                has_iac_origin=None, iac_attribution=None,
                severity=["CRITICAL"], finding_class=None, status=["open"],
                account=None, repo=None, image_urn=None, fix_state=None,
                exploit_band=None, grain=None, cause=None,
                source=None, owner=None, sla=None,
                reachable=None, kev=None, q=None, sort=None, order=None,
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
                has_iac_origin=None,
                resource_type="Bucket", provider="gcp", account=None,
                region=None, q=None, account_empty=None,
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
                ["cloudsec", "export", "query", "--named", "public_data_stores"], cls,
            )
            assert result.exit_code == 0, result.output
            inst.export_query_csv.assert_called_once_with(
                named="public_data_stores", text=None, query=None, project=None,
            )

    def test_export_query_requires_exactly_one(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["cloudsec", "export", "query"])
        assert result.exit_code != 0
        result = runner.invoke(
            cli, ["cloudsec", "export", "query", "--named", "a", "--text", "b"],
        )
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# 2026-07 additions: topology, finding classes, ciem identity, policy,
# simulate, inventory --all-accounts
# ---------------------------------------------------------------------------


class TestTopologyAndClasses:
    def test_topology(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "topology"], cls,
                return_value={"available": True, "scopes": [], "edges": []},
            )
            assert result.exit_code == 0, result.output
            inst.get_topology.assert_called_once_with()

    def test_finding_classes(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "finding", "classes"], cls,
                return_value={"classes": ["misconfig"]},
            )
            assert result.exit_code == 0, result.output
            inst.get_finding_classes.assert_called_once_with()


class TestCiemIdentity:
    def test_ciem_identity(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "ciem", "identity", "lcrn:x"], cls,
                return_value={"identity": {"urn": "lcrn:x"}},
            )
            assert result.exit_code == 0, result.output
            inst.get_identity.assert_called_once_with("lcrn:x")


class TestInventoryAllAccounts:
    def test_list_all_accounts_flag(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "inventory", "list", "--all-accounts"], cls,
                return_value={"resources": []},
            )
            assert result.exit_code == 0, result.output
            inst.list_inventory.assert_called_once_with(
                has_iac_origin=None,
                resource_type=None, provider=None, account=None,
                region=None, q=None, account_empty=None,
                cursor=None, limit=None,
            )

    def test_list_account_empty_flag(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "inventory", "list", "--account-empty"], cls,
                return_value={"resources": []},
            )
            assert result.exit_code == 0, result.output
            inst.list_inventory.assert_called_once_with(
                has_iac_origin=None,
                resource_type=None, provider=None, account=None,
                region=None, q=None, account_empty=True,
                cursor=None, limit=None,
            )

    def test_list_default_omits_account_empty(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "inventory", "list"], cls,
                return_value={"resources": []},
            )
            assert result.exit_code == 0, result.output
            _, kwargs = inst.list_inventory.call_args
            # The default must not forward a falsey account_empty.
            assert kwargs["account_empty"] is None

    def test_export_all_accounts_flag(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "export", "inventory", "--all-accounts"], cls,
            )
            assert result.exit_code == 0, result.output
            inst.export_inventory_csv.assert_called_once_with(
                has_iac_origin=None,
                resource_type=None, provider=None, account=None,
                region=None, q=None, account_empty=None,
            )

    def test_export_account_empty_flag(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "export", "inventory", "--account-empty"], cls,
            )
            assert result.exit_code == 0, result.output
            inst.export_inventory_csv.assert_called_once_with(
                has_iac_origin=None,
                resource_type=None, provider=None, account=None,
                region=None, q=None, account_empty=True,
            )

    def test_account_scope_flags_are_mutually_exclusive(self):
        runner = CliRunner()
        for args in [
            ["--account", "project-1", "--all-accounts"],
            ["--account", "project-1", "--account-empty"],
            ["--all-accounts", "--account-empty"],
        ]:
            result = runner.invoke(cli, ["cloudsec", "inventory", "list", *args])
            assert result.exit_code != 0
            assert "mutually exclusive" in result.output


class TestPolicy:
    def test_vocabulary(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "policy", "vocabulary"], cls,
                return_value={"surfaces": {}},
            )
            assert result.exit_code == 0, result.output
            inst.get_policy_vocabulary.assert_called_once_with()

    def test_suggest(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "policy", "suggest", "--dimension", "name",
                 "-q", "prod", "--target", "data_store", "--limit", "10"], cls,
                return_value={"values": []},
            )
            assert result.exit_code == 0, result.output
            inst.suggest_policy_values.assert_called_once_with(
                "name", "prod", target="data_store", limit=10,
            )

    def test_suggest_requires_dimension_and_q(self):
        runner = CliRunner()
        # missing --q
        result = runner.invoke(
            cli, ["cloudsec", "policy", "suggest", "--dimension", "name"],
        )
        assert result.exit_code != 0
        # invalid dimension is rejected by the Choice up front
        result = runner.invoke(
            cli, ["cloudsec", "policy", "suggest",
                  "--dimension", "bogus", "-q", "x"],
        )
        assert result.exit_code != 0


class TestSimulate:
    def test_resources_inline(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "simulate", "resources",
                 "--rules-json", '[{"name_glob": "prod-*"}]',
                 "--target", "data_store",
                 "--surface", "classification.data_stores",
                 "--resource-type", "DataStore",
                 "--sample-limit", "10"], cls,
                return_value={"evaluated": 1, "matched": 1},
            )
            assert result.exit_code == 0, result.output
            inst.simulate_resource_match.assert_called_once_with(
                [{"name_glob": "prod-*"}], target="data_store",
                surface="classification.data_stores",
                resource_types=["DataStore"], sample_limit=10,
            )

    def test_resources_from_stdin(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "simulate", "resources"], cls,
                return_value={"evaluated": 0, "matched": 0},
                stdin='[{"account_glob": "*prod*"}]',
            )
            assert result.exit_code == 0, result.output
            inst.simulate_resource_match.assert_called_once_with(
                [{"account_glob": "*prod*"}], target=None,
                surface=None, resource_types=None, sample_limit=None,
            )

    def test_resources_rejects_non_array(self):
        runner = CliRunner()
        result = runner.invoke(
            cli, ["cloudsec", "simulate", "resources",
                  "--rules-json", '{"name_glob": "x"}'],
        )
        assert result.exit_code != 0

    def test_findings_inline(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "simulate", "findings",
                 "--match-json", '{"finding_class": "misconfig"}',
                 "--sample-limit", "5"], cls,
                return_value={"evaluated": 3, "matched": 2},
            )
            assert result.exit_code == 0, result.output
            inst.simulate_finding_match.assert_called_once_with(
                {"finding_class": "misconfig"}, sample_limit=5,
            )

    def test_findings_empty_match_allowed(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "simulate", "findings", "--match-json", "{}"], cls,
                return_value={"evaluated": 9, "matched": 9},
            )
            assert result.exit_code == 0, result.output
            inst.simulate_finding_match.assert_called_once_with(
                {}, sample_limit=None,
            )


class TestFindingOwnerSelector:
    def test_owner_and_unassigned_ride_one_selector(self):
        # "mine or nobody's" is ONE repeatable filter with two values, and
        # the unassigned bucket travels as the empty string.
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "finding", "list",
                 "--owner", "alice@corp.com", "--unassigned"], cls,
                return_value={"findings": []},
            )
            assert result.exit_code == 0, result.output
            assert inst.list_findings.call_args[1]["owner"] == [
                "alice@corp.com", "",
            ]

    def test_unassigned_alone_selects_the_empty_owner(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "finding", "list", "--unassigned"], cls,
                return_value={"findings": []},
            )
            assert result.exit_code == 0, result.output
            assert inst.list_findings.call_args[1]["owner"] == [""]

    def test_no_owner_flags_send_no_constraint(self):
        # An empty selector must be None, not [] — [""] would silently
        # narrow the read to the untriaged bucket.
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "finding", "list"], cls,
                return_value={"findings": []},
            )
            assert result.exit_code == 0, result.output
            assert inst.list_findings.call_args[1]["owner"] is None

    def test_sla_filter_reaches_every_findings_surface(self):
        # --sla rides the shared filter decorator, so it must reach ALL FOUR
        # commands that decorator feeds. A surface that silently drops it
        # returns the unfiltered estate while the caller believes they asked
        # for the overdue slice.
        for argv, method, extra in (
            (["cloudsec", "finding", "list", "--sla", "breached"],
             "list_findings", {"findings": []}),
            (["cloudsec", "finding", "facets", "--sla", "breached"],
             "get_finding_facets", {"facets": {}}),
            (["cloudsec", "finding", "causes", "--sla", "breached"],
             "list_finding_causes", {"causes": [], "distinct": 0}),
            (["cloudsec", "export", "findings", "--sla", "breached"],
             "export_findings_csv", None),
        ):
            p1, p2, p3 = _patches()
            with p1, p2, p3 as cls:
                if extra is None:
                    result, inst = _invoke(argv, cls)
                else:
                    result, inst = _invoke(argv, cls, return_value=extra)
                assert result.exit_code == 0, result.output
                got = getattr(inst, method).call_args[1]["sla"]
                assert got == ["breached"], f"{method} got sla={got!r}"

    def test_sla_is_repeatable_and_absent_by_default(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "finding", "list",
                 "--sla", "breached", "--sla", "due_soon"],
                cls, return_value={"findings": []},
            )
            assert result.exit_code == 0, result.output
            assert inst.list_findings.call_args[1]["sla"] == ["breached", "due_soon"]

        # Unset must be None, not [] — an empty list would be forwarded as a
        # present-but-empty selection.
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "finding", "list"], cls,
                return_value={"findings": []},
            )
            assert result.exit_code == 0, result.output
            assert inst.list_findings.call_args[1]["sla"] is None

    def test_sort_due_at_forwards(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "finding", "list", "--sort", "due_at"], cls,
                return_value={"findings": []},
            )
            assert result.exit_code == 0, result.output
            assert inst.list_findings.call_args[1]["sort"] == "due_at"

    def test_facets_owner_pin_is_separate_from_the_filter(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "finding", "facets",
                 "--owner-pin", "me@corp.com", "--owner-pin", "bob@corp.com"],
                cls, return_value={"facets": {}},
            )
            assert result.exit_code == 0, result.output
            kwargs = inst.get_finding_facets.call_args[1]
            assert kwargs["owner_pin"] == ["me@corp.com", "bob@corp.com"]
            # A pin selects nothing: the owner FILTER stays unset.
            assert kwargs["owner"] is None

    def test_export_findings_takes_the_owner_filter(self):
        # The export must be the same filtered set the list shows.
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "export", "findings", "--owner", "alice@corp.com"],
                cls,
            )
            assert result.exit_code == 0, result.output
            assert inst.export_findings_csv.call_args[1]["owner"] == [
                "alice@corp.com",
            ]


class TestFindingCauses:
    def test_causes_rollup_with_filters(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "finding", "causes",
                 "--severity", "CRITICAL", "--limit", "5"], cls,
                return_value={"causes": [], "distinct": 0},
            )
            assert result.exit_code == 0, result.output
            inst.list_finding_causes.assert_called_once_with(
                has_iac_origin=None, iac_attribution=None,
                cause=None,
                severity=["CRITICAL"],
                finding_class=None,
                status=None,
                account=None,
                repo=None,
                image_urn=None,
                fix_state=None,
                exploit_band=None,
                grain=None,
                source=None,
                owner=None,
                sla=None,
                reachable=None,
                kev=None,
                q=None,
                limit=5,
            )

    def test_causes_single_cause(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "finding", "causes", "--cause", "lcrn:fw"], cls,
                return_value={"causes": [{"key": "lcrn:fw", "count": 22}],
                              "distinct": 1},
            )
            assert result.exit_code == 0, result.output
            assert inst.list_finding_causes.call_args[1]["cause"] == "lcrn:fw"


class TestCiemIdentities:
    def test_identities_full_cross_filter(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "ciem", "identities",
                 "--source", "okta", "--source", "gcp",
                 "--account", "proj-1", "--region", "us-central1",
                 "--kind", "service_account", "--criticality", "critical",
                 "--risk-band", "critical", "--mfa", "off",
                 "--admin", "--no-external", "--can-escalate",
                 "--with-sensitive", "-q", "deploy",
                 "--limit", "50", "--cursor", "c1"], cls,
                return_value={"principals": [], "next_cursor": None},
            )
            assert result.exit_code == 0, result.output
            inst.list_identity_access.assert_called_once_with(
                source=["okta", "gcp"],
                account=["proj-1"],
                region=["us-central1"],
                kind=["service_account"],
                criticality=["critical"],
                risk_band=["critical"],
                mfa="off",
                admin=True,
                external=False,
                public=None,
                disabled=None,
                crown_jewel=None,
                can_escalate=True,
                dormant_90d=None,
                with_sensitive=True,
                q="deploy",
                cursor="c1",
                limit=50,
            )

    def test_identities_unset_booleans_are_none_not_false(self):
        # Tri-state: an omitted flag must leave the dimension
        # unconstrained rather than pinning it to false.
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "ciem", "identities"], cls,
                return_value={"principals": []},
            )
            assert result.exit_code == 0, result.output
            kwargs = inst.list_identity_access.call_args[1]
            for key in ["admin", "external", "public", "disabled",
                        "crown_jewel", "can_escalate", "dormant_90d",
                        "with_sensitive", "mfa"]:
                assert kwargs[key] is None, key

    def test_facets_take_the_same_cross_filter(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "ciem", "facets",
                 "--kind", "user", "--mfa", "unknown"], cls,
                return_value={"facets": {}},
            )
            assert result.exit_code == 0, result.output
            kwargs = inst.get_identity_facets.call_args[1]
            assert kwargs["kind"] == ["user"]
            assert kwargs["mfa"] == "unknown"


class TestDataSecurityStores:
    def test_stores_full_cross_filter(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "data-security", "stores",
                 "--provider", "gcp", "--account", "proj-1",
                 "--region", "us-central1", "--store-kind", "bucket",
                 "--tier", "critical", "--data-class", "pii",
                 "--sensitive", "--no-public", "-q", "prod",
                 "--limit", "50"], cls,
                return_value={"stores": [], "next_cursor": ""},
            )
            assert result.exit_code == 0, result.output
            inst.list_data_stores.assert_called_once_with(
                provider=["gcp"],
                account=["proj-1"],
                region=["us-central1"],
                store_kind=["bucket"],
                tier=["critical"],
                data_class=["pii"],
                sensitivity=True,
                exposure=False,
                q="prod",
                cursor=None,
                limit=50,
            )

    def test_stores_unset_tristates_are_none(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "data-security", "stores"], cls,
                return_value={"stores": []},
            )
            assert result.exit_code == 0, result.output
            kwargs = inst.list_data_stores.call_args[1]
            assert kwargs["sensitivity"] is None
            assert kwargs["exposure"] is None

    def test_facets_take_the_same_cross_filter(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "data-security", "facets",
                 "--store-kind", "bucket", "--public"], cls,
                return_value={"facets": {}},
            )
            assert result.exit_code == 0, result.output
            kwargs = inst.get_data_security_facets.call_args[1]
            assert kwargs["store_kind"] == ["bucket"]
            assert kwargs["exposure"] is True


class TestFreeTier:
    def test_free_tier(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "free-tier"], cls,
                return_value={"is_free_tier": True, "sensor_quota": 2,
                              "max_providers": 2, "enabled_providers": 1},
            )
            assert result.exit_code == 0, result.output
            inst.get_free_tier.assert_called_once_with()
            assert "is_free_tier" in result.output


class TestClosedVocabularyGuards:
    """The closed server vocabularies fail CLOSED, so a typo must not parse.

    An unrecognized risk band contributes a FALSE predicate and a
    misspelled tier matches no row, so without validation a typo would
    exit 0 with an empty result under a filter the user can see applied.

    Each assertion pins the PARSE failure (exit 2 + click's "Invalid value
    for '--flag'"), not merely a non-zero exit: these run unmocked, so an
    accepted value also exits non-zero once it reaches the credential-less
    client, and `exit_code != 0` alone would pass with the Choice removed.
    """

    def _rejects(self, args, flag):
        runner = CliRunner()
        result = runner.invoke(cli, args)
        assert result.exit_code == 2, result.output
        assert f"Invalid value for {flag!r}" in result.output, result.output

    def test_rejects_unknown_risk_band(self):
        self._rejects(
            ["cloudsec", "ciem", "identities", "--risk-band", "urgent"],
            "--risk-band",
        )

    def test_rejects_unknown_criticality_tier(self):
        self._rejects(
            ["cloudsec", "ciem", "identities", "--criticality", "tier1"],
            "--criticality",
        )

    def test_rejects_unknown_store_tier(self):
        self._rejects(
            ["cloudsec", "data-security", "stores", "--tier", "tier1"],
            "--tier",
        )

    def test_rejects_unknown_mfa_state_by_parse_failure(self):
        # Replaces an earlier --mfa guard that asserted only a non-zero exit,
        # which an accepted value also produces without credentials: that one
        # survived deleting the Choice, so it was not testing anything.
        self._rejects(
            ["cloudsec", "ciem", "identities", "--mfa", "maybe"], "--mfa",
        )

    def test_unclassified_identities_selects_the_empty_tier(self):
        # "no tier assigned" is the EMPTY value on the wire, and it
        # combines with a named tier like --unassigned does for owner.
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "ciem", "identities",
                 "--criticality", "critical", "--unclassified"], cls,
                return_value={"principals": []},
            )
            assert result.exit_code == 0, result.output
            assert inst.list_identity_access.call_args[1]["criticality"] == [
                "critical", "",
            ]

    def test_unclassified_stores_selects_the_empty_tier(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "data-security", "stores", "--unclassified"], cls,
                return_value={"stores": []},
            )
            assert result.exit_code == 0, result.output
            assert inst.list_data_stores.call_args[1]["tier"] == [""]

    def test_no_tier_flags_send_no_constraint(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "data-security", "stores"], cls,
                return_value={"stores": []},
            )
            assert result.exit_code == 0, result.output
            assert inst.list_data_stores.call_args[1]["tier"] is None


# ---------------------------------------------------------------------------
# code subgroup (AppSec code lane)
# ---------------------------------------------------------------------------


class TestCloudSecCode:
    def test_code_subgroup_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["cloudsec", "code", "--help"])
        assert result.exit_code == 0
        for cmd in ["repos", "status", "sbom", "ingest", "scan"]:
            assert cmd in result.output

    def test_code_repos(self):
        with _patches()[0], _patches()[1], _patches()[2] as cs_cls:
            result, inst = _invoke(
                ["cloudsec", "code", "repos", "-q", "fixtures",
                 "--with-findings", "--provider", "github", "--limit", "50"],
                cs_cls, {"repos": [], "next_cursor": ""})
            assert result.exit_code == 0
            inst.list_code_repos.assert_called_once()
            kwargs = inst.list_code_repos.call_args.kwargs
            assert kwargs["q"] == "fixtures"
            assert kwargs["has_findings"] is True
            assert kwargs["provider"] == "github"
            assert kwargs["limit"] == 50

    def test_code_repos_without_findings_is_a_selection(self):
        """--without-findings must reach the SDK as False, not as None."""
        with _patches()[0], _patches()[1], _patches()[2] as cs_cls:
            result, inst = _invoke(
                ["cloudsec", "code", "repos", "--without-findings"],
                cs_cls, {"repos": []})
            assert result.exit_code == 0
            assert inst.list_code_repos.call_args.kwargs["has_findings"] is False

    def test_code_ingest_reads_the_file_and_pushes_it(self, tmp_path):
        doc = tmp_path / "trivy.sarif"
        doc.write_bytes(b'{"version":"2.1.0","runs":[]}')
        with _patches()[0], _patches()[1], _patches()[2] as cs_cls:
            result, inst = _invoke(
                ["cloudsec", "code", "ingest", "--repo", "acme/api",
                 "--source", "sarif", "-f", str(doc), "--commit", "c0ffee"],
                cs_cls, {"result": {}})
            assert result.exit_code == 0, result.output
            inst.ingest_code_results.assert_called_once()
            args, kwargs = inst.ingest_code_results.call_args
            assert args[0] == "acme/api"
            assert args[1] == "sarif"
            assert args[2] == b'{"version":"2.1.0","runs":[]}'
            assert kwargs["commit"] == "c0ffee"

    def test_scanner_succeeded_records_the_evidence_that_lets_a_sarif_close(self, tmp_path):
        """A SARIF closes findings it previously reported only if it proves its run
        succeeded (SARIF's own invocations[].executionSuccessful). Trivy and Gitleaks
        never write that field, so without this flag their pushes are additive forever
        and the customer sees findings that never resolve."""
        doc = tmp_path / "trivy.sarif"
        doc.write_bytes(b'{"version":"2.1.0","runs":[{"tool":{"driver":{"name":"trivy"}}}]}')
        with _patches()[0], _patches()[1], _patches()[2] as cs_cls:
            result, inst = _invoke(
                ["cloudsec", "code", "ingest", "--repo", "acme/api",
                 "--source", "sarif", "-f", str(doc), "--scanner-succeeded"],
                cs_cls, {"result": {}})
            assert result.exit_code == 0, result.output
            pushed = json.loads(inst.ingest_code_results.call_args[0][2])
            assert pushed["runs"][0]["invocations"] == [{"executionSuccessful": True}]
            # The rest of the document is untouched.
            assert pushed["runs"][0]["tool"]["driver"]["name"] == "trivy"

    def test_scanner_failed_records_the_failure_rather_than_omitting_it(self, tmp_path):
        """The flag is not a way to say 'always true'. A job whose scan step failed
        records THAT, which keeps the document additive instead of letting a broken
        scan look like a clean one."""
        doc = tmp_path / "trivy.sarif"
        doc.write_bytes(b'{"version":"2.1.0","runs":[{"tool":{"driver":{"name":"trivy"}}}]}')
        with _patches()[0], _patches()[1], _patches()[2] as cs_cls:
            result, inst = _invoke(
                ["cloudsec", "code", "ingest", "--repo", "acme/api",
                 "--source", "sarif", "-f", str(doc), "--scanner-failed"],
                cs_cls, {"result": {}})
            assert result.exit_code == 0, result.output
            pushed = json.loads(inst.ingest_code_results.call_args[0][2])
            assert pushed["runs"][0]["invocations"] == [{"executionSuccessful": False}]

    def test_a_tools_own_execution_claim_is_never_overwritten(self, tmp_path):
        """The tool knows whether it ran; the caller only knows whether the command
        exited 0. Overwriting a tool's executionSuccessful:false with true would
        manufacture exactly the authority this rule exists to withhold."""
        doc = tmp_path / "scan.sarif"
        doc.write_bytes(b'{"version":"2.1.0","runs":[{"invocations":'
                        b'[{"executionSuccessful":false}],"tool":{"driver":{"name":"x"}}}]}')
        with _patches()[0], _patches()[1], _patches()[2] as cs_cls:
            result, inst = _invoke(
                ["cloudsec", "code", "ingest", "--repo", "acme/api",
                 "--source", "sarif", "-f", str(doc), "--scanner-succeeded"],
                cs_cls, {"result": {}})
            assert result.exit_code == 0, result.output
            pushed = json.loads(inst.ingest_code_results.call_args[0][2])
            assert pushed["runs"][0]["invocations"] == [{"executionSuccessful": False}]
            assert "already states its own execution result" in result.output

    def test_an_invocation_that_states_nothing_is_still_stamped(self, tmp_path):
        """'invocations':[{}] is a run that has an invocation object and says NOTHING in
        it. The server reads a missing executionSuccessful as unsuccessful, so such a
        document closes nothing — declining to stamp it because the key is present would
        refuse at exactly the moment stamping was needed, and tell the operator the flag
        was unnecessary."""
        doc = tmp_path / "scan.sarif"
        doc.write_bytes(b'{"version":"2.1.0","runs":[{"invocations":[{}],"tool":{}}]}')
        with _patches()[0], _patches()[1], _patches()[2] as cs_cls:
            result, inst = _invoke(
                ["cloudsec", "code", "ingest", "--repo", "acme/api",
                 "--source", "sarif", "-f", str(doc), "--scanner-succeeded"],
                cs_cls, {"result": {}})
            assert result.exit_code == 0, result.output
            pushed = json.loads(inst.ingest_code_results.call_args[0][2])
            assert pushed["runs"][0]["invocations"] == [{"executionSuccessful": True}]

    def test_a_document_with_no_runs_says_so_rather_than_claiming_the_tool_spoke(self, tmp_path):
        """'every run already states its own result' is reassurance, and it is the wrong
        reassurance for a document that has no runs at all."""
        doc = tmp_path / "empty.sarif"
        doc.write_bytes(b'{"version":"2.1.0","runs":[]}')
        with _patches()[0], _patches()[1], _patches()[2] as cs_cls:
            result, inst = _invoke(
                ["cloudsec", "code", "ingest", "--repo", "acme/api",
                 "--source", "sarif", "-f", str(doc), "--scanner-succeeded"],
                cs_cls, {"result": {}})
            assert result.exit_code == 0, result.output
            assert "has no runs" in result.output
            assert "already states" not in result.output

    def test_non_ascii_text_is_not_escape_inflated(self, tmp_path):
        """json.dumps defaults to ensure_ascii=True, which turns every non-ASCII character
        into \\uXXXX and can nearly double a document whose messages are not Latin. The
        size cap is applied to the STAMPED bytes, so that inflation could refuse a file
        that is well under the limit on disk."""
        doc = tmp_path / "cjk.sarif"
        body = {"version": "2.1.0", "runs": [{"tool": {"driver": {"name": "trivy"}},
                "results": [{"message": {"text": "\u5371\u967a\u306a\u4f9d\u5b58\u95a2\u4fc2" * 200}}]}]}
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        doc.write_bytes(raw)
        with _patches()[0], _patches()[1], _patches()[2] as cs_cls:
            result, inst = _invoke(
                ["cloudsec", "code", "ingest", "--repo", "acme/api",
                 "--source", "sarif", "-f", str(doc), "--scanner-succeeded"],
                cs_cls, {"result": {}})
            assert result.exit_code == 0, result.output
            sent = inst.ingest_code_results.call_args[0][2]
            # Compaction may shrink it; escape-inflation would grow it by ~2x.
            assert len(sent) < len(raw) * 1.2, "the document was escape-inflated"
            assert json.loads(sent)["runs"][0]["invocations"] == [{"executionSuccessful": True}]

    def test_a_corrupt_gzip_names_the_file_and_the_problem(self, tmp_path):
        """gzip raises BadGzipFile/EOFError, neither a ValueError, so without an explicit
        guard the failure escapes to the CLI's catch-all and prints a bare zlib message
        with no filename and no hint that the compression is the problem."""
        doc = tmp_path / "truncated.sarif.gz"
        import gzip as _gzip
        doc.write_bytes(_gzip.compress(b'{"version":"2.1.0","runs":[]}')[:12])
        with _patches()[0], _patches()[1], _patches()[2] as cs_cls:
            result, inst = _invoke(
                ["cloudsec", "code", "ingest", "--repo", "acme/api",
                 "--source", "sarif", "-f", str(doc), "--scanner-succeeded"],
                cs_cls, {"result": {}})
            assert result.exit_code != 0
            assert "not a readable gzip stream" in result.output
            inst.ingest_code_results.assert_not_called()

    def test_corruption_inside_the_deflate_stream_is_caught_too(self, tmp_path):
        """Gzip corruption raises THREE exception types and none is a ValueError: EOFError
        for a truncated stream, BadGzipFile (an OSError) for a bad header or CRC, and
        zlib.error — which subclasses neither — for corruption inside the deflate stream.
        A guard that catches only the first two is blind to the shape it was written for."""
        import gzip as _gzip
        body = json.dumps({"version": "2.1.0",
                           "runs": [{"tool": {"driver": {"name": "t"}}}] * 500}).encode()
        blob = bytearray(_gzip.compress(body))
        for i in range(30, 60):
            blob[i] ^= 0xFF
        doc = tmp_path / "corrupt.sarif.gz"
        doc.write_bytes(bytes(blob))
        with _patches()[0], _patches()[1], _patches()[2] as cs_cls:
            result, inst = _invoke(
                ["cloudsec", "code", "ingest", "--repo", "acme/api",
                 "--source", "sarif", "-f", str(doc), "--scanner-succeeded"],
                cs_cls, {"result": {}})
            assert result.exit_code != 0
            assert "not a readable gzip stream" in result.output
            inst.ingest_code_results.assert_not_called()

    def test_a_number_json_cannot_represent_is_refused_not_emitted_as_Infinity(self, tmp_path):
        """Python parses 1e400 as inf and writes it back as the bare token `Infinity`,
        which is not valid JSON and which the Go server rejects outright. Re-serializing is
        the ONLY way that can happen — without the flag the original bytes go through
        untouched — so this must refuse rather than turn a readable document into an
        unreadable one."""
        doc = tmp_path / "huge.sarif"
        doc.write_bytes(b'{"version":"2.1.0","runs":[{"tool":{},"properties":{"n":1e400}}]}')
        with _patches()[0], _patches()[1], _patches()[2] as cs_cls:
            result, inst = _invoke(
                ["cloudsec", "code", "ingest", "--repo", "acme/api",
                 "--source", "sarif", "-f", str(doc), "--scanner-succeeded"],
                cs_cls, {"result": {}})
            assert result.exit_code != 0
            assert "cannot represent" in result.output
            inst.ingest_code_results.assert_not_called()

    def test_the_same_document_is_pushed_untouched_without_the_flag(self, tmp_path):
        """The control for both refusals above: neither shape is a problem the CLI creates
        for a caller who did not ask it to rewrite the document."""
        raw = b'{"version":"2.1.0","runs":[{"tool":{},"properties":{"n":1e400}}]}'
        doc = tmp_path / "huge.sarif"
        doc.write_bytes(raw)
        with _patches()[0], _patches()[1], _patches()[2] as cs_cls:
            result, inst = _invoke(
                ["cloudsec", "code", "ingest", "--repo", "acme/api",
                 "--source", "sarif", "-f", str(doc)],
                cs_cls, {"result": {}})
            assert result.exit_code == 0, result.output
            assert inst.ingest_code_results.call_args[0][2] == raw

    def test_a_gzipped_sarif_is_stamped_and_stays_gzipped(self, tmp_path):
        """CI jobs gzip large SARIF files. Stamping must not silently hand the API a
        document in a different encoding than the one it was given."""
        import gzip as _gzip
        doc = tmp_path / "trivy.sarif.gz"
        doc.write_bytes(_gzip.compress(b'{"version":"2.1.0","runs":[{"tool":{}}]}'))
        with _patches()[0], _patches()[1], _patches()[2] as cs_cls:
            result, inst = _invoke(
                ["cloudsec", "code", "ingest", "--repo", "acme/api",
                 "--source", "sarif", "-f", str(doc), "--scanner-succeeded"],
                cs_cls, {"result": {}})
            assert result.exit_code == 0, result.output
            sent = inst.ingest_code_results.call_args[0][2]
            assert sent[:2] == b"\x1f\x8b", "the document must still be gzipped"
            pushed = json.loads(_gzip.decompress(sent))
            assert pushed["runs"][0]["invocations"] == [{"executionSuccessful": True}]

    def test_the_flag_is_refused_for_sources_that_state_their_own_coverage(self, tmp_path):
        """report/v1 states its coverage directly and CycloneDX makes no claim about a
        scan having run, so silently accepting the flag there would imply it did
        something."""
        doc = tmp_path / "report.json"
        doc.write_bytes(b'{"schema":"lc-code-report/v1"}')
        with _patches()[0], _patches()[1], _patches()[2] as cs_cls:
            result, inst = _invoke(
                ["cloudsec", "code", "ingest", "--repo", "acme/api",
                 "--source", "report", "-f", str(doc), "--scanner-succeeded"],
                cs_cls, {"result": {}})
            assert result.exit_code != 0
            assert "--source sarif only" in result.output
            inst.ingest_code_results.assert_not_called()

    def test_without_the_flag_the_document_is_pushed_byte_for_byte(self, tmp_path):
        """The control: the CLI must not start rewriting documents on its own. Stamping
        happens only when the caller asks for it."""
        raw = b'{"version":"2.1.0","runs":[{"tool":{"driver":{"name":"trivy"}}}]}'
        doc = tmp_path / "trivy.sarif"
        doc.write_bytes(raw)
        with _patches()[0], _patches()[1], _patches()[2] as cs_cls:
            result, inst = _invoke(
                ["cloudsec", "code", "ingest", "--repo", "acme/api",
                 "--source", "sarif", "-f", str(doc)],
                cs_cls, {"result": {}})
            assert result.exit_code == 0, result.output
            assert inst.ingest_code_results.call_args[0][2] == raw

    def test_code_scan_refuses_to_do_nothing(self, tmp_path):
        """Without --ingest and without -o the report would be written into a
        temporary directory and deleted — a command that appears to succeed and
        leaves nothing behind. It must say so instead."""
        with _patches()[0], _patches()[1], _patches()[2] as cs_cls:
            with patch("limacharlie.commands.cloudsec._run_code_scanner"):
                result, inst = _invoke(
                    ["cloudsec", "code", "scan", str(tmp_path), "--repo", "acme/api"],
                    cs_cls, {"result": {}})
            assert result.exit_code != 0
            assert "nothing to do with the report" in result.output
            inst.ingest_code_results.assert_not_called()

    def test_code_scan_will_not_guess_the_repository(self, tmp_path):
        """--ingest against a checkout whose origin names no repository must
        refuse: which repository a finding belongs to is an identity, and a
        guessed one attaches somebody's findings to the wrong node."""
        with _patches()[0], _patches()[1], _patches()[2] as cs_cls:
            result, inst = _invoke(
                ["cloudsec", "code", "scan", str(tmp_path), "--ingest"],
                cs_cls, {"result": {}})
            assert result.exit_code != 0
            assert "--repo" in result.output
            inst.ingest_code_results.assert_not_called()

    def test_code_scan_container_invocation(self, tmp_path, monkeypatch):
        """The docker argv is the only genuinely fragile thing in this command — the
        mounts, the identity it runs as, and the data sources the scanner refuses to
        start without. It is asserted here because getting it wrong produces a scanner
        that cannot run at all, which is what happened once already."""
        from limacharlie.commands import cloudsec as cs_mod

        captured = {}

        def fake_run(cmd, timeout_s, *, env=None, container=None, usage_hint=None):
            captured["cmd"] = cmd
            captured["container"] = container
            # Stand in for the scanner: the caller reads this file next.
            out = cmd[cmd.index("--out") + 1]
            host_out = os.path.join(
                cmd[cmd.index("-v") + 1].split(":")[0], os.path.basename(out))
            with open(host_out, "wb") as f:
                f.write(b"REPORT")

        monkeypatch.setattr(cs_mod, "_run", fake_run)
        with _patches()[0], _patches()[1], _patches()[2] as cs_cls:
            result, _ = _invoke(
                ["cloudsec", "code", "scan", str(tmp_path), "--repo", "acme/api",
                 "-o", str(tmp_path / "report.json.gz")],
                cs_cls, {"result": {}})
        assert result.exit_code == 0, result.output
        cmd = captured["cmd"]
        assert cmd[:3] == ["docker", "run", "--rm"]
        joined = " ".join(cmd)
        # The checkout is mounted READ-ONLY; the scratch volume is the private workdir.
        assert "%s:/scan/src:ro" % str(tmp_path) in cmd
        assert any(a.endswith(":/scan") for a in cmd)
        # The scanner refuses to start without these, by design.
        assert any(a.startswith("TRIVY_DB_REPOSITORY=") for a in cmd)
        assert any(a.startswith("TRIVY_JAVA_DB_REPOSITORY=") for a in cmd)
        # No checks mirror was given, so the compiled-in checks are used rather than
        # silently skipping infrastructure files.
        assert "--embedded-checks" in cmd
        assert captured["container"] and "--name" in cmd
        assert "--spec" in joined and "/scan/spec.json" in joined

    def test_code_scan_refuses_scanners_it_cannot_run(self, tmp_path):
        """An unknown scanner used to be dropped silently — a narrower scan reported as a
        successful one. And `secrets` cannot work locally at all."""
        for bad, expect in [("sca,iacc", "unknown scanner"),
                            ("sca,secrets", "cannot run in a local scan")]:
            with _patches()[0], _patches()[1], _patches()[2] as cs_cls:
                result, _ = _invoke(
                    ["cloudsec", "code", "scan", str(tmp_path), "--repo", "acme/api",
                     "-o", str(tmp_path / "r.gz"), "--scanners", bad],
                    cs_cls, {"result": {}})
            assert result.exit_code != 0, bad
            assert expect in result.output, result.output

    # -- static-analysis rule sets ---------------------------------------------------

    @staticmethod
    def _scan_capturing(monkeypatch, tmp_path, extra_args, *, fail_code=0, hive_records=None):
        """Run `code scan` with the subprocess boundary replaced, capturing the argv and
        the rule set document the scanner would have been handed."""
        from limacharlie.commands import cloudsec as cs_mod

        captured = {}

        def fake_run(cmd, timeout_s, *, env=None, container=None, usage_hint=None):
            captured["cmd"] = cmd
            captured["usage_hint"] = usage_hint
            if cmd[0] == "docker":
                workdir = next(a for a in cmd if a.endswith(":/scan")).rsplit(":", 1)[0]
                to_host = lambda p: os.path.join(workdir, os.path.relpath(p, "/scan"))
            else:
                to_host = lambda p: p
            if "--rules-file" in cmd:
                with open(to_host(cmd[cmd.index("--rules-file") + 1]), "rb") as f:
                    captured["rules"] = f.read()
            if fail_code:
                # Exercise the real exit handling with the code the scanner returned.
                real = subprocess.CompletedProcess(cmd, fail_code)
                with patch("limacharlie.commands.cloudsec.subprocess.run", return_value=real):
                    return orig_run(cmd, timeout_s, env=env, container=container,
                                    usage_hint=usage_hint)
            with open(to_host(cmd[cmd.index("--out") + 1]), "wb") as f:
                f.write(b"REPORT")

        orig_run = cs_mod._run
        monkeypatch.setattr(cs_mod, "_run", fake_run)
        hive = MagicMock()
        hive.list.return_value = hive_records or {}
        with patch("limacharlie.commands.cloudsec.Hive", return_value=hive) as hive_cls, \
                _patches()[0], _patches()[1], _patches()[2] as cs_cls:
            result, _ = _invoke(
                ["cloudsec", "code", "scan", str(tmp_path), "--repo", "acme/api",
                 "-o", str(tmp_path / "r.gz")] + extra_args,
                cs_cls, {"result": {}})
        captured["hive_cls"] = hive_cls
        return result, captured

    def test_code_scan_sast_runs_the_default_rules_by_default(self, tmp_path, monkeypatch):
        """The scanner carries no rules: a sast scan with no rule option must ask for the
        shipped default set, or it silently runs no static analysis at all."""
        from limacharlie.commands import cloudsec as cs_mod
        result, cap = self._scan_capturing(monkeypatch, tmp_path, ["--scanners", "sca,sast"])
        assert result.exit_code == 0, result.output
        cmd = cap["cmd"]
        assert cmd[0] == "docker"
        assert cs_mod.DEFAULT_CODE_SCANNER_IMAGE in cmd
        assert cs_mod.DEFAULT_CODE_SCANNER_IMAGE.endswith(":v0.16.0")
        assert "--default-rules" in cmd and "--rules-file" not in cmd
        # The pinned image is known to take the flags, so no hint is attached.
        assert cap["usage_hint"] is None

    def test_code_scan_without_sast_passes_no_rule_flag(self, tmp_path, monkeypatch):
        """Without sast there is nothing to give rules to, and passing a rule flag anyway
        would break a scan against a scanner older than the flag."""
        result, cap = self._scan_capturing(monkeypatch, tmp_path, [])
        assert result.exit_code == 0, result.output
        assert "--default-rules" not in cap["cmd"]
        assert "--rules-file" not in cap["cmd"]

    def test_code_scan_rules_file_replaces_the_default_rules(self, tmp_path, monkeypatch):
        doc = {"version": 1, "records": [
            {"key": "my-rule", "rules": {"rules": [{"id": "r1"}]}}]}
        raw = json.dumps(doc).encode()
        rules = tmp_path / "rules.json"
        rules.write_bytes(raw)
        result, cap = self._scan_capturing(
            monkeypatch, tmp_path, ["--scanners", "sast", "--rules-file", str(rules)])
        assert result.exit_code == 0, result.output
        cmd = cap["cmd"]
        assert "--default-rules" not in cmd
        # Handed over inside the private scratch volume, byte for byte: the caller's own
        # directory is never mounted into the container.
        assert cmd[cmd.index("--rules-file") + 1] == "/scan/rules.json"
        assert cap["rules"] == raw
        assert cmd.count("-v") == 2

    def test_code_scan_binary_gets_the_rules_file_on_the_host(self, tmp_path, monkeypatch):
        body = '{"version":1,"records":[{"key":"k","rules":{"rules":[{"id":"r"}]}}]}'
        rules = tmp_path / "rules.json"
        rules.write_text(body)
        result, cap = self._scan_capturing(
            monkeypatch, tmp_path, ["--scanners", "sast", "--binary", "/opt/scanner-agent",
                                    "--rules-file", str(rules)])
        assert result.exit_code == 0, result.output
        cmd = cap["cmd"]
        assert cmd[0] == "/opt/scanner-agent"
        path = cmd[cmd.index("--rules-file") + 1]
        assert os.path.isabs(path) and path.endswith("rules.json")
        assert cap["rules"] == body.encode()
        assert "--default-rules" not in cmd
        # A binary we did not pin may predate the flag: its usage error gets the hint.
        assert "v0.16.0" in cap["usage_hint"]

    def test_code_scan_binary_default_rules(self, tmp_path, monkeypatch):
        result, cap = self._scan_capturing(
            monkeypatch, tmp_path, ["--scanners", "sast", "--binary", "/opt/scanner-agent"])
        assert result.exit_code == 0, result.output
        assert cap["cmd"][0] == "/opt/scanner-agent"
        assert "--default-rules" in cap["cmd"]

    def test_code_scan_rule_options_are_refused_where_they_cannot_apply(
            self, tmp_path, monkeypatch):
        rules = tmp_path / "rules.json"
        rules.write_text('{"version":1,"records":[]}')
        cases = [
            (["--scanners", "sast", "--rules-file", str(rules), "--org-rules"],
             "give one"),
            (["--rules-file", str(rules)], "only applies to the sast scanner"),
            (["--org-rules"], "only applies to the sast scanner"),
        ]
        for args, expect in cases:
            result, cap = self._scan_capturing(monkeypatch, tmp_path, args)
            assert result.exit_code != 0, args
            assert expect in result.output, result.output
            assert "cmd" not in cap, args
            cap["hive_cls"].assert_not_called()

    def test_code_scan_refuses_a_rules_file_that_is_not_a_rule_set(
            self, tmp_path, monkeypatch):
        cases = [
            ("not json", "is not JSON"),
            ('{"rules":[{"id":"x"}]}', "is not a code rule set document"),
            ('{"version":2,"records":[]}', "is not a code rule set document"),
            ('{"version":1,"records":[{"key":"","rules":{"rules":[]}}]}', "record 0"),
            ('{"version":1,"records":[{"key":"k","rules":[]}]}', "record 0"),
            ('{"version":1,"records":[{"key":"k","rules":{"rules":[{"id":"a"}]}},'
             '{"key":"k","rules":{"rules":[{"id":"b"}]}}]}', "duplicate record key 'k'"),
            # The scanner parses with unknown fields refused and reports a refused document
            # as a section error while still exiting 0, so these must stop here.
            ('{"version":1,"records":[],"comment":"x"}', "is not a code rule set document"),
            ('{"version":true,"records":[]}', "is not a code rule set document"),
            ('{"version":1,"records":[{"key":"k","enabled":true,"rules":{"rules":[{"id":"a"}]}}]}',
             "record 0"),
            # Nothing to run: a sast pass that ran no rule is not a clean scan.
            ('{"version":1,"records":[]}', "holds no rules"),
            ('{"version":1,"records":[{"key":"k","rules":{}}]}', "holds no rules"),
        ]
        for body, expect in cases:
            rules = tmp_path / "rules.json"
            rules.write_text(body)
            result, cap = self._scan_capturing(
                monkeypatch, tmp_path, ["--scanners", "sast", "--rules-file", str(rules)])
            assert result.exit_code != 0, body
            assert expect in result.output, result.output
            assert "cmd" not in cap, body

    def test_code_scan_org_rules_builds_the_hosted_rule_set(self, tmp_path, monkeypatch):
        """--org-rules composes what a hosted scan runs: enabled, unexpired records only,
        sorted by key, each contributing just its rules array."""
        import time as _time
        from limacharlie.sdk.hive import HiveRecord

        future = int(_time.time() * 1000) + 3_600_000
        past = int(_time.time() * 1000) - 3_600_000
        rule = lambda i: {"id": i, "languages": ["python"], "severity": "ERROR",
                          "message": "m", "pattern": "eval(...)"}
        records = {
            "b-rule": HiveRecord(name="b-rule", enabled=True,
                                 data={"rules": [rule("b")], "note": "ignored"}),
            "a-rule": HiveRecord(name="a-rule", enabled=True, expiry=future,
                                 data={"rules": [rule("a")]}),
            "disabled": HiveRecord(name="disabled", enabled=False,
                                   data={"rules": [rule("d")]}),
            "expired": HiveRecord(name="expired", enabled=True, expiry=past,
                                  data={"rules": [rule("e")]}),
            "empty": HiveRecord(name="empty", enabled=True, data={"rules": []}),
        }
        result, cap = self._scan_capturing(
            monkeypatch, tmp_path, ["--scanners", "sast", "--org-rules"],
            hive_records=records)
        assert result.exit_code == 0, result.output
        assert cap["hive_cls"].call_args[0][1] == "cloudsec_code_rule"
        cmd = cap["cmd"]
        assert "--default-rules" not in cmd
        assert cmd[cmd.index("--rules-file") + 1] == "/scan/rules.json"
        # Laid out like the hosted lane's document: version first, then records.
        assert cap["rules"].startswith(b'{"version":1,"records":[{"key":"a-rule","rules":')
        doc = json.loads(cap["rules"])
        assert doc == {"version": 1, "records": [
            {"key": "a-rule", "rules": {"rules": [rule("a")]}},
            {"key": "b-rule", "rules": {"rules": [rule("b")]}},
        ]}
        # The enabled record that holds nothing is named, not dropped silently.
        assert "'empty'" in result.output

    def test_code_scan_org_rules_reads_nothing_when_a_local_check_fails(self, tmp_path,
                                                                       monkeypatch):
        """The org's rules are fetched only after every local check has passed."""
        bad = tmp_path / "a:b"
        bad.mkdir()
        from limacharlie.commands import cloudsec as cs_mod
        monkeypatch.setattr(cs_mod, "_run", lambda *a, **k: pytest.fail("scan ran"))
        with patch("limacharlie.commands.cloudsec.Hive") as hive_cls, \
                _patches()[0], _patches()[1], _patches()[2] as cs_cls:
            result, _ = _invoke(
                ["cloudsec", "code", "scan", str(bad), "--repo", "acme/api",
                 "-o", str(tmp_path / "r.gz"), "--scanners", "sast", "--org-rules"],
                cs_cls, {"result": {}})
        assert result.exit_code != 0
        assert "contains ':'" in result.output
        hive_cls.assert_not_called()

    def test_code_scan_org_rules_refuses_an_org_with_no_rules(self, tmp_path, monkeypatch):
        from limacharlie.sdk.hive import HiveRecord
        records = {"off": HiveRecord(name="off", enabled=False, data={"rules": [{"id": "x"}]})}
        result, cap = self._scan_capturing(
            monkeypatch, tmp_path, ["--scanners", "sast", "--org-rules"],
            hive_records=records)
        assert result.exit_code != 0
        assert "no enabled cloudsec_code_rule record" in result.output
        assert "cmd" not in cap

    def test_code_scan_org_rules_surfaces_a_hive_read_failure(self, tmp_path, monkeypatch):
        from limacharlie.commands import cloudsec as cs_mod
        monkeypatch.setattr(cs_mod, "_run", lambda *a, **k: pytest.fail("scan ran"))
        hive = MagicMock()
        hive.list.side_effect = RuntimeError("403 forbidden")
        with patch("limacharlie.commands.cloudsec.Hive", return_value=hive), \
                _patches()[0], _patches()[1], _patches()[2] as cs_cls:
            result, _ = _invoke(
                ["cloudsec", "code", "scan", str(tmp_path), "--repo", "acme/api",
                 "-o", str(tmp_path / "r.gz"), "--scanners", "sast", "--org-rules"],
                cs_cls, {"result": {}})
        assert result.exit_code != 0
        assert "cannot read this org's cloudsec_code_rule records" in result.output
        assert "403 forbidden" in result.output

    def test_code_scan_old_custom_scanner_usage_error_names_the_version(
            self, tmp_path, monkeypatch):
        """A pre-v0.16.0 --image rejects --default-rules with a usage exit. That must say
        which version is needed, not just a bare exit code."""
        result, cap = self._scan_capturing(
            monkeypatch, tmp_path,
            ["--scanners", "sast", "--image", "example.com/scanner:v0.4.0"], fail_code=2)
        assert result.exit_code != 0
        assert "example.com/scanner:v0.4.0" in cap["cmd"]
        assert "--default-rules" in cap["cmd"]
        assert "exited 2" in result.output
        assert "v0.16.0 or newer" in result.output

    def test_code_scan_other_failures_do_not_blame_the_scanner_version(
            self, tmp_path, monkeypatch):
        result, _ = self._scan_capturing(
            monkeypatch, tmp_path,
            ["--scanners", "sast", "--image", "example.com/scanner:v0.4.0"], fail_code=3)
        assert result.exit_code != 0
        assert "exited 3" in result.output
        assert "v0.16.0" not in result.output

    def test_git_repo_key_refuses_a_remote_that_names_no_repository(self):
        """A local remote yields a plausible, wrong key — exactly the guess --ingest
        refuses to make from an absent one."""
        from limacharlie.commands import cloudsec as cs_mod

        cases = {
            "https://github.com/acme/api.git": "acme/api",
            "git@github.com:acme/api.git": "acme/api",
            "/home/me/src/api": None,
            "file:///home/me/src/api": None,
            "../sibling/api": None,
        }
        for url, want in cases.items():
            with patch.object(cs_mod, "_git", return_value=url):
                assert cs_mod._git_repo_key("/anywhere") == want, url

    def test_git_repo_key_keeps_a_nested_gitlab_namespace_whole(self):
        """A GitLab repository nested under a group/subgroup namespace
        publishes that WHOLE path as its key (go-cloudsec
        model.SplitRepoKey cuts a nested-owner provider's key on the LAST
        '/'). Keeping only the last two segments would silently attribute
        a local scan to a DIFFERENT repository than the one checked out —
        one dropping the group, sharing the same subgroup/name."""
        from limacharlie.commands import cloudsec as cs_mod

        cases = {
            "https://gitlab.com/acme/platform/backend.git": "acme/platform/backend",
            "git@gitlab.com:acme/platform/backend.git": "acme/platform/backend",
            "https://gitlab.com/acme/platform/infra/backend.git":
                "acme/platform/infra/backend",
            # A flat two-segment owner (GitHub, Bitbucket, or a top-level
            # GitLab group) is unaffected — this is the no-op the fix must
            # preserve.
            "https://github.com/acme/api.git": "acme/api",
        }
        for url, want in cases.items():
            with patch.object(cs_mod, "_git", return_value=url):
                assert cs_mod._git_repo_key("/anywhere") == want, url

    def test_code_repos_all_walks_the_cursor(self):
        """--all must use the iterator, not a single page.

        A filtered page can be short without being last, so a one-shot page
        would quietly under-report the repository list.
        """
        with _patches()[0], _patches()[1], _patches()[2] as cs_cls:
            result, inst = _invoke(["cloudsec", "code", "repos", "--all"],
                                   cs_cls, {"repos": []})
            inst.iter_code_repos.return_value = iter([])
            assert result.exit_code == 0
            inst.iter_code_repos.assert_called_once()
            inst.list_code_repos.assert_not_called()

    def test_code_status(self):
        with _patches()[0], _patches()[1], _patches()[2] as cs_cls:
            result, inst = _invoke(["cloudsec", "code", "status"], cs_cls,
                                   {"code": [], "totals": {}})
            assert result.exit_code == 0
            inst.get_code_status.assert_called_once_with()

    def test_code_capabilities(self):
        with _patches()[0], _patches()[1], _patches()[2] as cs_cls:
            result, inst = _invoke(
                ["cloudsec", "code", "capabilities"], cs_cls, {"connections": []})
            assert result.exit_code == 0, result.output
            inst.get_code_capabilities.assert_called_once_with(repo=None)

    def test_code_capabilities_with_nested_gitlab_repo(self):
        """A nested GitLab namespace path is a valid --repo value here too;
        the CLI must not truncate or reject it before it reaches the SDK."""
        with _patches()[0], _patches()[1], _patches()[2] as cs_cls:
            result, inst = _invoke(
                ["cloudsec", "code", "capabilities", "--repo", "acme/platform/backend"],
                cs_cls, {"connections": []})
            assert result.exit_code == 0, result.output
            inst.get_code_capabilities.assert_called_once_with(repo="acme/platform/backend")

    def test_code_fixes(self):
        with _patches()[0], _patches()[1], _patches()[2] as cs_cls:
            result, inst = _invoke(
                ["cloudsec", "code", "fixes"], cs_cls, {"fixes": [], "distinct": 0})
            assert result.exit_code == 0, result.output
            inst.get_code_fixes.assert_called_once_with(cursor=None, limit=None)

    def test_code_fixes_forwards_cursor_and_limit(self):
        with _patches()[0], _patches()[1], _patches()[2] as cs_cls:
            result, inst = _invoke(
                ["cloudsec", "code", "fixes", "--cursor", "abc", "--limit", "20"],
                cs_cls, {"fixes": [], "distinct": 0})
            assert result.exit_code == 0, result.output
            inst.get_code_fixes.assert_called_once_with(cursor="abc", limit=20)

    def test_code_fixes_all_walks_the_cursor(self):
        """--all must use the iterator, not a single page — same rule as
        'code repos --all', for the same reason: a page can be short
        without being last."""
        with _patches()[0], _patches()[1], _patches()[2] as cs_cls:
            inst = MagicMock()
            inst.iter_code_fixes.return_value = iter([])
            cs_cls.return_value = inst
            runner = CliRunner()
            result = runner.invoke(
                cli, ["--output", "json", "cloudsec", "code", "fixes", "--all"])
            assert result.exit_code == 0, result.output
            inst.iter_code_fixes.assert_called_once()
            inst.get_code_fixes.assert_not_called()

    def test_code_sbom_prints_the_link(self):
        with _patches()[0], _patches()[1], _patches()[2] as cs_cls:
            result, inst = _invoke(
                ["cloudsec", "code", "sbom", "--repo", "acme/api"],
                cs_cls, {"repo": "acme/api", "sbom": {"url": "https://x"}})
            assert result.exit_code == 0
            inst.get_code_sbom.assert_called_once_with("acme/api", provider=None)
            inst.download_code_sbom.assert_not_called()

    def test_code_sbom_download_missing_is_an_explained_failure(self):
        """-o with no SBOM must NOT write an empty file that looks like one."""
        with _patches()[0], _patches()[1], _patches()[2] as cs_cls:
            inst = MagicMock()
            cs_cls.return_value = inst
            inst.download_code_sbom.return_value = None
            inst.get_code_sbom.return_value = {
                "repo": "acme/api", "sbom": None,
                "reason": "sbom_not_generated_yet"}
            runner = CliRunner()
            with runner.isolated_filesystem():
                result = runner.invoke(cli, [
                    "--output", "json", "cloudsec", "code", "sbom",
                    "--repo", "acme/api", "-o", "out.gz"])
                assert result.exit_code != 0
                assert "sbom_not_generated_yet" in result.output
                import os
                assert not os.path.exists("out.gz")

    def test_code_rescan_forwards_the_repository_and_ref(self):
        with _patches()[0], _patches()[1], _patches()[2] as cs_cls:
            result, inst = _invoke(
                ["cloudsec", "code", "rescan", "acme/api",
                 "--ref", "refs/heads/main"],
                cs_cls, {"accepted": True, "debounce_seconds": 600})
            assert result.exit_code == 0
            inst.rescan_code_repo.assert_called_once_with(
                "acme/api", ref="refs/heads/main", provider=None)

    def test_code_rescan_takes_the_repository_positionally(self):
        """'rescan <repo>' — the repository is the subject, not an option.

        The sibling 'code scan <path>' takes a filesystem path positionally
        for the same reason; keeping the two shapes apart is what stops
        'code rescan' from reading like a local scan of a directory.
        """
        with _patches()[0], _patches()[1], _patches()[2] as cs_cls:
            result, inst = _invoke(
                ["cloudsec", "code", "rescan", "lc-appsec-fixtures"],
                cs_cls, {"accepted": True})
            assert result.exit_code == 0
            inst.rescan_code_repo.assert_called_once_with(
                "lc-appsec-fixtures", ref=None, provider=None)

    def test_code_autofix_takes_the_finding_positionally(self):
        """'autofix <finding_id>' — the finding is the subject.

        And there is no --package/--version option, on purpose: the backend
        resolves the id against its own scan's rows, so naming a package here
        would be the one way to request a fix the scan never found.
        """
        with _patches()[0], _patches()[1], _patches()[2] as cs_cls:
            result, inst = _invoke(
                ["cloudsec", "code", "autofix", "fnd_" + "a" * 32],
                cs_cls, {"accepted": True, "debounce_seconds": 10})
            assert result.exit_code == 0
            inst.autofix_code_finding.assert_called_once_with(
                "fnd_" + "a" * 32, repo=None, provider=None)

    def test_code_autofix_forwards_the_repository_hint(self):
        with _patches()[0], _patches()[1], _patches()[2] as cs_cls:
            result, inst = _invoke(
                ["cloudsec", "code", "autofix", "fnd_" + "b" * 32,
                 "--repo", "acme/api"],
                cs_cls, {"accepted": True})
            assert result.exit_code == 0
            inst.autofix_code_finding.assert_called_once_with(
                "fnd_" + "b" * 32, repo="acme/api", provider=None)

    def test_finding_list_forwards_repo(self):
        with _patches()[0], _patches()[1], _patches()[2] as cs_cls:
            result, inst = _invoke(
                ["cloudsec", "finding", "list", "--repo", "acme/api",
                 "--repo", "acme/web"], cs_cls, {"findings": []})
            assert result.exit_code == 0
            assert inst.list_findings.call_args.kwargs["repo"] == [
                "acme/api", "acme/web"]

    def test_finding_facets_forwards_repo(self):
        with _patches()[0], _patches()[1], _patches()[2] as cs_cls:
            result, inst = _invoke(
                ["cloudsec", "finding", "facets", "--repo", "acme/api"],
                cs_cls, {"facets": {}})
            assert result.exit_code == 0
            assert inst.get_finding_facets.call_args.kwargs["repo"] == ["acme/api"]

    def test_export_findings_forwards_repo(self):
        with _patches()[0], _patches()[1], _patches()[2] as cs_cls:
            result, inst = _invoke(
                ["cloudsec", "export", "findings", "--repo", "acme/api"],
                cs_cls)
            assert result.exit_code == 0
            assert inst.export_findings_csv.call_args.kwargs["repo"] == ["acme/api"]


class TestFindingVulnerabilitySelectors:
    """The B52 noise-control selectors and the image pivot.

    `grain` is the one selector whose ABSENCE is not "unconstrained": the
    server's default worklist leads with the package grain, so without
    `--grain cve` the per-CVE findings are unreachable. These tests pin
    that every one of them survives the CLI -> SDK hop, on every route
    that accepts them.
    """

    def test_list_forwards_vulnerability_selectors(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "finding", "list",
                 "--grain", "cve", "--grain", "other",
                 "--fix-state", "fix_available",
                 "--exploit-band", "kev_overdue",
                 "--exploit-band", "kev_due",
                 "--image-urn", "lcrn:img:a", "--image-urn", "lcrn:img:b",
                 "--cause", "lcrn:fw/allow-all"],
                cls, return_value={"findings": []},
            )
            assert result.exit_code == 0, result.output
            kwargs = inst.list_findings.call_args.kwargs
            assert kwargs["grain"] == ["cve", "other"]
            assert kwargs["fix_state"] == ["fix_available"]
            assert kwargs["exploit_band"] == ["kev_overdue", "kev_due"]
            assert kwargs["image_urn"] == ["lcrn:img:a", "lcrn:img:b"]
            assert kwargs["cause"] == "lcrn:fw/allow-all"

    def test_facets_forwards_vulnerability_selectors(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "finding", "facets", "--grain", "cve",
                 "--fix-state", "unknown", "--image-urn", "lcrn:img:a"],
                cls, return_value={"facets": {}},
            )
            assert result.exit_code == 0, result.output
            kwargs = inst.get_finding_facets.call_args.kwargs
            assert kwargs["grain"] == ["cve"]
            assert kwargs["fix_state"] == ["unknown"]
            assert kwargs["image_urn"] == ["lcrn:img:a"]

    def test_causes_forwards_vulnerability_selectors(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "finding", "causes", "--grain", "package",
                 "--exploit-band", "none"],
                cls, return_value={"causes": [], "distinct": 0},
            )
            assert result.exit_code == 0, result.output
            kwargs = inst.list_finding_causes.call_args.kwargs
            assert kwargs["grain"] == ["package"]
            assert kwargs["exploit_band"] == ["none"]

    def test_export_forwards_vulnerability_selectors(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "export", "findings", "--grain", "cve",
                 "--image-urn", "lcrn:img:a"],
                cls,
            )
            assert result.exit_code == 0, result.output
            kwargs = inst.export_findings_csv.call_args.kwargs
            assert kwargs["grain"] == ["cve"]
            assert kwargs["image_urn"] == ["lcrn:img:a"]

    def test_closed_vocabularies_are_validated_client_side(self):
        """A typo must not read as an unfiltered estate.

        These are repeatable keys, so a bad value would survive to the
        backend and return an empty page — but `--grain` is worse than
        that: a dropped value re-engages the leading-grain DEFAULT, which
        answers a different question successfully. Refuse them here.
        """
        for flag, bad in (("--grain", "packages"),
                          ("--fix-state", "available"),
                          ("--exploit-band", "kev")):
            p1, p2, p3 = _patches()
            with p1, p2, p3 as cls:
                result, _inst = _invoke(
                    ["cloudsec", "finding", "list", flag, bad], cls,
                )
                assert result.exit_code == 2, (flag, result.output)
                assert bad in result.output


class TestCodePRCheck:
    def test_pr_check_forwards_the_body(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "code", "pr-check", "acme/api", "--pr", "42",
                 "--base-sha", "a" * 40, "--head-sha", "b" * 40,
                 "--action", "synchronize"],
                cls, return_value={"accepted": True},
            )
            assert result.exit_code == 0, result.output
            inst.check_pull_request.assert_called_once_with(
                "acme/api", 42, "a" * 40, "b" * 40, "synchronize",
                prev_base_sha=None,
                base_ref=None, head_ref=None, provider=None,
            )

    def test_edited_without_prev_base_sha_is_refused(self):
        """`edited` also reports a title change, which changes nothing.

        Sending one without prev_base_sha would spend a published RPC on
        every description edit in a busy repository, so refuse it here
        rather than downstream.
        """
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "code", "pr-check", "acme/api", "--pr", "42",
                 "--base-sha", "a" * 40, "--head-sha", "b" * 40,
                 "--action", "edited"],
                cls,
            )
            assert result.exit_code == 2, result.output
            assert "--prev-base-sha" in result.output
            inst.check_pull_request.assert_not_called()

    def test_prev_base_sha_without_edited_is_refused(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "code", "pr-check", "acme/api", "--pr", "42",
                 "--base-sha", "a" * 40, "--head-sha", "b" * 40,
                 "--action", "opened", "--prev-base-sha", "c" * 40],
                cls,
            )
            assert result.exit_code == 2, result.output
            inst.check_pull_request.assert_not_called()

    def test_edited_with_prev_base_sha_is_accepted(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "code", "pr-check", "acme/api", "--pr", "42",
                 "--base-sha", "a" * 40, "--head-sha", "b" * 40,
                 "--action", "edited", "--prev-base-sha", "c" * 40],
                cls, return_value={"accepted": True},
            )
            assert result.exit_code == 0, result.output
            assert inst.check_pull_request.call_args.kwargs[
                "prev_base_sha"] == "c" * 40

    def test_a_missing_action_is_refused(self):
        """The host refuses a body with no action, so never send one.

        The gateway tolerates an absent action — it guards its vocabulary
        check with `action != ""` — but the collection host behind it
        does not, so a request without one fails unconditionally. That is
        exactly the shape a CI job would send if the flag were optional.
        """
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "code", "pr-check", "acme/api", "--pr", "42",
                 "--base-sha", "a" * 40, "--head-sha", "b" * 40],
                cls,
            )
            assert result.exit_code == 2, result.output
            assert "--action" in result.output
            inst.check_pull_request.assert_not_called()

    def test_unknown_action_is_refused(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "code", "pr-check", "acme/api", "--pr", "42",
                 "--base-sha", "a" * 40, "--head-sha", "b" * 40,
                 "--action", "closed"],
                cls,
            )
            assert result.exit_code == 2, result.output
            inst.check_pull_request.assert_not_called()


class TestCodeWebhook:
    def test_webhook_forwards_the_three_fields(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "code", "webhook", "--connection", "my-github",
                 "--url", "https://x.hook.limacharlie.io/oid/"
                          "github-code-webhook-my-github/abc",
                 "--secret", "s" * 24],
                cls, return_value={"state": "available"},
            )
            assert result.exit_code == 0, result.output
            inst.configure_code_webhook.assert_called_once_with(
                "my-github",
                "https://x.hook.limacharlie.io/oid/"
                "github-code-webhook-my-github/abc",
                "s" * 24,
            )

    def test_the_secret_is_not_echoed(self):
        """The url's last segment and the secret are credentials."""
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, _inst = _invoke(
                ["cloudsec", "code", "webhook", "--connection", "my-github",
                 "--url", "https://x.hook.limacharlie.io/oid/"
                          "github-code-webhook-my-github/abc",
                 "--secret", "sekrit-value-not-in-output"],
                cls, return_value={"state": "available", "reason": ""},
            )
            assert result.exit_code == 0, result.output
            assert "sekrit-value-not-in-output" not in result.output
            # The url's last segment is the adapter's URL secret, so the
            # whole url is a credential too — it must not be echoed back
            # as a confirmation the way a benign argument would be.
            assert "hook.limacharlie.io" not in result.output


class TestImageCommands:
    def test_image_repos_forwards_tri_state_and_selectors(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "image", "repos", "--provider", "aws",
                 "--registry", "r1", "--region", "us-east-1",
                 "--without-findings", "--with-images",
                 "--scanning-state", "disabled", "--sort", "risk",
                 "--limit", "50"],
                cls, return_value={"image_repos": []},
            )
            assert result.exit_code == 0, result.output
            kwargs = inst.list_image_repos.call_args.kwargs
            assert kwargs["provider"] == ["aws"]
            assert kwargs["registry"] == ["r1"]
            assert kwargs["region"] == ["us-east-1"]
            assert kwargs["has_findings"] is False
            assert kwargs["has_images"] is True
            assert kwargs["scanning_state"] == "disabled"
            assert kwargs["sort"] == "risk"
            assert kwargs["limit"] == 50

    def test_image_repos_tri_state_defaults_to_unconstrained(self):
        """Omitting the flag must send None, not False.

        False is a real selection on these dimensions ("repositories with
        no findings"), so defaulting it would silently narrow the read.
        """
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "image", "repos"], cls,
                return_value={"image_repos": []},
            )
            assert result.exit_code == 0, result.output
            kwargs = inst.list_image_repos.call_args.kwargs
            assert kwargs["has_findings"] is None
            assert kwargs["has_images"] is None

    def test_image_repos_all_walks_the_cursor(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            inst = MagicMock()
            cls.return_value = inst
            inst.iter_image_repos.return_value = iter([{"urn": "a"},
                                                       {"urn": "b"}])
            runner = CliRunner()
            result = runner.invoke(
                cli, ["--output", "json", "cloudsec", "image", "repos",
                      "--all"],
            )
            assert result.exit_code == 0, result.output
            payload = json.loads(result.output)
            assert payload["image_repos"] == [{"urn": "a"}, {"urn": "b"}]
            assert payload["total"] == 2
            assert payload["next_cursor"] == ""
            inst.list_image_repos.assert_not_called()

    def test_image_repo_facets_takes_no_paging(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "image", "repo-facets", "--provider", "gcp"],
                cls, return_value={"total": 0},
            )
            assert result.exit_code == 0, result.output
            kwargs = inst.get_image_repo_facets.call_args.kwargs
            assert "cursor" not in kwargs and "limit" not in kwargs
            assert kwargs["provider"] == ["gcp"]

    def test_image_list_forwards_placement_selectors(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "image", "list", "--repo-urn", "lcrn:repo:1",
                 "--tag", "latest", "--tag", "v2", "--findings", "with",
                 "--running", "--unsigned", "--sort", "pushed"],
                cls, return_value={"images": []},
            )
            assert result.exit_code == 0, result.output
            kwargs = inst.list_container_images.call_args.kwargs
            assert kwargs["repo_urn"] == ["lcrn:repo:1"]
            assert kwargs["tag"] == ["latest", "v2"]
            assert kwargs["findings"] == "with"
            assert kwargs["running"] is True
            assert kwargs["signed"] is False
            assert kwargs["sort"] == "pushed"

    def test_image_list_signed_defaults_to_unconstrained(self):
        """Unknown signing status matches neither True nor False.

        The server predicate is `signed = @signed`, so an image whose
        provider never reported a signature is invisible under either
        pinned value. Defaulting the flag would hide those rows.
        """
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "image", "list"], cls,
                return_value={"images": []},
            )
            assert result.exit_code == 0, result.output
            kwargs = inst.list_container_images.call_args.kwargs
            assert kwargs["signed"] is None
            assert kwargs["running"] is None

    def test_image_get_passes_the_digest(self):
        p1, p2, p3 = _patches()
        digest = "sha256:" + "0" * 64
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "image", "get", digest], cls,
                return_value={"image": {}},
            )
            assert result.exit_code == 0, result.output
            inst.get_container_image.assert_called_once_with(digest)

    def test_image_list_rejects_unknown_sort(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "image", "list", "--sort", "severity"], cls,
            )
            assert result.exit_code == 2, result.output
            inst.list_container_images.assert_not_called()


class TestComplianceV2:
    def test_run_forwards_selectors(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "compliance", "run", "--assignment", "prod",
                 "--run-id", "2026-Q3"],
                cls, return_value={"run": {}},
            )
            assert result.exit_code == 0, result.output
            inst.create_compliance_run.assert_called_once_with(
                framework=None, assignment="prod", run_id="2026-Q3")

    def test_runs_list_and_detail(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "compliance", "runs", "--run-id", "r1"], cls,
                return_value={"run": {}, "controls": []},
            )
            assert result.exit_code == 0, result.output
            inst.list_compliance_runs.assert_called_once_with(
                run_id="r1", framework=None, assignment=None, limit=None)

    def test_attest_reads_the_body_from_a_file(self, tmp_path):
        body = {"id": "a1", "revision": 1, "control_key": "1.1",
                "outcome": "pass"}
        f = tmp_path / "att.json"
        f.write_text(json.dumps(body))
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "compliance", "attest", "--input-file", str(f),
                 "--assignment", "prod"],
                cls, return_value={"attestations": []},
            )
            assert result.exit_code == 0, result.output
            inst.create_compliance_attestation.assert_called_once_with(
                body, framework=None, assignment="prod")

    def test_attest_rejects_a_non_object_body(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "compliance", "attest", "--attestation", "[1,2]"],
                cls,
            )
            assert result.exit_code == 2, result.output
            inst.create_compliance_attestation.assert_not_called()

    def test_events_forwards_window(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "compliance", "events", "--days", "30",
                 "--limit", "500"],
                cls, return_value={"events": []},
            )
            assert result.exit_code == 0, result.output
            inst.list_compliance_events.assert_called_once_with(
                assignment=None, days=30, limit=500)

    def test_export_writes_the_decoded_document(self, tmp_path):
        """`content` is base64 on this transport — a file must hold bytes."""
        import base64 as _b64
        out = tmp_path / "run.pdf"
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            inst = MagicMock()
            cls.return_value = inst
            inst.export_compliance_run.return_value = {
                "format": "pdf",
                "content": _b64.b64encode(b"%PDF-1.4 body").decode(),
                "filename": "compliance-r1.pdf",
            }
            runner = CliRunner()
            result = runner.invoke(cli, [
                "cloudsec", "compliance", "export", "--run-id", "r1",
                "--format", "pdf", "-o", str(out),
            ])
            assert result.exit_code == 0, result.output
            assert out.read_bytes() == b"%PDF-1.4 body"

    def test_export_without_output_prints_the_envelope(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "compliance", "export", "--run-id", "r1"], cls,
                return_value={"format": "json", "content": "e30=",
                              "filename": "compliance-r1.json"},
            )
            assert result.exit_code == 0, result.output
            assert json.loads(result.output)["filename"] == \
                "compliance-r1.json"
            inst.export_compliance_run.assert_called_once_with(
                "r1", fmt=None, brand=None)

    def test_export_rejects_an_unknown_format(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "compliance", "export", "--run-id", "r1",
                 "--format", "html"],
                cls,
            )
            assert result.exit_code == 2, result.output
            inst.export_compliance_run.assert_not_called()

    def test_schedule_set_reads_the_body(self, tmp_path):
        body = {"id": "s1", "assignment": "prod", "framework_id": "cis-aws",
                "owner": "a@b.c", "cadence": "weekly", "delivery": "output",
                "destination_ref": "output://soc", "formats": ["pdf"],
                "next_run_at": "2026-10-01T00:00:00Z", "revision": 1}
        f = tmp_path / "sched.json"
        f.write_text(json.dumps(body))
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "compliance", "schedule-set", "--input-file",
                 str(f)],
                cls, return_value={"schedules": []},
            )
            assert result.exit_code == 0, result.output
            inst.set_compliance_schedule.assert_called_once_with(body)


class TestAzureScopeHierarchy:
    def test_scope_hierarchy(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(
                ["cloudsec", "azure", "scope-hierarchy"], cls,
                return_value={"edges": [], "traversable": False},
            )
            assert result.exit_code == 0, result.output
            inst.get_azure_scope_hierarchy.assert_called_once_with()


class TestIaCSelectors:
    @pytest.mark.parametrize('command,method', [
        (['finding', 'list'], 'list_findings'),
        (['finding', 'facets'], 'get_finding_facets'),
        (['finding', 'causes'], 'list_finding_causes'),
        (['export', 'findings'], 'export_findings_csv'),
    ])
    def test_finding_flags(self, command, method):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(['cloudsec', *command, '--no-has-iac-origin', '--iac-attribution', 'unknown'], cls)
            assert result.exit_code == 0, result.output
            kwargs = getattr(inst, method).call_args.kwargs
            assert kwargs['has_iac_origin'] is False
            assert kwargs['iac_attribution'] == ['unknown']

    @pytest.mark.parametrize('command,method', [
        (['inventory', 'list'], 'list_inventory'),
        (['inventory', 'facets'], 'get_inventory_facets'),
        (['export', 'inventory'], 'export_inventory_csv'),
    ])
    def test_inventory_flags(self, command, method):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(['cloudsec', *command, '--no-has-iac-origin'], cls)
            assert result.exit_code == 0, result.output
            assert getattr(inst, method).call_args.kwargs['has_iac_origin'] is False

    def test_unknown_verdict_refused(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3 as cls:
            result, inst = _invoke(['cloudsec', 'finding', 'list', '--iac-attribution', 'safe'], cls)
            assert result.exit_code != 0
            inst.list_findings.assert_not_called()


class TestProvenanceCommands:
    def test_push_preserves_bytes(self, tmp_path):
        document = tmp_path / "provenance.json"
        raw = b'{ "schema" : "lc-build-provenance/v1" }'
        document.write_bytes(raw)
        with _patches()[0], _patches()[1], _patches()[2] as mock:
            result, instance = _invoke(["cloudsec", "code", "provenance", "push", "-f", str(document)], mock)
        assert result.exit_code == 0, result.output
        instance.push_code_provenance.assert_called_once_with(raw)

    def test_push_bounds_before_client(self, tmp_path):
        document = tmp_path / "too-large.json"
        document.write_bytes(b"x" * ((1 << 20) + 1))
        with _patches()[0], _patches()[1], _patches()[2] as mock:
            result, instance = _invoke(["cloudsec", "code", "provenance", "push", "-f", str(document)], mock)
        assert result.exit_code != 0
        instance.push_code_provenance.assert_not_called()
