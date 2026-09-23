"""Tests for the Code Security evidence chain, coverage and remediation surface.

The fixtures under ``fixtures/evidence-chain`` are byte-identical copies of the
server's own pinned wire bodies. ``counts.json`` is the one query the API, the
web app and this CLI must all report identically; its hash is pinned below so a
copy that drifts from the server's fixture fails here.
"""

import hashlib
import json
import os
import re
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from limacharlie.cli import cli
from limacharlie.sdk.cloudsec import (
    ASSERTIVE_OUTCOMES,
    CHAIN_STAGES,
    CloudSec,
    chain_stage_summary,
    coverage_percent,
    coverage_summary,
)

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "evidence-chain")
COUNTS_SHA256 = "35f587893d633f8aec4b959f736b58adaa5f2a4a05ae25fc0cfc7203582a7824"
OID = "b85fd2bd-ae21-4c1f-8a42-b90b51aeddeb"
FID = "fnd_0123456789abcdef0123456789abcdef"
RID = "rem_" + "c" * 32


def _load(name):
    with open(os.path.join(FIXTURES, name), "rb") as f:
        raw = f.read()
    return raw, json.loads(raw)


def _org():
    org = MagicMock()
    org.oid = OID
    org.client.request.return_value = {}
    return org


# ---------------------------------------------------------------------------
# The shared count fixture
# ---------------------------------------------------------------------------


def test_count_fixture_is_the_servers_byte_for_byte():
    raw, _ = _load("counts.json")
    assert hashlib.sha256(raw).hexdigest() == COUNTS_SHA256


def _invoke(args, **returns):
    with patch("limacharlie.commands.cloudsec.Client"), \
            patch("limacharlie.commands.cloudsec.Organization"), \
            patch("limacharlie.commands.cloudsec.CloudSec") as cls:
        inst = MagicMock()
        inst.oid = OID
        cls.return_value = inst
        for name, value in returns.items():
            getattr(inst, name).return_value = value
        result = CliRunner().invoke(cli, ["--output", "json"] + args)
    return result, inst


def test_cli_counts_agree_with_the_api_for_one_query():
    """The CLI prints the server's counts for the fixture's query, never a count of rows.

    The fixture's findings page holds 2 rows of a total of 7. A CLI that counted what it
    loaded would print 2.
    """
    _, fx = _load("counts.json")
    expected = fx["expected"]

    result, inst = _invoke(["cloudsec", "finding", "facets", "--has-iac-origin", "--severity", "HIGH"],
                           get_finding_facets=fx["findings_facets"])
    assert result.exit_code == 0, result.output
    assert inst.get_finding_facets.call_args.kwargs["has_iac_origin"] is True
    assert inst.get_finding_facets.call_args.kwargs["severity"] == ["HIGH"]
    assert json.loads(result.output)["facets"]["total"] == expected["findings_total"]
    assert expected["findings_total"] != expected["findings_page_rows"]

    result, _ = _invoke(["cloudsec", "code", "coverage", "--summary"], get_code_coverage=fx["code_coverage"])
    assert result.exit_code == 0, result.output
    rows = json.loads(result.output)["coverage"]
    assert [(r["metric"], r["numerator"], r["denominator"]) for r in rows] == \
        [(e["metric"], e["numerator"], e["denominator"]) for e in expected["coverage"]]

    result, _ = _invoke(["cloudsec", "finding", "chain", FID, "--summary"], get_finding_evidence_chain=fx["evidence_chain"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["gaps"] == expected["chain_gaps"]


# ---------------------------------------------------------------------------
# Coverage: a percentage only on a clean line
# ---------------------------------------------------------------------------


def test_coverage_percent_only_on_clean_lines():
    _, fx = _load("counts.json")
    lines = fx["code_coverage"]["coverage"]["lines"]
    shown = {l["metric"]: coverage_percent(l) for l in lines}
    assert shown["workloads_with_digest"] == pytest.approx(80.0)
    assert shown["remediation_outcomes"] == pytest.approx(60.0)
    # Unmeasured metrics are null, never 0 of 0, and never a percentage.
    assert shown["pr_context_success"] is None
    unmeasured = next(l for l in lines if l["metric"] == "pr_context_success")
    assert unmeasured["numerator"] is None and unmeasured["denominator"] is None
    assert unmeasured["reason"] and unmeasured["action"]


@pytest.mark.parametrize("fixture,metric,reason", [
    ("mssp-2.json", "workloads_with_digest", "coverage_incomplete"),
    ("mssp-4.json", "workloads_with_digest", "no_denominator"),
])
def test_coverage_hides_the_percentage_and_says_why(fixture, metric, reason):
    _, body = _load(fixture)
    rows = {r["metric"]: r for r in coverage_summary(body)}
    assert rows[metric]["percent"] is None
    assert rows[metric]["reason"] == reason
    assert rows[metric]["action"]


@pytest.mark.parametrize("line", [
    {"numerator": 5, "denominator": 5, "complete": False},
    {"numerator": 5, "denominator": 5, "complete": True, "truncated": True},
    {"numerator": 5, "denominator": 5, "complete": True, "reason": "coverage_stale"},
    {"numerator": 0, "denominator": 0, "complete": True},
    {"numerator": None, "denominator": None, "complete": False},
    {"numerator": 6, "denominator": 5, "complete": True},
    {"numerator": True, "denominator": 1, "complete": True},
])
def test_coverage_percent_refuses_anything_unclean(line):
    assert coverage_percent(line) is None


# ---------------------------------------------------------------------------
# Chain: verbatim reasons, no reassurance on a gap
# ---------------------------------------------------------------------------


def test_an_unrecognised_reason_is_shown_verbatim():
    _, body = _load("secops-7.json")
    observed = next(r for r in chain_stage_summary(body) if r["stage"] == "observed")
    assert observed["reason"] == "sensor_quarantined"
    assert observed["reason_recognised"] is False
    assert observed["action"] == "review_reason"


def test_every_stage_is_listed_and_every_gap_has_an_action():
    for name in ("secops-7.json", "appsec-8.json", "cloud-1.json"):
        _, body = _load(name)
        rows = chain_stage_summary(body)
        assert [r["stage"] for r in rows] == list(CHAIN_STAGES)
        for r in rows:
            if r["status"] in ("partial", "unknown"):
                assert r["reason"] and r["action"], (name, r)


def test_an_assertive_outcome_on_a_gap_is_never_displayed():
    _, body = _load("appsec-8.json")
    stages = {s["stage"]: s for s in body["chain"]["stages"]}
    # appsec-8: the run says verified but the finding is open again.
    assert stages["verified"]["status"] == "partial"
    tampered = json.loads(json.dumps(body))
    for s in tampered["chain"]["stages"]:
        if s["stage"] == "verified":
            s["outcome"] = "verified"
    row = next(r for r in chain_stage_summary(tampered) if r["stage"] == "verified")
    assert row["outcome"] == ""
    assert "verified" in ASSERTIVE_OUTCOMES["verified"]


def test_cli_chain_prints_the_full_response_by_default():
    _, body = _load("secops-7.json")
    result, inst = _invoke(["cloudsec", "finding", "chain", FID, "--runtime"], get_finding_evidence_chain=body)
    assert result.exit_code == 0, result.output
    inst.get_finding_evidence_chain.assert_called_once_with(FID, runtime=True)
    assert "sensor_quarantined" in result.output


# ---------------------------------------------------------------------------
# SDK transport
# ---------------------------------------------------------------------------


def test_sdk_routes():
    org = _org()
    cs = CloudSec(org)
    cs.get_finding_evidence_chain(FID)
    assert org.client.request.call_args.args[:2] == ("GET", f"cloudsec/{OID}/findings/{FID}/evidence-chain")
    assert org.client.request.call_args.kwargs["query_params"] is None
    cs.get_finding_evidence_chain(FID, runtime=True)
    assert org.client.request.call_args.kwargs["query_params"] == [("runtime", "true")]
    cs.get_code_coverage()
    assert org.client.request.call_args.args[:2] == ("GET", f"cloudsec/{OID}/code/coverage")
    cs.get_code_impact(finding_id=FID)
    assert org.client.request.call_args.kwargs["query_params"] == [("finding_id", FID)]
    cs.list_remediations(finding_id=FID)
    assert org.client.request.call_args.args[1] == f"cloudsec/{OID}/remediations"
    cs.create_remediation(FID, "open_fix_pr", "k-1")
    call = org.client.request.call_args
    assert call.args[:2] == ("POST", f"cloudsec/{OID}/findings/{FID}/remediations")
    assert json.loads(call.kwargs["raw_body"]) == {"action": "open_fix_pr", "idempotency_key": "k-1"}
    cs.decide_remediation(RID, "approve", 3, "d" * 64)
    call = org.client.request.call_args
    assert call.args[1] == f"cloudsec/{OID}/remediations/{RID}/approve"
    assert json.loads(call.kwargs["raw_body"]) == {"generation": 3, "scope_digest": "d" * 64}
    cs.decide_remediation(RID, "cancel", 3)
    assert json.loads(org.client.request.call_args.kwargs["raw_body"]) == {"generation": 3}


@pytest.mark.parametrize("call", [
    lambda cs: cs.get_finding_evidence_chain(".."),
    lambda cs: cs.get_finding_evidence_chain("fnd_a/../b"),
    lambda cs: cs.get_remediation("../status"),
    lambda cs: cs.create_remediation("fnd_x", "open_fix_pr", "k"),
    lambda cs: cs.decide_remediation(RID, "merge", 1),
    lambda cs: cs.decide_remediation(RID, "approve", 1),
    lambda cs: cs.decide_remediation(RID, "cancel", -1),
    lambda cs: cs.decide_remediation(RID, "cancel", True),
    lambda cs: cs.decide_remediation("rem_x", "cancel", 1),
    lambda cs: cs.get_code_impact(),
    lambda cs: cs.get_code_impact(repo_urn="lcrn:x", finding_id=FID),
    lambda cs: cs.get_code_impact(commit="a" * 40),
])
def test_sdk_refuses_before_any_request(call):
    org = _org()
    with pytest.raises(ValueError):
        call(CloudSec(org))
    assert org.client.request.call_count == 0


# ---------------------------------------------------------------------------
# Remediation decisions: review first, confirm bound to what was reviewed
# ---------------------------------------------------------------------------


def _run(state="awaiting_approval", generation=3, digest="d" * 64):
    return {"result": {"run": {
        "run_id": RID, "finding_id": FID, "action": "open_fix_pr", "state": state,
        "generation": generation, "scope_digest": digest,
        "scope": {"targets": [{"kind": "image", "urn": "lcrn:img"}], "old_digests": ["sha256:" + "1" * 64]},
        "deadline_at": "2026-09-30T00:00:00Z",
    }, "steps": []}}


def test_approve_without_confirm_sends_nothing_and_prints_the_review():
    result, inst = _invoke(["cloudsec", "remediation", "approve", RID], get_remediation=_run())
    assert result.exit_code == 0, result.output
    out = json.loads(result.output)
    assert out["review"]["targets"] == [{"kind": "image", "urn": "lcrn:img"}]
    assert out["review"]["generation"] == 3
    assert re.fullmatch(r"[0-9a-f]{16}", out["confirm"])
    inst.decide_remediation.assert_not_called()


def test_approve_with_the_reviewed_token_sends_the_reviewed_generation_and_scope():
    result, _ = _invoke(["cloudsec", "remediation", "approve", RID], get_remediation=_run())
    token = json.loads(result.output)["confirm"]
    result, inst = _invoke(["cloudsec", "remediation", "approve", RID, "--confirm", token],
                           get_remediation=_run(), decide_remediation={"result": {}})
    assert result.exit_code == 0, result.output
    inst.decide_remediation.assert_called_once_with(RID, "approve", 3, "d" * 64)


@pytest.mark.parametrize("changed", [
    _run(generation=4),
    _run(digest="e" * 64),
])
def test_a_token_stops_matching_when_the_run_changed(changed):
    result, _ = _invoke(["cloudsec", "remediation", "approve", RID], get_remediation=_run())
    token = json.loads(result.output)["confirm"]
    result, inst = _invoke(["cloudsec", "remediation", "approve", RID, "--confirm", token], get_remediation=changed)
    assert result.exit_code != 0
    inst.decide_remediation.assert_not_called()


def test_a_token_for_one_decision_does_not_authorise_another():
    result, _ = _invoke(["cloudsec", "remediation", "reject", RID], get_remediation=_run())
    token = json.loads(result.output)["confirm"]
    result, inst = _invoke(["cloudsec", "remediation", "approve", RID, "--confirm", token], get_remediation=_run())
    assert result.exit_code != 0
    inst.decide_remediation.assert_not_called()


@pytest.mark.parametrize("decision,state", [
    ("approve", "monitoring"), ("reject", "executing"), ("cancel", "verified"), ("approve", "quarantined"),
])
def test_a_run_that_cannot_take_the_decision_is_refused_locally(decision, state):
    result, inst = _invoke(["cloudsec", "remediation", decision, RID, "--confirm", "0" * 16],
                           get_remediation=_run(state=state))
    assert result.exit_code != 0
    inst.decide_remediation.assert_not_called()
