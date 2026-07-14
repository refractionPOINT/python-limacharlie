"""Tests for limacharlie.sdk.cloudsec module."""

import json

from unittest.mock import MagicMock

import pytest

from limacharlie.sdk.cloudsec import CloudSec


OID = "11111111-2222-3333-4444-555555555555"


@pytest.fixture
def mock_org():
    org = MagicMock()
    org.oid = OID
    org.client = MagicMock()
    return org


@pytest.fixture
def cs(mock_org):
    return CloudSec(mock_org)


def _get_call(mock_org):
    """Pull (url, query_pairs) out of a mocked GET client.request call."""
    args, kwargs = mock_org.client.request.call_args
    assert args[0] == "GET"
    return args[1], kwargs.get("query_params")


def _post_call(mock_org):
    """Pull (url, decoded_json_body) out of a mocked POST client.request call."""
    args, kwargs = mock_org.client.request.call_args
    assert args[0] == "POST"
    assert kwargs["content_type"] == "application/json"
    return args[1], json.loads(kwargs["raw_body"])


class TestBasics:
    def test_oid_property(self, cs):
        assert cs.oid == OID

    def test_get_omits_empty_query(self, cs, mock_org):
        mock_org.client.request.return_value = {"chokepoints": []}
        cs.list_chokepoints()
        url, qp = _get_call(mock_org)
        assert url == f"cloudsec/{OID}/chokepoints"
        assert qp is None


class TestFindings:
    def test_list_findings_defaults(self, cs, mock_org):
        mock_org.client.request.return_value = {"findings": []}
        cs.list_findings()
        url, qp = _get_call(mock_org)
        assert url == f"cloudsec/{OID}/findings"
        assert qp is None

    def test_list_findings_all_selectors(self, cs, mock_org):
        mock_org.client.request.return_value = {}
        cs.list_findings(
            severity=["CRITICAL", "HIGH"],
            finding_class=["toxic_combination"],
            status=["open"],
            account=["acct-1"],
            reachable=True,
            kev=False,
            q="prod",
            sort="lc_risk",
            order="desc",
            cursor="c1",
            limit=50,
        )
        _, qp = _get_call(mock_org)
        # Repeatable keys appear once per value; booleans are lowered.
        assert qp == [
            ("severity", "CRITICAL"),
            ("severity", "HIGH"),
            ("finding_class", "toxic_combination"),
            ("status", "open"),
            ("account", "acct-1"),
            ("reachable", "true"),
            ("kev", "false"),
            ("q", "prod"),
            ("sort", "lc_risk"),
            ("order", "desc"),
            ("cursor", "c1"),
            ("limit", "50"),
        ]

    def test_finding_facets_takes_filters_only(self, cs, mock_org):
        mock_org.client.request.return_value = {}
        cs.get_finding_facets(severity=["LOW"], kev=True)
        url, qp = _get_call(mock_org)
        assert url == f"cloudsec/{OID}/findings/facets"
        assert qp == [("severity", "LOW"), ("kev", "true")]

    def test_get_finding(self, cs, mock_org):
        mock_org.client.request.return_value = {"finding": {}}
        cs.get_finding("fnd_abc")
        url, qp = _get_call(mock_org)
        assert url == f"cloudsec/{OID}/findings/fnd_abc"
        assert qp is None


class TestFindingWrites:
    def test_set_finding_status(self, cs, mock_org):
        mock_org.client.request.return_value = {"ok": True}
        cs.set_finding_status(
            "fnd_abc", "accepted", reason="known", expires_at=1767225600,
        )
        url, body = _post_call(mock_org)
        assert url == f"cloudsec/{OID}/findings/fnd_abc/status"
        assert body == {"resolution": {
            "kind": "accepted", "reason": "known", "expires_at": 1767225600,
        }}

    def test_set_finding_status_reopen_omits_optionals(self, cs, mock_org):
        mock_org.client.request.return_value = {"ok": True}
        cs.set_finding_status("fnd_abc", "open")
        _, body = _post_call(mock_org)
        assert body == {"resolution": {"kind": "open"}}

    def test_bulk_set_finding_status(self, cs, mock_org):
        mock_org.client.request.return_value = {"updated": 2}
        cs.bulk_set_finding_status(["fnd_a", "fnd_b"], "mitigated", reason="fixed")
        url, body = _post_call(mock_org)
        assert url == f"cloudsec/{OID}/findings/bulk/status"
        assert body == {
            "finding_ids": ["fnd_a", "fnd_b"],
            "resolution": {"kind": "mitigated", "reason": "fixed"},
        }

    def test_set_finding_owner_empty_clears(self, cs, mock_org):
        mock_org.client.request.return_value = {"ok": True}
        cs.set_finding_owner("fnd_abc", "")
        url, body = _post_call(mock_org)
        assert url == f"cloudsec/{OID}/findings/fnd_abc/owner"
        assert body == {"owner": ""}

    def test_set_finding_ticket(self, cs, mock_org):
        mock_org.client.request.return_value = {"ok": True}
        cs.set_finding_ticket("fnd_abc", "JIRA-123")
        url, body = _post_call(mock_org)
        assert url == f"cloudsec/{OID}/findings/fnd_abc/ticket"
        assert body == {"ticket": "JIRA-123"}


class TestAttackPathsAndCiem:
    def test_list_attack_paths_selectors(self, cs, mock_org):
        mock_org.client.request.return_value = {"paths": []}
        cs.list_attack_paths(severity=["CRITICAL"], q="db")
        url, qp = _get_call(mock_org)
        assert url == f"cloudsec/{OID}/attack-paths"
        assert qp == [("severity", "CRITICAL"), ("q", "db")]

    def test_public_access(self, cs, mock_org):
        mock_org.client.request.return_value = {"access": []}
        cs.get_public_access()
        url, _ = _get_call(mock_org)
        assert url == f"cloudsec/{OID}/ciem/public-access"

    def test_identity_facets(self, cs, mock_org):
        mock_org.client.request.return_value = {"facets": {}}
        cs.get_identity_facets()
        url, _ = _get_call(mock_org)
        assert url == f"cloudsec/{OID}/ciem/facets"


class TestInventoryAndResources:
    def test_list_inventory_maps_type_selector(self, cs, mock_org):
        mock_org.client.request.return_value = {"resources": []}
        cs.list_inventory(resource_type="gcp_bucket", region="us-central1", limit=10)
        url, qp = _get_call(mock_org)
        assert url == f"cloudsec/{OID}/inventory"
        # resource_type is sent as the gateway's `type` selector.
        assert qp == [
            ("type", "gcp_bucket"), ("region", "us-central1"), ("limit", "10"),
        ]

    def test_list_inventory_provider_selector(self, cs, mock_org):
        mock_org.client.request.return_value = {"resources": []}
        cs.list_inventory(provider="okta")
        url, qp = _get_call(mock_org)
        assert url == f"cloudsec/{OID}/inventory"
        assert qp == [("provider", "okta")]

    def test_inventory_facets(self, cs, mock_org):
        mock_org.client.request.return_value = {}
        cs.get_inventory_facets()
        url, _ = _get_call(mock_org)
        assert url == f"cloudsec/{OID}/inventory/facets"

    def test_data_security_facets(self, cs, mock_org):
        mock_org.client.request.return_value = {}
        cs.get_data_security_facets()
        url, _ = _get_call(mock_org)
        assert url == f"cloudsec/{OID}/data-security/facets"

    def test_get_resource(self, cs, mock_org):
        mock_org.client.request.return_value = {"resource": None}
        cs.get_resource("lcrn:x")
        url, qp = _get_call(mock_org)
        assert url == f"cloudsec/{OID}/resource"
        assert qp == [("urn", "lcrn:x")]


class TestGraphAndQueries:
    def test_graph_neighbors(self, cs, mock_org):
        mock_org.client.request.return_value = {"graph": {}}
        cs.get_graph_neighbors("lcrn:x", limit=500)
        url, qp = _get_call(mock_org)
        assert url == f"cloudsec/{OID}/graph/neighbors"
        assert qp == [("urn", "lcrn:x"), ("limit", "500")]

    def test_list_queries(self, cs, mock_org):
        mock_org.client.request.return_value = {"queries": []}
        cs.list_queries()
        url, _ = _get_call(mock_org)
        assert url == f"cloudsec/{OID}/queries"

    def test_run_query_named(self, cs, mock_org):
        mock_org.client.request.return_value = {"rows": []}
        cs.run_query(named="public-buckets")
        url, body = _post_call(mock_org)
        assert url == f"cloudsec/{OID}/query"
        assert body == {"named": "public-buckets"}

    def test_run_query_dsl_with_projection(self, cs, mock_org):
        mock_org.client.request.return_value = {"rows": []}
        cs.run_query(query={"match": "x"}, project=["a", "b"])
        _, body = _post_call(mock_org)
        assert body == {"query": {"match": "x"}, "project": ["a", "b"]}


class TestCompliance:
    def test_report_default(self, cs, mock_org):
        mock_org.client.request.return_value = {"report": {}}
        cs.get_compliance()
        url, qp = _get_call(mock_org)
        assert url == f"cloudsec/{OID}/compliance"
        assert qp is None

    def test_report_assignment(self, cs, mock_org):
        mock_org.client.request.return_value = {"report": {}}
        cs.get_compliance(assignment="prod-scope")
        _, qp = _get_call(mock_org)
        assert qp == [("assignment", "prod-scope")]

    def test_frameworks_and_assignments(self, cs, mock_org):
        mock_org.client.request.return_value = {}
        cs.list_compliance_frameworks()
        assert _get_call(mock_org)[0] == f"cloudsec/{OID}/compliance/frameworks"
        cs.list_compliance_assignments()
        assert _get_call(mock_org)[0] == f"cloudsec/{OID}/compliance/assignments"


class TestOverviewTrendsChokepoints:
    def test_overview_trend_days(self, cs, mock_org):
        mock_org.client.request.return_value = {"score": 0}
        cs.get_overview(trend_days=90)
        url, qp = _get_call(mock_org)
        assert url == f"cloudsec/{OID}/overview"
        assert qp == [("trend_days", "90")]

    def test_changes_limit(self, cs, mock_org):
        mock_org.client.request.return_value = {"changes": []}
        cs.list_changes(limit=100)
        url, qp = _get_call(mock_org)
        assert url == f"cloudsec/{OID}/changes"
        assert qp == [("limit", "100")]

    def test_risk_trend(self, cs, mock_org):
        mock_org.client.request.return_value = {"trend": []}
        cs.get_risk_trend()
        url, qp = _get_call(mock_org)
        assert url == f"cloudsec/{OID}/risk-trend"
        assert qp is None

    def test_scan_status_provider(self, cs, mock_org):
        mock_org.client.request.return_value = {"status": {}}
        cs.get_scan_status(provider="aws")
        url, qp = _get_call(mock_org)
        assert url == f"cloudsec/{OID}/scan-status"
        assert qp == [("provider", "aws")]

    def test_scan_status_provider_is_case_normalized(self, cs, mock_org):
        # The backend scan-state read is a case-sensitive lookup keyed on
        # lowercase provider ids; "AWS" would silently read as never-scanned.
        mock_org.client.request.return_value = {"status": {}}
        cs.get_scan_status(provider=" AWS ")
        _, qp = _get_call(mock_org)
        assert qp == [("provider", "aws")]

    def test_dismiss_chokepoint_with_reason(self, cs, mock_org):
        mock_org.client.request.return_value = {"ok": True}
        cs.dismiss_chokepoint("lcrn:x", reason="decom")
        url, body = _post_call(mock_org)
        assert url == f"cloudsec/{OID}/chokepoints/dismiss"
        assert body == {"urn": "lcrn:x", "reason": "decom"}

    def test_restore_chokepoint(self, cs, mock_org):
        mock_org.client.request.return_value = {"ok": True}
        cs.restore_chokepoint("lcrn:x")
        url, body = _post_call(mock_org)
        assert url == f"cloudsec/{OID}/chokepoints/restore"
        assert body == {"urn": "lcrn:x"}


class TestResolution:
    def test_resolve_sensors_bulk(self, cs, mock_org):
        mock_org.client.request.return_value = {"resolved": []}
        cs.resolve_sensors(["sid-1", "sid-2"])
        url, qp = _get_call(mock_org)
        assert url == f"cloudsec/{OID}/resolve/sensors"
        assert qp == [("sid", "sid-1"), ("sid", "sid-2")]

    def test_resolve_assets_bulk(self, cs, mock_org):
        mock_org.client.request.return_value = {"resolved": []}
        cs.resolve_assets(["lcrn:a", "lcrn:b"])
        url, qp = _get_call(mock_org)
        assert url == f"cloudsec/{OID}/resolve/assets"
        assert qp == [("urn", "lcrn:a"), ("urn", "lcrn:b")]

    def test_resolve_sensors_chunks_large_batches(self, cs, mock_org):
        # Ids ride as repeated query params, so large batches must be
        # split to stay within the ~8KB URL limit, and the per-chunk
        # responses merged.
        sids = [f"sid-{i}" for i in range(250)]
        mock_org.client.request.side_effect = [
            {"resolved": [{"sid": "a"}], "unresolved": ["x"]},
            {"resolved": [{"sid": "b"}], "unresolved": []},
            {"resolved": [], "unresolved": ["y"]},
        ]
        out = cs.resolve_sensors(sids)
        calls = mock_org.client.request.call_args_list
        assert len(calls) == 3
        sent = [kwargs["query_params"] for _, kwargs in calls]
        assert [len(qp) for qp in sent] == [100, 100, 50]
        # Every id is sent exactly once, in order.
        assert [v for qp in sent for _, v in qp] == sids
        assert out == {
            "resolved": [{"sid": "a"}, {"sid": "b"}],
            "unresolved": ["x", "y"],
        }

    def test_resolve_assets_empty_batch_makes_no_request(self, cs, mock_org):
        out = cs.resolve_assets([])
        mock_org.client.request.assert_not_called()
        assert out == {"resolved": [], "unresolved": []}


class TestCaasm:
    def test_list_assets(self, cs, mock_org):
        mock_org.client.request.return_value = {"resources": []}
        cs.list_caasm_assets(q="laptop", limit=50)
        url, qp = _get_call(mock_org)
        assert url == f"cloudsec/{OID}/caasm/assets"
        assert qp == [("q", "laptop"), ("limit", "50")]

    def test_list_coverage(self, cs, mock_org):
        mock_org.client.request.return_value = {"findings": []}
        cs.list_caasm_coverage(status=["open"], severity=["HIGH"], cursor="c")
        url, qp = _get_call(mock_org)
        assert url == f"cloudsec/{OID}/caasm/coverage"
        assert qp == [("status", "open"), ("severity", "HIGH"), ("cursor", "c")]

    def test_policy_get(self, cs, mock_org):
        mock_org.client.request.return_value = {"resources": []}
        cs.get_caasm_policy()
        url, _ = _get_call(mock_org)
        assert url == f"cloudsec/{OID}/caasm/policy"

    def test_policy_set(self, cs, mock_org):
        mock_org.client.request.return_value = {"ok": True}
        policy = {"expect": [{"label": "edr", "capability": "edr", "kinds": ["device"]}]}
        cs.set_caasm_policy(policy)
        url, body = _post_call(mock_org)
        assert url == f"cloudsec/{OID}/caasm/policy"
        assert body == {"policy": policy}

    def test_ingest_records(self, cs, mock_org):
        mock_org.client.request.return_value = {"result": {}}
        cs.caasm_ingest("okta", records=[{"id": "u1"}])
        url, body = _post_call(mock_org)
        assert url == f"cloudsec/{OID}/caasm/ingest"
        assert body == {"source": "okta", "records": [{"id": "u1"}]}

    def test_ingest_single_record(self, cs, mock_org):
        mock_org.client.request.return_value = {"result": {}}
        cs.caasm_ingest("crowdstrike", record={"device_id": "d1"})
        _, body = _post_call(mock_org)
        assert body == {"source": "crowdstrike", "record": {"device_id": "d1"}}


class TestProvider:
    def test_test_provider(self, cs, mock_org):
        mock_org.client.request.return_value = {"supported": True, "report": {}}
        provider = {"provider_type": "gcp", "credentials": "hive://secret/gcp-sa"}
        cs.test_provider(provider)
        url, body = _post_call(mock_org)
        assert url == f"cloudsec/{OID}/providers/test"
        assert body == {"provider": provider}

    def test_provider_manifests_all(self, cs, mock_org):
        mock_org.client.request.return_value = {"manifests": []}
        cs.get_provider_manifests()
        url, qp = _get_call(mock_org)
        assert url == f"cloudsec/{OID}/providers/manifest"
        assert qp is None

    def test_provider_manifests_single(self, cs, mock_org):
        mock_org.client.request.return_value = {"manifest": {}}
        cs.get_provider_manifests(provider_type="gcp")
        url, qp = _get_call(mock_org)
        assert url == f"cloudsec/{OID}/providers/manifest"
        assert qp == [("type", "gcp")]


class TestFleetOverview:
    def test_fleet_overview_user_creds_request_scoped_token(self, cs, mock_org):
        client = mock_org.client
        client._uid = "user-1"
        client._oauth_creds = None
        client._jwt = "org-scoped-jwt"
        client.mint_jwt.return_value = "multi-org-jwt"
        client.request.return_value = {"orgs": [], "next_cursor": ""}
        cs.get_fleet_overview(oids=["o1", "o2"], group="g1", limit=50, trend_days=90)
        # A multi-org JWT is minted (pure mint, no client-state mutation)...
        client.mint_jwt.assert_called_once_with()
        client.refresh_jwt.assert_not_called()
        args, kwargs = client.request.call_args
        # ...and sent as a request-scoped Authorization header against the
        # NON-oid-scoped fleet path, bypassing the client's own JWT.
        assert args == ("GET", "cloudsec/fleet/overview")
        assert kwargs["is_no_auth"] is True
        assert kwargs["extra_headers"] == {"Authorization": "Bearer multi-org-jwt"}
        assert kwargs["query_params"] == [
            ("oids", "o1"), ("oids", "o2"), ("group", "g1"),
            ("limit", "50"), ("trend_days", "90"),
        ]
        # The client's own JWT was never touched.
        assert client._jwt == "org-scoped-jwt"

    def test_fleet_overview_token_cached_across_pages(self, cs, mock_org):
        client = mock_org.client
        client._uid = "user-1"
        client._oauth_creds = None
        client.mint_jwt.return_value = "multi-org-jwt"
        client.request.return_value = {"orgs": [], "next_cursor": "c2"}
        cs.get_fleet_overview()
        cs.get_fleet_overview(cursor="c2")
        # One mint serves the whole paged sweep.
        client.mint_jwt.assert_called_once_with()
        assert client.request.call_count == 2

    def test_fleet_overview_401_reminted_once(self, cs, mock_org):
        from limacharlie.errors import AuthenticationError
        client = mock_org.client
        client._uid = "user-1"
        client._oauth_creds = None
        client.mint_jwt.side_effect = ["stale-jwt", "fresh-jwt"]
        client.request.side_effect = [
            AuthenticationError("401"), {"orgs": []},
        ]
        out = cs.get_fleet_overview()
        assert out == {"orgs": []}
        # The 401 re-minted the MULTI-ORG token (not the client's org-scoped
        # refresh) and retried with it.
        assert client.mint_jwt.call_count == 2
        assert client.request.call_args[1]["extra_headers"] == {
            "Authorization": "Bearer fresh-jwt",
        }
        client.refresh_jwt.assert_not_called()

    def test_fleet_overview_persistent_401_raises(self, cs, mock_org):
        from limacharlie.errors import AuthenticationError
        client = mock_org.client
        client._uid = "user-1"
        client._oauth_creds = None
        client.mint_jwt.return_value = "multi-org-jwt"
        client.request.side_effect = AuthenticationError("401")
        with pytest.raises(AuthenticationError):
            cs.get_fleet_overview()
        # The cached token was dropped so the next call starts fresh.
        assert cs._fleet_jwt is None

    def test_fleet_overview_org_key_uses_current_jwt(self, cs, mock_org):
        client = mock_org.client
        client._uid = None
        client._oauth_creds = None
        client.request.return_value = {"orgs": []}
        cs.get_fleet_overview()
        client.mint_jwt.assert_not_called()
        client.refresh_jwt.assert_not_called()
        args, kwargs = client.request.call_args
        assert args == ("GET", "cloudsec/fleet/overview")
        assert kwargs["query_params"] is None

    def test_fleet_overview_all_orgs_opt_out(self, cs, mock_org):
        client = mock_org.client
        client._uid = "user-1"
        client._oauth_creds = None
        client.request.return_value = {"orgs": []}
        cs.get_fleet_overview(all_orgs=False)
        client.mint_jwt.assert_not_called()
        client.refresh_jwt.assert_not_called()


class TestCsvExports:
    def test_export_findings_csv(self, cs, mock_org):
        mock_org.client.request.return_value = "col_a,col_b\n1,2\n"
        out = cs.export_findings_csv(severity=["CRITICAL"], status=["open"], q="prod")
        args, kwargs = mock_org.client.request.call_args
        assert args == ("GET", f"cloudsec/{OID}/findings")
        assert kwargs["query_params"] == [
            ("severity", "CRITICAL"), ("status", "open"), ("q", "prod"),
            ("format", "csv"),
        ]
        assert kwargs["raw_response"] is True
        assert out == "col_a,col_b\n1,2\n"

    def test_export_inventory_csv(self, cs, mock_org):
        mock_org.client.request.return_value = "urn\n"
        cs.export_inventory_csv(resource_type="Bucket", provider="gcp")
        args, kwargs = mock_org.client.request.call_args
        assert args == ("GET", f"cloudsec/{OID}/inventory")
        assert kwargs["query_params"] == [
            ("type", "Bucket"), ("provider", "gcp"), ("format", "csv"),
        ]
        assert kwargs["raw_response"] is True

    def test_export_compliance_csv(self, cs, mock_org):
        mock_org.client.request.return_value = "control\n"
        cs.export_compliance_csv(framework="cis-aws")
        args, kwargs = mock_org.client.request.call_args
        assert args == ("GET", f"cloudsec/{OID}/compliance")
        assert kwargs["query_params"] == [
            ("framework", "cis-aws"), ("format", "csv"),
        ]
        assert kwargs["raw_response"] is True

    def test_export_query_csv(self, cs, mock_org):
        mock_org.client.request.return_value = "a\n"
        cs.export_query_csv(named="public-buckets")
        args, kwargs = mock_org.client.request.call_args
        assert args == ("POST", f"cloudsec/{OID}/query")
        assert kwargs["query_params"] == [("format", "csv")]
        assert json.loads(kwargs["raw_body"]) == {"named": "public-buckets"}
        assert kwargs["raw_response"] is True
