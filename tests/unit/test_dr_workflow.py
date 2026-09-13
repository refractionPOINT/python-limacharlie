import copy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from limacharlie import dr_workflow as wf


def intent(condition, event="OT_APP"):
    return {"version": 1, "event_type": event, "name": "test", "condition": condition}


def eq(path, value):
    return {"op": "eq", "path": path, "value": value}


def test_unknown_custom_fields_never_borrow_sensor_contracts():
    rule = intent(eq(["event", "DOMAIN_NAME"], "example.com"), "DNS_REQUEST")
    with pytest.raises(wf.NeedsEvidence):
        wf.schema_context(rule, [], "custom_json")
    assert (
        wf.schema_context(rule, [], "lc_sensor")["sensor_revision"]
        == wf.SENSOR_REVISION
    )


def test_ot_schema_and_same_element_scope():
    node = {
        "op": "some",
        "path": ["event", "readings"],
        "where": {
            "op": "all",
            "rules": [
                eq(["unit"], "bar"),
                {"op": "gt", "path": ["pressure"], "value": 80},
            ],
        },
    }
    i = intent(node)
    sample = {
        "routing": {"event_type": "OT_APP"},
        "event": {
            "readings": [{"unit": "bar", "pressure": 45}],
            "vendor": {"anything": True},
        },
    }
    schema = wf.schema_context(i, [sample], "custom_json")
    assert schema["kind"] == "observed_json" and schema["absence_proven"] is False
    detect = wf.compile_rule(i)["detect"]
    assert detect["path"] == "event/readings/"
    assert detect["rule"]["rules"][1]["path"] == "event/pressure"
    good = copy.deepcopy(sample)
    good["event"]["readings"] = [{"unit": "bar", "pressure": 90}]
    split = copy.deepcopy(sample)
    split["event"]["readings"] = [
        {"unit": "bar", "pressure": 45},
        {"unit": "psi", "pressure": 90},
    ]
    assert wf.matches(node, good) and not wf.matches(node, split)
    cases = wf.fixtures(i, [sample])
    assert any(c["label"] == "split-array-control" and not c["expected"] for c in cases)


def test_mixed_numeric_and_string_values_require_evidence_decision():
    i = intent({"op": "gt", "path": ["event", "temperature"], "value": 80})
    rows = [
        {"routing": {"event_type": "OT_APP"}, "event": {"temperature": v}}
        for v in [81, "81"]
    ]
    with pytest.raises(wf.NeedsEvidence, match="Mixed"):
        wf.schema_context(i, rows, "custom_json")


@pytest.mark.parametrize(
    "data,path,value",
    [
        ([1, 2], ["event"], 1),
        ({"custom field": False}, ["event", "custom field"], False),
        (42, ["event"], 42),
    ],
)
def test_custom_data_has_no_predefined_field_catalog(data, path, value):
    sample = {"routing": {"event_type": "OT_APP"}, "event": data}
    i = intent(eq(path, value))
    if isinstance(data, list):
        with pytest.raises(wf.NeedsEvidence):
            wf.schema_context(i, [sample], "custom_json")
    else:
        assert wf.schema_context(i, [sample], "custom_json")["kind"] == "observed_json"


def test_package_alternatives_are_exercised_and_source_is_not_modified():
    i = wf.package_intent(
        "java-child", {"children": ["bash", "powershell.exe"]}, "java-child"
    )
    original = copy.deepcopy(i)
    cases = wf.fixtures(i, [])
    positives = [c["event"] for c in cases if c["expected"]]
    assert {
        wf.get(e, ["event", "PARENT", "FILE_PATH"]).split("/")[-1] for e in positives
    } >= {"java", "java.exe", "javaw", "javaw.exe"}
    assert {wf.get(e, ["event", "FILE_PATH"]).split("/")[-1] for e in positives} >= {
        "bash",
        "powershell.exe",
    }
    assert i == original


@pytest.mark.parametrize(
    "bad",
    [
        {"op": "exec", "path": ["event", "x"], "value": "touch /tmp/pwned"},
        eq(["event", "x/y"], 1),
        eq(["routing", "oid"], "other"),
        {"op": "gt", "path": ["event", "x"], "value": float("nan")},
    ],
)
def test_unsupported_intents_fail_before_any_api(bad):
    with pytest.raises(ValueError):
        wf.compile_rule(intent(bad))


def test_contradictory_conditions_do_not_get_successful_fixtures():
    i = intent({"op": "all", "rules": [eq(["event", "x"], 1), eq(["event", "x"], 2)]})
    with pytest.raises(ValueError, match="Conflicting"):
        wf.fixtures(i, [])


def test_replay_disagreement_is_invalid_and_no_remote_write(tmp_path, monkeypatch):
    org = SimpleNamespace(oid="org")
    replay = Mock()
    replay._get_replay_url.return_value = "replay.invalid"
    replay.scan_events.return_value = {
        "stats": {"n_proc": 1},
        "results": [],
        "did_match": False,
    }
    monkeypatch.setattr(wf, "Replay", lambda o: replay)
    i = wf.package_intent("dns-domain", {"domain": "example.com"}, "dns")
    report = wf.build(org, tmp_path / "draft", i, source="lc_sensor")
    assert report["status"] == "invalid" and not report["deployed"]
    assert replay.scan_events.call_count == 1
    assert (
        report["schema"]["sample_count"] == 0
        and report["grounding"] == "lc_sensor_contract"
    )


def test_cross_org_evidence_rejected_before_replay(tmp_path):
    with pytest.raises(ValueError, match="different organization"):
        wf.build(
            SimpleNamespace(oid="one"),
            tmp_path / "draft",
            intent(eq(["event", "x"], 1)),
            samples=[
                {"routing": {"event_type": "OT_APP", "oid": "two"}, "event": {"x": 1}}
            ],
        )


def test_contract_recheck_reestablishes_schema_and_exact_intent(tmp_path, monkeypatch):
    from limacharlie import dr_drafting as drafting
    from limacharlie.sdk import replay as replay_module

    org = SimpleNamespace(oid="org")
    i = wf.package_intent("dns-domain", {"domain": "example.com"}, "dns")
    replay = Mock()
    replay._get_replay_url.return_value = "replay.invalid"

    def scan(events, **kwargs):
        results = [
            {"action": "report", "data": {"detect": e}}
            for e in events
            if wf.matches(i["condition"], e)
        ]
        return {
            "stats": {"n_proc": len(events)},
            "results": results,
            "did_match": bool(results),
        }

    replay.scan_events.side_effect = scan
    monkeypatch.setattr(wf, "Replay", lambda o: replay)
    monkeypatch.setattr(replay_module, "Replay", lambda o: replay)
    root = tmp_path / "draft"
    assert wf.build(org, root, i, source="lc_sensor")["status"] == "tested"
    assert drafting.check(org, root)["grounding"] == "lc_sensor_contract"
    candidate = drafting.load(root / "candidate.json")
    candidate["detect"]["path"] = "event/INVENTED"
    import json

    (root / "candidate.json").write_text(json.dumps(candidate))
    result = drafting.check(org, root)
    assert result["status"] == "invalid" and any(
        "intent" in e for e in result["errors"]
    )


@pytest.mark.parametrize("values", [[81, "81"], ["81", 81]])
def test_mixed_types_in_one_array_are_order_independent(values):
    i = intent(
        {
            "op": "some",
            "path": ["event", "readings"],
            "where": {"op": "gt", "path": ["pressure"], "value": 80},
        }
    )
    sample = {
        "routing": {"event_type": "OT_APP"},
        "event": {"readings": [{"pressure": v} for v in values]},
    }
    with pytest.raises(wf.NeedsEvidence, match="Mixed"):
        wf.schema_context(i, [sample], "custom_json")


def test_batch_checks_each_outcome_and_rejects_lost_identity(monkeypatch):
    org = SimpleNamespace(oid="org")
    cases = [
        {
            "label": str(i),
            "event": {"routing": {"event_type": "DNS_REQUEST"}, "event": {}},
            "expected": expected,
        }
        for i, expected in enumerate([True, True, False])
    ]
    replay = Mock()
    monkeypatch.setattr(wf, "Replay", lambda o: replay)

    def response(ids, n=3):
        return {
            "stats": {"n_proc": n},
            "did_match": bool(ids),
            "results": [
                {
                    "action": "report",
                    "data": {"detect": {"routing": {"lc_draft_fixture_id": i}}},
                }
                for i in ids
            ],
        }

    replay.scan_events.return_value = response([0])
    checks = wf.replay_cases(org, {}, cases)
    assert (
        "error" not in checks[0] and "error" in checks[1] and "error" not in checks[2]
    )
    replay.scan_events.return_value = response([0, 1, 2])
    assert "error" in wf.replay_cases(org, {}, cases)[2]
    for bad in (
        response([0, 0]),
        response([True]),
        response([10]),
        response([0, 1], 2),
    ):
        replay.scan_events.return_value = bad
        assert "error" in wf.replay_cases(org, {}, cases)[0]
    assert all("lc_draft_fixture_id" not in c["event"]["routing"] for c in cases)


def test_irrelevant_case_default_does_not_require_another_model_turn():
    rule = intent(
        {
            "op": "eq",
            "path": ["event", "enabled"],
            "value": False,
            "case_sensitive": False,
        }
    )
    detect = wf.compile_rule(rule)["detect"]
    assert detect["value"] is False and "case sensitive" not in detect
    rule["condition"]["case_sensitive"] = "false"
    with pytest.raises(ValueError):
        wf.compile_rule(rule)


def test_sensor_label_cannot_promote_custom_fields_into_versioned_contract():
    sample = {"routing": {"event_type": "DNS_REQUEST"}, "event": {"customer_extra": 1}}
    i = intent(eq(["event", "customer_extra"], 1), "DNS_REQUEST")
    with pytest.raises(wf.NeedsEvidence, match="outside"):
        wf.schema_context(i, [sample], "lc_sensor")
    assert wf.schema_context(i, [sample], "custom_json")["kind"] == "observed_json"
