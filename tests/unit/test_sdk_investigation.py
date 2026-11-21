"""Tests for limacharlie.sdk.investigation (Investigation Engine)."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from limacharlie.errors import (
    ApiError,
    AuthenticationError,
    ValidationError,
    error_from_status_code,
)
from limacharlie.sdk import investigation as inv_mod
from limacharlie.sdk.hive import HiveRecord
from limacharlie.sdk.investigation import (
    Investigation,
    InvestigationError,
    dump_template,
    parse_document,
    parse_template_source,
)


@pytest.fixture
def mock_org():
    org = MagicMock()
    org.oid = "oid-1"
    org.client = MagicMock()
    return org


@pytest.fixture
def inv(mock_org):
    return Investigation(mock_org)


@pytest.fixture
def hive():
    """The Hive the SDK writes templates to."""
    with patch.object(inv_mod, "Hive") as cls:
        h = MagicMock()
        cls.return_value = h
        yield h


def _not_found():
    return error_from_status_code(400, {"error": "lc_error_code:RECORD_NOT_FOUND - no such record"})


VALID = {"valid": True, "errors": [], "warnings": [{"code": "unused_step", "path": "gather.x", "message": "m"}]}
INVALID = {"valid": False, "errors": [{"code": "unknown_field", "path": "gather.a", "message": "m", "suggestion": "b"}], "warnings": []}

# The rules of a template: sentences carry {step.path} references and a `when` may be a string or a list.
RULES = {
    "escalate": [{"id": "known_bad_link", "when": ["link.known_bad", "link.clicked"], "say": "The link {link.url} is known bad."}],
    "close": [{"id": "long_history", "when": "history.days > 30", "say": "Long history."}],
}
RULES_SRC = (
    "description: test plan\nrules:\n  escalate:\n    - id: known_bad_link\n      when: [link.known_bad, link.clicked]\n"
    "      say: The link {link.url} is known bad.\n"
    "  close:\n    - id: long_history\n      when: history.days > 30\n      say: Long history.\n"
)

SRC = "description: test plan\ngather:\n  a:\n    op: entity.get\n    args: {entity_id: $entity}\n"


def _request_args(mock_org):
    call = mock_org.client.request.call_args
    return call.args[0], call.args[1], call.kwargs


# ---------------------------------------------------------------------------
# Routes and parameters
# ---------------------------------------------------------------------------

class TestRoutes:
    def test_kit_sections_are_comma_separated(self, inv, mock_org):
        mock_org.client.request.return_value = {}
        inv.get_authoring_kit(["guide", "library"])
        verb, path, kw = _request_args(mock_org)
        assert (verb, path) == ("GET", "investigate/oid-1/authoring-kit")
        assert kw["query_params"] == [("sections", "guide,library")]

    def test_kit_without_sections_sends_no_query(self, inv, mock_org):
        mock_org.client.request.return_value = {}
        inv.get_authoring_kit()
        assert _request_args(mock_org)[2]["query_params"] is None

    def test_kit_rejects_unknown_section_before_calling(self, inv, mock_org):
        with pytest.raises(ValidationError, match="nope"):
            inv.get_authoring_kit(["guide", "nope"])
        mock_org.client.request.assert_not_called()

    def test_effective_policy_sends_class_not_class_underscore(self, inv, mock_org):
        mock_org.client.request.return_value = {}
        inv.get_effective_policy(category="c", priority=3, target_tags=["a", "b"], action_class="contain.host")
        query = dict(_request_args(mock_org)[2]["query_params"])
        assert query == {"category": "c", "priority": "3", "target_tags": "a,b", "class": "contain.host"}

    def test_effective_policy_sends_the_template(self, inv, mock_org):
        mock_org.client.request.return_value = {}
        inv.get_effective_policy(template="t")
        assert dict(_request_args(mock_org)[2]["query_params"]) == {"template": "t"}

    def test_list_runs_sends_only_set_filters(self, inv, mock_org):
        mock_org.client.request.return_value = {"runs": []}
        inv.list_runs(state="running", limit=20, cursor="cur")
        verb, path, kw = _request_args(mock_org)
        assert (verb, path) == ("GET", "investigate/oid-1/runs")
        assert dict(kw["query_params"]) == {"state": "running", "limit": "20", "cursor": "cur"}

    def test_list_runs_limit_bounds(self, inv):
        with pytest.raises(ValidationError):
            inv.list_runs(limit=201)

    def test_iter_runs_follows_cursors_and_rejects_a_stuck_one(self, inv, mock_org):
        mock_org.client.request.side_effect = [
            {"runs": [{"run_id": "a"}], "next_cursor": "c1"},
            {"runs": [{"run_id": "b"}], "next_cursor": ""},
        ]
        assert [r["run_id"] for r in inv.iter_runs(state="completed")] == ["a", "b"]
        second = dict(mock_org.client.request.call_args.kwargs["query_params"])
        assert second == {"state": "completed", "cursor": "c1"}

        mock_org.client.request.side_effect = None
        mock_org.client.request.return_value = {"runs": [], "next_cursor": "same"}
        with pytest.raises(ApiError, match="did not advance"):
            list(inv.iter_runs(cursor="same"))

    def test_iter_actions_follows_cursors_and_rejects_a_stuck_one(self, inv, mock_org):
        mock_org.client.request.side_effect = [
            {"actions": [{"id": "a"}], "next_cursor": "c1"},
            {"actions": [{"id": "b"}], "next_cursor": ""},
        ]
        assert [a["id"] for a in inv.iter_actions(state="awaiting_approval")] == ["a", "b"]
        assert dict(mock_org.client.request.call_args.kwargs["query_params"]) == {"state": "awaiting_approval", "cursor": "c1"}
        mock_org.client.request.side_effect = None
        mock_org.client.request.return_value = {"actions": [], "next_cursor": "same"}
        with pytest.raises(ApiError, match="did not advance"):
            list(inv.iter_actions(cursor="same"))

    def test_run_id_is_escaped_and_validated(self, inv, mock_org):
        mock_org.client.request.return_value = {}
        inv.get_run("run:1.a-b")
        assert _request_args(mock_org)[1] == "investigate/oid-1/runs/run%3A1.a-b"
        for bad in ("..", ".", "a/b", "", "x" * 129):
            with pytest.raises(ValidationError):
                inv.get_run(bad)

    def test_delete_run_route_response_and_no_retry(self, inv, mock_org):
        response = {"deleted": True}
        mock_org.client.request.return_value = response
        assert inv.delete_run("run:1.a-b") == response
        mock_org.client.request.assert_called_once_with(
            "DELETE", "investigate/oid-1/runs/run%3A1.a-b",
            query_params=None, timeout=None, retry_gateway_timeout=False,
        )

    @pytest.mark.parametrize("run_id", ["..", ".", "a/b", "", "x" * 129])
    def test_delete_run_rejects_invalid_ids_before_request(self, inv, mock_org, run_id):
        with pytest.raises(ValidationError):
            inv.delete_run(run_id)
        mock_org.client.request.assert_not_called()

    @pytest.mark.parametrize("status, code", [(403, "forbidden"), (404, "not_found"), (409, "conflict"), (504, "timeout")])
    def test_delete_run_preserves_errors_without_replay(self, inv, mock_org, status, code):
        body = {"error": "deletion refused", "error_code": code}
        mock_org.client.request.side_effect = error_from_status_code(status, body)
        with pytest.raises(InvestigationError) as ei:
            inv.delete_run("r1")
        assert ei.value.status_code == status
        assert ei.value.error_code == code
        assert ei.value.to_dict()["error"] == "deletion refused"
        assert _request_args(mock_org)[2]["retry_gateway_timeout"] is False

    def test_delete_run_404_without_engine_code_says_the_route_is_not_served(self, inv, mock_org):
        mock_org.client.request.side_effect = error_from_status_code(404, {"error": "not found"})
        with pytest.raises(InvestigationError) as ei:
            inv.delete_run("r1")
        assert ei.value.status_code == 404
        assert "does not serve run deletion" in ei.value.suggestion
        # What the user sees carries the delete hint only, once.
        assert str(ei.value).count("Suggestion:") == 1
        assert "does not serve run deletion" in str(ei.value)
        assert "experimental and gated" not in str(ei.value)
        doc = ei.value.to_dict()
        assert doc["error"] == "not found"
        assert "does not serve run deletion" in doc["suggestion"]

    def test_delete_run_404_with_engine_code_keeps_the_engine_message(self, inv, mock_org):
        body = {"error": "no such run", "error_code": "not_found"}
        mock_org.client.request.side_effect = error_from_status_code(404, body)
        with pytest.raises(InvestigationError) as ei:
            inv.delete_run("r1")
        assert ei.value.error_code == "not_found"
        assert "does not serve" not in (ei.value.suggestion or "")

    def test_events_bounds_and_params(self, inv, mock_org):
        mock_org.client.request.return_value = {"events": [], "next": 4, "done": False}
        inv.get_run_events("r1", after=4, wait=10, limit=500)
        verb, path, kw = _request_args(mock_org)
        assert path == "investigate/oid-1/runs/r1/events"
        assert dict(kw["query_params"]) == {"after": "4", "wait": "10", "limit": "500"}
        assert kw["timeout"] > 10
        for kwargs in ({"wait": 11}, {"wait": -1}, {"after": -1}, {"limit": 0}, {"limit": 501}):
            with pytest.raises(ValidationError):
                inv.get_run_events("r1", **kwargs)

    def test_follow_stops_at_done_and_resumes_from_next(self, inv, mock_org):
        mock_org.client.request.side_effect = [
            {"events": [{"seq": 1}, {"seq": 2}], "next": 2, "done": False},
            {"events": [], "next": 2, "done": False},
            {"events": [{"seq": 3}], "next": 3, "done": True},
        ]
        state = {}
        seqs = [e["seq"] for e in inv.iter_run_events("r1", state=state)]
        assert seqs == [1, 2, 3]
        assert state == {"next": 3, "done": True, "timed_out": False}
        afters = [dict(c.kwargs["query_params"])["after"] for c in mock_org.client.request.call_args_list]
        assert afters == ["0", "2", "2"]

    def test_follow_reports_a_timeout_with_the_resume_point(self, inv, mock_org):
        mock_org.client.request.return_value = {"events": [{"seq": 7}], "next": 7, "done": False}
        state = {}
        events = list(inv.iter_run_events("r1", after=5, timeout=0, state=state))
        assert [e["seq"] for e in events] == [7]
        assert state["done"] is False and state["timed_out"] is True and state["next"] == 7

    def test_writes_are_sent_once_and_as_json(self, inv, mock_org):
        mock_org.client.request.return_value = {"run": {}, "joined": False}
        inv.start_run({"trigger": {"detection_id": "d"}, "plan": {"auto": True}, "wait_seconds": 20})
        verb, path, kw = _request_args(mock_org)
        assert (verb, path) == ("POST", "investigate/oid-1/runs")
        assert json.loads(kw["raw_body"]) == {"trigger": {"detection_id": "d"}, "plan": {"auto": True}, "wait_seconds": 20}
        assert kw["content_type"] == "application/json"
        assert kw["retry_gateway_timeout"] is False  # a run is never replayed after a timeout
        assert kw["timeout"] >= 20

    def test_reads_may_be_retried(self, inv, mock_org):
        mock_org.client.request.return_value = {}
        inv.list_operators()
        assert "retry_gateway_timeout" not in _request_args(mock_org)[2]

    def test_decide_action_path_and_body(self, inv, mock_org):
        mock_org.client.request.return_value = {}
        inv.decide_action("r1", "a:1", "deny", note="legit")
        verb, path, kw = _request_args(mock_org)
        assert (verb, path) == ("POST", "investigate/oid-1/runs/r1/actions/a%3A1/deny")
        assert json.loads(kw["raw_body"]) == {"note": "legit"}
        with pytest.raises(ValidationError):
            inv.decide_action("r1", "a1", "delete")

    def test_list_actions_joins_states_and_uses_class(self, inv, mock_org):
        mock_org.client.request.return_value = {"actions": []}
        inv.list_actions(state=["awaiting_approval", "proposed"], action_class="tag", run_id="r1", limit=5)
        query = dict(_request_args(mock_org)[2]["query_params"])
        assert query == {"state": "awaiting_approval,proposed", "class": "tag", "run_id": "r1", "limit": "5"}

    def test_wave_needs_steps_and_gets_a_long_timeout(self, inv, mock_org):
        with pytest.raises(ValidationError):
            inv.run_wave({"steps": []})
        mock_org.client.request.return_value = {"results": []}
        inv.run_wave({"steps": [{"id": "a", "op": "x"}], "deadline_ms": 200000})
        assert _request_args(mock_org)[2]["timeout"] >= 200


# ---------------------------------------------------------------------------
# Plan tests
# ---------------------------------------------------------------------------

class TestPlanTest:
    def test_needs_exactly_one_plan_and_samples(self, inv):
        with pytest.raises(ValidationError):
            inv.test_plan([{"detection_id": "d"}])
        with pytest.raises(ValidationError):
            inv.test_plan([{"detection_id": "d"}], template="a", inline="b")
        with pytest.raises(ValidationError):
            inv.test_plan([], template="a")

    def test_request_shape(self, inv, mock_org):
        mock_org.client.request.return_value = {"test_id": "t"}
        inv.test_plan([{"detect_cat": "c", "last": 3}], inline=SRC, strict=True, mode="full", wait_seconds=2,
                      overrides={"budgets": {"max_wall_seconds": 60}})
        verb, path, kw = _request_args(mock_org)
        assert (verb, path) == ("POST", "investigate/oid-1/test-plan")
        assert json.loads(kw["raw_body"]) == {
            "samples": [{"detect_cat": "c", "last": 3}], "wait_seconds": 2, "inline": SRC, "strict": True,
            "mode": "full", "overrides": {"budgets": {"max_wall_seconds": 60}},
        }

    def test_wait_for_test_polls_with_results_seen_until_done(self, inv, mock_org):
        mock_org.client.request.side_effect = [
            {"test_id": "t1", "state": "running", "samples_done": 2, "done": False},
            {"test_id": "t1", "state": "done", "samples_done": 3, "done": True},
        ]
        out = inv.wait_for_test({"test_id": "t1", "state": "running", "samples_done": 0, "done": False})
        assert out["done"] is True
        queries = [dict(c.kwargs["query_params"]) for c in mock_org.client.request.call_args_list]
        assert [q["after"] for q in queries] == ["0", "2"]
        assert mock_org.client.request.call_args.args[1] == "investigate/oid-1/test-plan/t1"

    def test_wait_for_test_gives_up_at_the_timeout(self, inv, mock_org):
        running = {"test_id": "t1", "state": "running", "samples_done": 0, "done": False}
        assert inv.wait_for_test(running, timeout=0) is running
        mock_org.client.request.assert_not_called()

    def test_an_invalid_test_is_not_polled(self, inv, mock_org):
        invalid = {"test_id": "t1", "state": "invalid", "done": False}
        assert inv.wait_for_test(invalid) is invalid
        mock_org.client.request.assert_not_called()


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class TestErrors:
    def test_typed_errors_keep_the_response_body(self):
        for status, body in ((403, {"error": "x"}), (404, {"error": "y", "error_code": "not_found"}), (429, {"a": 1})):
            assert error_from_status_code(status, body).response_body == body

    def test_coded_issues_survive_verbatim(self, inv, mock_org):
        issues = [{"code": "unknown_field", "path": "steps[0].select[0]", "message": "no such field", "suggestion": "hosts_30d"}]
        mock_org.client.request.side_effect = error_from_status_code(
            400, {"error": "the wave is invalid", "error_code": "bad_request", "errors": issues, "warnings": [{"code": "operator_denied"}]},
        )
        with pytest.raises(InvestigationError) as ei:
            inv.run_wave({"steps": [{"id": "a", "op": "x"}]})
        exc = ei.value
        assert exc.issues == issues
        assert exc.warnings == [{"code": "operator_denied"}]
        assert exc.error_code == "bad_request" and exc.status_code == 400
        assert "[unknown_field] steps[0].select[0]: no such field (did you mean hosts_30d)" in str(exc)
        assert exc.to_dict()["errors"] == issues

    def test_unknown_path_404_says_the_feature_is_off(self, inv, mock_org):
        mock_org.client.request.side_effect = error_from_status_code(404, {"error": "not found"})
        with pytest.raises(InvestigationError) as ei:
            inv.list_runs()
        assert ei.value.error_code is None
        assert "gated per deployment" in ei.value.suggestion
        assert ei.value.exit_code == 3

    def test_engine_404_is_a_missing_run_not_a_disabled_feature(self, inv, mock_org):
        mock_org.client.request.side_effect = error_from_status_code(
            404, {"error": "run not found", "error_code": "not_found"})
        with pytest.raises(InvestigationError) as ei:
            inv.get_run("r1")
        assert ei.value.error_code == "not_found"
        assert not ei.value.suggestion
        assert "run not found" in str(ei.value)

    def test_missing_permissions_are_named(self, inv, mock_org):
        mock_org.client.request.side_effect = error_from_status_code(403, {"error": "Missing permissions"})
        with pytest.raises(InvestigationError) as ei:
            inv.start_run({"trigger": {}, "plan": {}})
        assert "insight.evt.get" in ei.value.suggestion and "investigation.set" in ei.value.suggestion

    def test_engine_403_keeps_its_own_message(self, inv, mock_org):
        mock_org.client.request.side_effect = error_from_status_code(
            403, {"error": "only the starter may add inputs", "error_code": "forbidden"})
        with pytest.raises(InvestigationError) as ei:
            inv.decide_action("r", "a", "approve")
        assert not ei.value.suggestion and ei.value.error_code == "forbidden"

    def test_no_engine_for_the_org_is_a_503(self, inv, mock_org):
        mock_org.client.request.side_effect = error_from_status_code(
            503, {"error": "the investigation engine is not available for this organization"})
        with pytest.raises(InvestigationError) as ei:
            inv.get_stats()
        assert "not available for this organization" in str(ei.value)
        assert "feature off" in ei.value.suggestion

    def test_run_cap(self, inv, mock_org):
        mock_org.client.request.side_effect = error_from_status_code(
            429, {"error": "too many runs", "error_code": "too_many_runs"})
        with pytest.raises(InvestigationError) as ei:
            inv.start_run({})
        assert "concurrent run cap" in ei.value.suggestion

    def test_authentication_errors_pass_through_untouched(self, inv, mock_org):
        mock_org.client.request.side_effect = AuthenticationError("bad key", code=401)
        with pytest.raises(AuthenticationError):
            inv.list_runs()


# ---------------------------------------------------------------------------
# Template source
# ---------------------------------------------------------------------------

_SCALARS = json.loads((Path(__file__).parent / "fixtures" / "investigation_scalars.json").read_text(encoding="utf-8"))["cases"]
_PLAIN_SCALARS = [
    c for c in _SCALARS
    if c["kind"] != "error" and c["kind"] not in ("sequence", "mapping")
    and c["src"] == c["src"].strip() and c["src"] and c["src"][0] not in "'\"!&*#" and " #" not in c["src"]
]


def _args_value(src: str) -> str:
    return "gather:\n  x:\n    op: plan.pick\n    args:\n      value: " + src + "\n"


class TestTemplateSource:
    @pytest.mark.parametrize("case", _SCALARS, ids=[c["src"] or "<empty>" for c in _SCALARS])
    def test_args_scalars_are_read_as_the_engine_reads_them(self, case):
        """Every spelling retains its expected public template scalar type."""
        src, kind, want = case["src"], case["kind"], case.get("value", "")
        if kind not in {"null", "bool", "int", "float", "string", "timestamp", "sequence", "mapping", "error"}:
            pytest.fail(f"Unknown scalar fixture kind: {kind!r}")
        text = _args_value(src)
        if kind == "error":
            with pytest.raises(ValidationError):
                parse_template_source(text)
            return
        if kind == "float" and want in ("nan", "+inf", "-inf"):
            with pytest.raises(ValidationError, match="JSON cannot carry"):
                parse_template_source(text)
            return
        got = parse_template_source(text)["gather"]["x"]["args"]["value"]
        if kind == "null":
            assert got is None
        elif kind == "bool":
            assert got is (want == "true")
        elif kind == "int":
            assert type(got) is int and got == int(want)
        elif kind == "float":
            assert type(got) is float and got == float(want)
        elif kind in ("string", "timestamp"):
            assert type(got) is str and got == want
        elif kind == "sequence":
            assert isinstance(got, list)
        elif kind == "mapping":
            assert isinstance(got, dict)

    def test_the_typed_field_lists_cover_every_non_text_field_of_the_engine(self):
        """A field the engine adds as a number or boolean must be added to the SDK's lists, or it would be stored as text."""
        fields = json.loads((Path(__file__).parent / "fixtures" / "investigation_typed_fields.json").read_text(encoding="utf-8"))["fields"]
        sdk_paths = {
            "number": {".".join(p) for p in inv_mod._NUMBER_PATHS},
            "bool": {".".join(p) for p in inv_mod._BOOL_PATHS},
        }
        assert {f["path"] for f in fields if f["kind"] == "number"} == sdk_paths["number"]
        assert {f["path"] for f in fields if f["kind"] == "bool"} == sdk_paths["bool"]

    def test_text_fields_keep_the_authors_spelling(self):
        data = parse_template_source(
            "description: 1e3\nstatus: 012\napplies_to: {category: [on, 0o17, 2026-11-10]}\n"
            "starts_from: none\ndeadline: 10m\ncase: {kind: [on, yes], severity: {default: low}}\n"
        )
        assert data == {
            "description": "1e3", "status": "012",
            "applies_to": {"category": ["on", "0o17", "2026-11-10"]},
            "starts_from": "none", "deadline": "10m",
            "case": {"kind": ["on", "yes"], "severity": {"default": "low"}},
        }

    def test_numeric_and_boolean_fields_are_read_as_such(self):
        data = parse_template_source(
            "version: 3\n"
            "gather: {a: {op: o, always: yes}, b: {use: p, pack_version: 0x10, always: False}, c: {op: o, always: true}}\n"
        )
        assert data["version"] == 3 and type(data["version"]) is int
        assert data["gather"]["a"]["always"] is True and data["gather"]["c"]["always"] is True
        assert data["gather"]["b"]["always"] is False
        assert data["gather"]["b"]["pack_version"] == 16 and type(data["gather"]["b"]["pack_version"]) is int

    def test_rule_sentences_and_conditions_stay_text(self):
        """A `when`, a `say`, an `only_if` or a rule id is text whatever it looks like; only `always` is a boolean."""
        data = parse_template_source(
            "gather: {a: {op: o, only_if: 'true', why: yes, ask: 1e3, always: true}}\n"
            "rules: {escalate: [{id: on, when: true, say: 012}], never_close_when: [off, '1e3']}\n"
        )
        assert data["gather"]["a"] == {"op": "o", "only_if": "true", "why": "yes", "ask": "1e3", "always": True}
        assert data["rules"]["escalate"] == [{"id": "on", "when": "true", "say": "012"}]
        assert data["rules"]["never_close_when"] == ["off", "1e3"]

    def test_act_attrs_are_read_like_step_args(self):
        """`attrs` is a free mapping the engine reads as any: the numbers in it stay numbers."""
        data = parse_template_source(
            "act:\n  - {class: tag, target: $a.sid, on: [r], attrs: {tag: 'ie:x', ttl: 86400, deep: {k: 0o17}}}\n"
        )
        assert data["act"][0]["attrs"] == {"tag": "ie:x", "ttl": 86400, "deep": {"k": 15}}
        assert data["act"][0]["target"] == "$a.sid"

    def test_quoted_and_tagged_scalars(self):
        data = parse_template_source(
            _args_value('"1e3"') + "").copy()
        assert data["gather"]["x"]["args"]["value"] == "1e3"
        got = parse_template_source(
            "gather:\n  x:\n    op: o\n    args: {a: !!str 12, b: !!int '0x1f', c: !!float 1, d: '~', e: !!binary aGk=}\n"
        )["gather"]["x"]["args"]
        assert got == {"a": "12", "b": 31, "c": 1.0, "d": "~", "e": "hi"}

    def test_a_tag_that_does_not_fit_is_refused(self):
        with pytest.raises(ValidationError, match="cannot decode"):
            parse_template_source(_args_value("!!int abc"))

    def test_nested_args_are_read_like_top_level_args(self):
        got = parse_template_source(
            "gather:\n  x:\n    op: o\n    args:\n      list: [012, 1_000, 1e3, off]\n      deep: {k: 0o17}\n"
        )["gather"]["x"]["args"]
        assert got == {"list": [10, 1000, 1000.0, "off"], "deep": {"k": 15}}

    def test_dump_round_trips_text_that_looks_like_something_else(self):
        data = {"a": "yes", "c": "2026-11-10", "n": "0308"}
        assert parse_template_source(dump_template(data)) == data

    @pytest.mark.parametrize("case", _PLAIN_SCALARS, ids=[c["src"] or "<empty>" for c in _PLAIN_SCALARS])
    def test_dump_quotes_every_string_the_engine_would_read_as_something_else(self, case):
        """A string the engine reads as a non-string when bare must be written quoted."""
        src = case["src"]
        text = dump_template({"gather": {"x": {"op": "plan.pick", "args": {"value": src}}}})
        assert parse_template_source(text)["gather"]["x"]["args"]["value"] == src
        if case["kind"] != "string":
            assert f"value: {src}\n" not in text, f"{src!r} would be read as {case['kind']}: {text}"

    @pytest.mark.parametrize("src", ["1e3", "0o17", "1E+3", "1e-3", "0x1F", "012", "1_000", ".5", "5.", "+1", ".inf", "-.INF", ".nan", "~", "null", "True", "yes", "off", "2026-11-10", "10:30"])
    def test_dump_of_quoted_numeric_strings_keeps_the_type(self, src):
        data = {"description": src, "gather": {"x": {"op": "o", "args": {"v": src, "l": [src]}}}}
        assert json.dumps(parse_template_source(dump_template(data))) == json.dumps(data)

    def test_dump_keeps_key_order(self):
        text = dump_template({"zebra": 1, "alpha": 2})
        assert text.index("zebra") < text.index("alpha")

    def test_rule_sentences_of_every_shape_round_trip(self):
        # The SDK treats a template as an opaque mapping: a rule's `when` is a string, a list or {any: [...]}.
        data = {"rules": {"escalate": [
            {"id": "a", "when": "x.y", "say": "Plain: {a.b} seen."},
            {"id": "b", "when": ["x.y", "z == 1"], "say": "yes"},
            {"id": "c", "when": {"any": ["x.y", {"all": ["p", "q"]}]}},
        ], "never_close_when": ["signals.any_holds"]}}
        text = dump_template(data)
        assert parse_template_source(text) == data
        assert parse_template_source(RULES_SRC)["rules"] == RULES

    @pytest.mark.parametrize("src,match", [
        ("", "empty"),
        ("- a\n- b\n", "mapping"),
        ("a: [unclosed\n", "not valid YAML"),
        ("a: &x 1\nb: *x\n", "anchors and aliases"),
    ])
    def test_refused_sources(self, src, match):
        with pytest.raises(ValidationError, match=match):
            parse_template_source(src)


# ---------------------------------------------------------------------------
# save_template
# ---------------------------------------------------------------------------

class TestSaveTemplate:
    def _stored(self, status, etag="e2"):
        return HiveRecord(name="my-plan", data={"description": "test plan", "status": status}, etag=etag)

    def test_saves_a_draft_by_default_creating_only(self, inv, mock_org, hive):
        mock_org.client.request.return_value = VALID
        hive.get.side_effect = [_not_found(), self._stored("draft")]
        out = inv.save_template("my-plan", SRC)
        assert out["saved"] is True and out["status"] == "draft"
        record = hive.set.call_args.args[0]
        assert record.name == "my-plan" and record.data["status"] == "draft"
        assert record.etag == inv_mod._CREATE_ONLY_ETAG
        assert record.tags is None and record.comment is None  # no metadata block: the hive default applies
        assert out["warnings"] == VALID["warnings"]

    def test_validates_the_exact_text_that_is_stored(self, inv, mock_org, hive):
        mock_org.client.request.return_value = VALID
        hive.get.side_effect = [_not_found(), self._stored("draft")]
        inv.save_template("my-plan", SRC)
        sent = json.loads(mock_org.client.request.call_args.kwargs["raw_body"])["yaml"]
        assert parse_template_source(sent)["status"] == "draft"

    def test_quoted_numeric_looking_strings_are_validated_as_stored(self, inv, mock_org, hive):
        src = ('description: "1e3"\ngather:\n  a:\n    op: plan.pick\n'
               '    args: {value: "1e3", hex: "0o17", num: 1e3, octal: 012}\n')
        mock_org.client.request.return_value = VALID
        hive.get.side_effect = [_not_found(), self._stored("draft")]
        inv.save_template("my-plan", src)
        stored = hive.set.call_args.args[0].data
        assert stored["description"] == "1e3"
        assert stored["gather"]["a"]["args"] == {"value": "1e3", "hex": "0o17", "num": 1000.0, "octal": 10}
        sent = json.loads(mock_org.client.request.call_args.kwargs["raw_body"])["yaml"]
        assert json.dumps(parse_template_source(sent)) == json.dumps(stored)
        assert '"1e3"' in sent and '"0o17"' in sent  # still strings when the engine reads the text it validated

    def test_a_nan_in_the_source_is_refused_before_anything_is_sent(self, inv, mock_org, hive):
        with pytest.raises(ValidationError, match="JSON cannot carry"):
            inv.save_template("my-plan", "gather: {a: {op: plan.pick, args: {value: .nan}}}\n")
        mock_org.client.request.assert_not_called()
        hive.set.assert_not_called()

    def test_a_template_cannot_activate_itself(self, inv, mock_org, hive):
        out = inv.save_template("my-plan", SRC + "status: active\n")
        assert out["saved"] is False and "cannot activate itself" in out["reason"]
        mock_org.client.request.assert_not_called()
        hive.set.assert_not_called()

    def test_explicit_active_is_written_active(self, inv, mock_org, hive):
        mock_org.client.request.return_value = VALID
        hive.get.side_effect = [_not_found(), self._stored("active")]
        out = inv.save_template("my-plan", SRC, status="active")
        assert out["saved"] is True and out["status"] == "active"
        assert hive.set.call_args.args[0].data["status"] == "active"

    def test_invalid_template_is_not_written_and_carries_the_report(self, inv, mock_org, hive):
        mock_org.client.request.return_value = INVALID
        out = inv.save_template("my-plan", SRC)
        assert out["saved"] is False and out["validation"] == INVALID
        hive.get.assert_not_called()
        hive.set.assert_not_called()

    def test_existing_record_is_not_overwritten_silently(self, inv, mock_org, hive):
        mock_org.client.request.return_value = VALID
        hive.get.return_value = self._stored("draft")
        out = inv.save_template("my-plan", SRC)
        assert out["saved"] is False and "overwrite" in out["reason"]
        hive.set.assert_not_called()

    def test_overwrite_replaces_a_draft_with_its_etag_and_keeps_its_metadata(self, inv, mock_org, hive):
        mock_org.client.request.return_value = VALID
        existing = HiveRecord(name="my-plan", data={"status": "draft"}, etag="e1", tags=["mine"], comment="old", enabled=True)
        hive.get.side_effect = [existing, self._stored("draft")]
        out = inv.save_template("my-plan", SRC, overwrite=True, comment="9/10 agree", tags=["ai-draft"])
        assert out["saved"] is True
        record = hive.set.call_args.args[0]
        assert record.etag == "e1"
        assert record.tags == ["mine", "ai-draft"] and record.comment == "9/10 agree" and record.enabled is True

    def test_overwrite_without_metadata_flags_sends_no_metadata(self, inv, mock_org, hive):
        mock_org.client.request.return_value = VALID
        existing = HiveRecord(name="my-plan", data={"status": "draft"}, etag="e1", tags=["mine"], enabled=True)
        hive.get.side_effect = [existing, self._stored("draft")]
        inv.save_template("my-plan", SRC, overwrite=True)
        record = hive.set.call_args.args[0]
        assert record.tags is None and record.enabled is None

    def test_new_record_with_metadata_is_enabled(self, inv, mock_org, hive):
        # Metadata sent without `enabled` would be stored as disabled.
        mock_org.client.request.return_value = VALID
        hive.get.side_effect = [_not_found(), self._stored("draft")]
        inv.save_template("my-plan", SRC, comment="c", tags=["t"])
        assert hive.set.call_args.args[0].enabled is True

    def test_a_draft_never_replaces_an_active_template_even_with_overwrite(self, inv, mock_org, hive):
        mock_org.client.request.return_value = VALID
        hive.get.return_value = self._stored("active")
        out = inv.save_template("my-plan", SRC, overwrite=True)
        assert out["saved"] is False and "is active" in out["reason"]
        hive.set.assert_not_called()

    def test_an_active_template_is_replaced_only_by_explicit_active_and_overwrite(self, inv, mock_org, hive):
        mock_org.client.request.return_value = VALID
        hive.get.side_effect = [self._stored("active", "e1"), self._stored("active", "e2")]
        assert inv.save_template("my-plan", SRC, status="active", overwrite=True)["saved"] is True
        assert hive.set.call_args.args[0].etag == "e1"
        hive.get.side_effect = [self._stored("active", "e1")]
        assert inv.save_template("my-plan", SRC, status="active")["saved"] is False

    def test_a_record_with_an_unknown_status_is_left_alone(self, inv, mock_org, hive):
        mock_org.client.request.return_value = VALID
        hive.get.return_value = self._stored("retired")
        out = inv.save_template("my-plan", SRC, overwrite=True)
        assert out["saved"] is False and "retired" in out["reason"]
        hive.set.assert_not_called()

    def test_a_hive_failure_other_than_not_found_stops_the_save(self, inv, mock_org, hive):
        mock_org.client.request.return_value = VALID
        hive.get.side_effect = error_from_status_code(500, "boom")
        with pytest.raises(ApiError):
            inv.save_template("my-plan", SRC)
        hive.set.assert_not_called()

    def test_stored_status_that_differs_is_reported_as_an_error(self, inv, mock_org, hive):
        mock_org.client.request.return_value = VALID
        hive.get.side_effect = [_not_found(), self._stored("active")]
        with pytest.raises(ApiError, match="status reads 'active', not 'draft'"):
            inv.save_template("my-plan", SRC)

    @pytest.mark.parametrize("name", ["", "Upper", "-lead", "a b", "x" * 65, "a/b"])
    def test_bad_names_are_refused_before_any_call(self, inv, mock_org, hive, name):
        with pytest.raises(ValidationError):
            inv.save_template(name, SRC)
        mock_org.client.request.assert_not_called()

    def test_name_key_in_the_source_is_refused(self, inv):
        with pytest.raises(ValidationError, match="name"):
            inv.save_template("my-plan", "name: other\n" + SRC)

    def test_bad_status_in_source_or_argument(self, inv):
        with pytest.raises(ValidationError):
            inv.save_template("my-plan", SRC + "status: retired\n")
        with pytest.raises(ValidationError):
            inv.save_template("my-plan", SRC, status="retired")


    def test_a_write_that_landed_but_failed_on_replay_is_not_reported_as_an_error(self, inv, mock_org, hive):
        mock_org.client.request.return_value = VALID
        data = {"description": "test plan", "gather": {"a": {"op": "entity.get", "args": {"entity_id": "$entity"}}}, "status": "draft"}
        landed = HiveRecord(name="my-plan", data=data, etag="e9")
        hive.get.side_effect = [_not_found(), landed, landed]
        hive.set.side_effect = error_from_status_code(400, {"error": "lc_error_code:ETAG_MISMATCH"})
        assert inv.save_template("my-plan", SRC)["saved"] is True

    def test_a_failed_overwrite_does_not_pass_as_saved_when_the_comment_was_lost(self, inv, mock_org, hive):
        mock_org.client.request.return_value = VALID
        data = {"description": "test plan", "gather": {"a": {"op": "entity.get", "args": {"entity_id": "$entity"}}}, "status": "draft"}
        same = HiveRecord(name="my-plan", data=data, etag="e1", comment="old", tags=[], enabled=True)
        hive.get.side_effect = [same, same]
        hive.set.side_effect = error_from_status_code(500, "boom")
        with pytest.raises(ApiError):
            inv.save_template("my-plan", SRC, overwrite=True, comment="new: 9/10 agree")

    def test_a_write_that_failed_and_did_not_land_is_an_error(self, inv, mock_org, hive):
        mock_org.client.request.return_value = VALID
        hive.get.side_effect = [_not_found(), _not_found()]
        hive.set.side_effect = error_from_status_code(400, {"error": "lc_error_code:ETAG_MISMATCH"})
        with pytest.raises(ApiError):
            inv.save_template("my-plan", SRC)


class TestRuleSentences:
    """The rules of a template (ids, conditions, sentences) travel through get, save and install unchanged."""

    def test_get_template_returns_the_rules_in_the_record_and_the_yaml(self, inv, hive):
        hive.get.return_value = HiveRecord(name="p", data={"description": "d", "rules": RULES}, etag="e")
        view = inv.get_template("p")
        assert view["data"]["rules"] == RULES
        assert parse_template_source(view["yaml"])["rules"] == RULES

    def test_save_validates_and_stores_the_rules_unchanged(self, inv, mock_org, hive):
        mock_org.client.request.return_value = VALID
        hive.get.side_effect = [_not_found(), HiveRecord(name="p", data={"status": "draft"}, etag="e")]
        assert inv.save_template("p", RULES_SRC)["saved"] is True
        sent = json.loads(mock_org.client.request.call_args.kwargs["raw_body"])["yaml"]
        assert parse_template_source(sent)["rules"] == RULES
        assert hive.set.call_args.args[0].data["rules"] == RULES

    def test_install_defaults_writes_a_library_template_with_its_rules(self, inv, mock_org, hive):
        def request(verb, path, **kw):
            if path.endswith("authoring-kit"):
                return {"library": [{"name": "alpha", "version": 3, "status": "active", "yaml": RULES_SRC}]}
            return VALID
        mock_org.client.request.side_effect = request
        hive.get.side_effect = [_not_found(), HiveRecord(name="alpha", data={"status": "draft"}, etag="e")]
        out = inv.install_default_templates()
        assert [w["name"] for w in out["written"]] == ["alpha"]
        assert hive.set.call_args.args[0].data["rules"] == RULES


class TestTemplateRecordPermissions:
    def test_a_refused_hive_operation_names_the_investigation_plan_permissions(self, inv, hive):
        hive.get.side_effect = error_from_status_code(400, {"error": "lc_error_code:UNAUTHORIZED - nope"})
        with pytest.raises(InvestigationError) as ei:
            inv.get_template("x")
        assert "investigation_plan.get" in ei.value.suggestion and ei.value.status_code == 403

    def test_other_hive_failures_keep_their_status_code_and_message(self, inv, hive):
        hive.delete.side_effect = error_from_status_code(500, "boom")
        with pytest.raises(InvestigationError) as ei:
            inv.delete_template("x")
        assert ei.value.status_code == 500 and "boom" in ei.value.raw_message
        assert "investigation_plan" not in (ei.value.suggestion or "")

    def test_a_coded_hive_refusal_keeps_its_lc_error_code(self, inv, hive):
        hive.get.side_effect = [HiveRecord(name="p", data={"status": "draft"}, etag="e1")]
        hive.set.side_effect = error_from_status_code(
            400, {"error": "lc_error_code:API_KEY_NOT_ALLOWED - an API key cannot promote"})
        with patch.object(Investigation, "validate_plan", return_value=VALID):
            with pytest.raises(InvestigationError) as ei:
                inv.promote_template("p")
        doc = ei.value.to_dict()
        assert doc["error_code"] == "API_KEY_NOT_ALLOWED" and "cannot promote" in doc["error"]
        assert doc["status"] == 400 and ei.value.exit_code == 1


class TestAIMayDecide:
    """What the AI may decide is a field of the `default` policy record; only that field changes."""

    DEFAULT = {"autonomy": {"close.false_positive": {"mode": "suggest", "lease": "2h"}}, "ai_may_decide": {"mailsec-message": "escalate"}}

    def test_without_a_default_record_nothing_is_granted(self, inv, mock_org, hive):
        hive.get.side_effect = _not_found()
        assert inv.get_ai_may_decide() == {"record": "default", "ai_may_decide": {}}
        inv_mod.Hive.assert_called_with(mock_org, "investigation_policy")
        hive.get.assert_called_with("default")
        mock_org.client.request.assert_not_called()

    def test_the_modes_of_the_default_record_are_returned(self, inv, hive):
        hive.get.return_value = HiveRecord(name="default", data=self.DEFAULT, enabled=True, etag="e1", last_author="a@example.com", last_modified=5)
        out = inv.get_ai_may_decide()
        assert out["ai_may_decide"] == {"mailsec-message": "escalate"}
        assert (out["etag"], out["enabled"], out["last_author"]) == ("e1", True, "a@example.com")

    def test_setting_a_mode_changes_that_field_only_and_is_conditional(self, inv, hive):
        stored = HiveRecord(name="default", data=self.DEFAULT, enabled=True, etag="e1", tags=["t"], comment="c", expiry=0)
        after = HiveRecord(name="default", data={**self.DEFAULT, "ai_may_decide": {"mailsec-message": "close_and_escalate"}}, enabled=True, etag="e2")
        hive.get.side_effect = [stored, after]
        out = inv.set_ai_may_decide("mailsec-message", "close_and_escalate")
        record = hive.set.call_args.args[0]
        assert record.etag == "e1" and record.enabled is True
        assert record.data["autonomy"] == self.DEFAULT["autonomy"], "the rest of the record is kept"
        assert record.data["ai_may_decide"] == {"mailsec-message": "close_and_escalate"}
        assert (record.tags, record.comment) == (["t"], "c")
        assert out["changed"] is True and out["ai_may_decide"] == {"mailsec-message": "close_and_escalate"}
        assert stored.data["ai_may_decide"] == {"mailsec-message": "escalate"}, "the record read is not mutated"

    def test_a_missing_default_record_is_created_without_overwriting(self, inv, hive):
        hive.get.side_effect = [_not_found(), HiveRecord(name="default", data={"ai_may_decide": {"*": "escalate"}}, enabled=True, etag="e2")]
        out = inv.set_ai_may_decide("*", "escalate")
        record = hive.set.call_args.args[0]
        assert record.etag == inv_mod._CREATE_ONLY_ETAG and record.enabled is True
        assert record.data == {"ai_may_decide": {"*": "escalate"}}
        assert out["changed"] is True

    def test_the_same_mode_writes_nothing(self, inv, hive):
        hive.get.return_value = HiveRecord(name="default", data=self.DEFAULT, enabled=True, etag="e1")
        assert inv.set_ai_may_decide("mailsec-message", "escalate")["changed"] is False
        hive.set.assert_not_called()

    def test_off_removes_a_template_entry_that_nothing_else_grants(self, inv, hive):
        hive.get.side_effect = [HiveRecord(name="default", data=self.DEFAULT, enabled=True, etag="e1"), HiveRecord(name="default", data={"autonomy": self.DEFAULT["autonomy"]}, enabled=True, etag="e2")]
        inv.set_ai_may_decide("mailsec-message", "off")
        assert "ai_may_decide" not in hive.set.call_args.args[0].data

    def test_off_is_written_when_the_wildcard_grants(self, inv, hive):
        stored = HiveRecord(name="default", data={"ai_may_decide": {"*": "escalate", "mailsec-message": "escalate"}}, enabled=True, etag="e1")
        hive.get.side_effect = [stored, stored]
        inv.set_ai_may_decide("mailsec-message", "off")
        assert hive.set.call_args.args[0].data["ai_may_decide"] == {"*": "escalate", "mailsec-message": "off"}

    def test_off_on_a_missing_record_writes_nothing(self, inv, hive):
        hive.get.side_effect = _not_found()
        assert inv.set_ai_may_decide("mailsec-message", "off")["changed"] is False
        hive.set.assert_not_called()

    def test_the_wildcard_off_on_a_missing_record_is_refused_not_created(self, inv, hive):
        hive.get.side_effect = _not_found()
        with pytest.raises(ValidationError, match="no default policy record"):
            inv.set_ai_may_decide("*", "off")
        hive.set.assert_not_called()

    def test_the_wildcard_off_on_an_existing_record_is_written(self, inv, hive):
        stored = HiveRecord(name="default", data={"ai_may_decide": {"*": "escalate"}}, enabled=True, etag="e1")
        hive.get.side_effect = [stored, HiveRecord(name="default", data={"ai_may_decide": {"*": "off"}}, enabled=True, etag="e2")]
        assert inv.set_ai_may_decide("*", "off")["changed"] is True
        assert hive.set.call_args.args[0].data["ai_may_decide"] == {"*": "off"}

    def test_the_modes_are_written_as_strings_the_hive_accepts(self, inv, hive):
        """`off` must reach the hive as the text "off" (never a YAML 1.1 boolean), in the record and in the JSON it is sent as."""
        stored = HiveRecord(name="default", data={"ai_may_decide": {"*": "escalate", "t": "escalate"}}, enabled=True, etag="e1")
        hive.get.side_effect = [stored, stored]
        inv.set_ai_may_decide("t", "off")
        data = hive.set.call_args.args[0].data
        assert data["ai_may_decide"] == {"*": "escalate", "t": "off"}
        assert json.loads(json.dumps(data))["ai_may_decide"]["t"] == "off" and isinstance(data["ai_may_decide"]["t"], str)

    @pytest.mark.parametrize("template,mode", [("t", "on"), ("t", "auto"), ("Bad Name", "off"), ("", "off"), ("a/b", "escalate")])
    def test_a_bad_name_or_mode_is_refused_before_any_call(self, inv, hive, template, mode):
        with pytest.raises(ValidationError):
            inv.set_ai_may_decide(template, mode)
        hive.get.assert_not_called()
        hive.set.assert_not_called()

    def test_a_refused_write_names_the_policy_permissions(self, inv, hive):
        hive.get.side_effect = error_from_status_code(400, {"error": "lc_error_code:UNAUTHORIZED - nope"})
        with pytest.raises(InvestigationError) as ei:
            inv.set_ai_may_decide("t", "escalate")
        assert "investigation_policy" in ei.value.suggestion and ei.value.status_code == 403


class TestRunOutcomes:
    def test_list_runs_sends_the_outcome_filter(self, inv, mock_org):
        mock_org.client.request.return_value = {"runs": [], "next_cursor": ""}
        inv.list_runs(outcome="ai_recommends_benign", template="t")
        assert dict(mock_org.client.request.call_args.kwargs["query_params"]) == {"outcome": "ai_recommends_benign", "template": "t"}

    def test_undecided_is_an_outcome_filter(self, inv, mock_org):
        mock_org.client.request.return_value = {"runs": []}
        inv.list_runs(outcome="undecided")
        assert dict(mock_org.client.request.call_args.kwargs["query_params"]) == {"outcome": "undecided"}

    @pytest.mark.parametrize("bad", ["false_positive", "decided", "CLOSED_BY_RULE", "inconclusive"])
    def test_a_label_or_unknown_word_is_not_an_outcome(self, inv, mock_org, bad):
        with pytest.raises(ValidationError, match="outcome"):
            inv.list_runs(outcome=bad)
        mock_org.client.request.assert_not_called()

    def test_every_outcome_the_engine_documents_is_accepted(self, inv, mock_org):
        mock_org.client.request.return_value = {"runs": []}
        for outcome in inv_mod.RUN_OUTCOMES:
            inv.list_runs(outcome=outcome)
        assert len(inv_mod.RUN_OUTCOMES) == 8

    def test_iter_runs_keeps_the_outcome_across_pages(self, inv, mock_org):
        mock_org.client.request.side_effect = [{"runs": [{"run_id": "a"}], "next_cursor": "c"}, {"runs": [{"run_id": "b"}]}]
        assert [r["run_id"] for r in inv.iter_runs(outcome="couldnt_tell")] == ["a", "b"]
        assert [dict(c.kwargs["query_params"])["outcome"] for c in mock_org.client.request.call_args_list] == ["couldnt_tell"] * 2

    def test_the_run_and_the_steps_come_back_as_the_engine_sent_them(self, inv, mock_org):
        verdict = {"outcome": "ai_recommends_benign", "label": "inconclusive", "decided": False,
                   "recommendation": {"label": "benign", "self_rated_confidence": 0.8, "rationale": "r", "citations": ["a.b"], "by": "ai_review"},
                   "missing": [{"step": "s", "reason": "timeout", "needed_by": ["rule_1"], "ask": "Is it?"}]}
        run = {"run_id": "r1", "verdict": verdict, "ai_may_decide": "off", "ai_agent": {"name": "triage"}, "critical_path": []}
        steps = {"steps": [{"id": "s", "narrative": {"why": "w", "found": "f", "used": ["ai_review"]}}], "timeline": [], "ai_may_decide": "off"}
        mock_org.client.request.side_effect = [run, steps]
        assert inv.get_run("r1") == run
        assert inv.get_run_steps("r1") == steps


PAUSE_DATA = {"autonomy": {"*": {"mode": "suggest"}}}


class TestPause:
    """Pause, resume and status are the ``autonomy-manual-pause`` policy record, never a gateway route."""

    def test_status_without_the_record_is_not_paused(self, inv, mock_org, hive):
        hive.get.side_effect = _not_found()
        assert inv.get_pause() == {"paused": False, "record": "autonomy-manual-pause"}
        inv_mod.Hive.assert_called_with(mock_org, "investigation_policy")
        hive.get.assert_called_with("autonomy-manual-pause")
        mock_org.client.request.assert_not_called()

    def test_status_of_the_pause_record(self, inv, hive):
        hive.get.return_value = HiveRecord(
            name="autonomy-manual-pause", data=PAUSE_DATA, enabled=True, etag="e1", last_author="a@example.com", last_modified=5)
        assert inv.get_pause() == {
            "paused": True, "record": "autonomy-manual-pause", "etag": "e1", "last_author": "a@example.com", "last_modified": 5}

    @pytest.mark.parametrize("enabled,data,reason", [
        (False, PAUSE_DATA, "disabled"),
        (None, PAUSE_DATA, "disabled"),
        (True, {"autonomy": {"*": {"mode": "auto"}}}, "edited"),
        (True, {"match": {"run": 'template == "t"'}, **PAUSE_DATA}, "edited"),
        (True, PAUSE_DATA, "expires"),
    ])
    def test_a_record_that_does_not_pause_says_why(self, inv, hive, enabled, data, reason):
        hive.get.return_value = HiveRecord(
            name="autonomy-manual-pause", data=data, enabled=enabled, etag="e1", expiry=1893456000000 if reason == "expires" else 0)
        view = inv.get_pause()
        assert view["paused"] is False and view["inactive_reason"] == reason

    def test_a_failed_read_is_not_taken_for_a_missing_record(self, inv, hive):
        hive.get.side_effect = error_from_status_code(500, "boom")
        with pytest.raises(InvestigationError) as ei:
            inv.get_pause()
        assert ei.value.status_code == 500

    def test_pause_creates_the_record_and_only_it(self, inv, mock_org, hive):
        hive.get.side_effect = [_not_found(), HiveRecord(name="autonomy-manual-pause", data=PAUSE_DATA, enabled=True, etag="e2")]
        out = inv.pause_actions()
        record = hive.set.call_args.args[0]
        assert (record.name, record.data, record.enabled) == ("autonomy-manual-pause", PAUSE_DATA, True)
        assert record.etag == inv_mod._CREATE_ONLY_ETAG
        assert out["paused"] is True and out["changed"] is True
        hive.delete.assert_not_called()
        mock_org.client.request.assert_not_called()

    def test_pause_twice_writes_nothing(self, inv, hive):
        hive.get.return_value = HiveRecord(name="autonomy-manual-pause", data=PAUSE_DATA, enabled=True, etag="e1")
        out = inv.pause_actions()
        assert out["paused"] is True and out["changed"] is False
        hive.set.assert_not_called()

    def test_pause_repairs_a_disabled_record_with_its_etag_and_metadata(self, inv, hive):
        stored = HiveRecord(name="autonomy-manual-pause", data=PAUSE_DATA, enabled=False, etag="e1", tags=["t"], comment="c", expiry=0)
        hive.get.side_effect = [stored, HiveRecord(name="autonomy-manual-pause", data=PAUSE_DATA, enabled=True, etag="e2")]
        inv.pause_actions()
        record = hive.set.call_args.args[0]
        assert record.etag == "e1" and record.enabled is True and record.data == PAUSE_DATA
        assert (record.tags, record.comment) == (["t"], "c")

    def test_pause_rewrites_an_expiring_record_without_its_expiry(self, inv, hive):
        stored = HiveRecord(name="autonomy-manual-pause", data=PAUSE_DATA, enabled=True, etag="e1", expiry=1893456000000)
        hive.get.side_effect = [stored, HiveRecord(name="autonomy-manual-pause", data=PAUSE_DATA, enabled=True, etag="e2", expiry=0)]
        out = inv.pause_actions()
        assert hive.set.call_args.args[0].expiry == 0
        assert out["paused"] is True and out["changed"] is True

    def test_a_new_record_is_written_without_expiry(self, inv, hive):
        hive.get.side_effect = [_not_found(), HiveRecord(name="autonomy-manual-pause", data=PAUSE_DATA, enabled=True, etag="e2")]
        inv.pause_actions()
        assert hive.set.call_args.args[0].expiry == 0

    def test_a_concurrent_pause_that_wins_the_race_is_not_an_error(self, inv, hive):
        won = HiveRecord(name="autonomy-manual-pause", data=PAUSE_DATA, enabled=True, etag="e9")
        hive.get.side_effect = [_not_found(), won]
        hive.set.side_effect = error_from_status_code(400, {"error": "lc_error_code:ETAG_MISMATCH - changed"})
        out = inv.pause_actions()
        assert out["paused"] is True and out["changed"] is False

    def test_a_failed_write_that_did_not_pause_is_raised(self, inv, hive):
        hive.get.side_effect = [_not_found(), _not_found()]
        hive.set.side_effect = error_from_status_code(500, "boom")
        with pytest.raises(InvestigationError) as ei:
            inv.pause_actions()
        assert ei.value.status_code == 500

    def test_resume_deletes_the_record(self, inv, mock_org, hive):
        hive.get.side_effect = [HiveRecord(name="autonomy-manual-pause", data=PAUSE_DATA, enabled=True, etag="e1"), _not_found()]
        out = inv.resume_actions()
        hive.delete.assert_called_once_with("autonomy-manual-pause")
        assert out["paused"] is False and out["changed"] is True
        mock_org.client.request.assert_not_called()

    def test_resume_without_the_record_deletes_nothing(self, inv, hive):
        hive.get.side_effect = _not_found()
        assert inv.resume_actions()["changed"] is False
        hive.delete.assert_not_called()

    def test_a_refused_pause_names_the_policy_permissions(self, inv, hive):
        hive.get.side_effect = error_from_status_code(400, {"error": "lc_error_code:UNAUTHORIZED - nope"})
        with pytest.raises(InvestigationError) as ei:
            inv.get_pause()
        assert "investigation_policy.get" in ei.value.suggestion and "investigation_policy.del" in ei.value.suggestion
        assert ei.value.status_code == 403


class TestReasonCode:
    BODY = {"error": "no active template applies", "error_code": "bad_request", "http_status": 400,
            "reason_code": "no_template_applies"}

    def test_a_refused_start_keeps_its_reason_code(self, inv, mock_org):
        mock_org.client.request.side_effect = error_from_status_code(400, dict(self.BODY))
        with pytest.raises(InvestigationError) as ei:
            inv.start_run({"trigger": {"detection_id": "d"}})
        exc = ei.value
        assert exc.reason_code == "no_template_applies" and exc.error_code == "bad_request"
        assert "(reason_code: no_template_applies)" in str(exc)
        doc = exc.to_dict()
        assert doc["reason_code"] == "no_template_applies"
        assert doc["error"] == "no active template applies"

    def test_a_policy_refusal_keeps_its_path(self, inv, mock_org):
        mock_org.client.request.side_effect = error_from_status_code(
            400, {"error": "unknown field", "error_code": "policy_unknown_field", "path": "/autonomy/tag/mode"})
        with pytest.raises(InvestigationError) as ei:
            inv.get_effective_policy()
        assert ei.value.path == "/autonomy/tag/mode" and ei.value.to_dict()["path"] == "/autonomy/tag/mode"
        assert ei.value.reason_code is None and "reason_code" not in ei.value.to_dict()

    def test_a_reason_already_in_the_message_is_not_repeated(self, inv, mock_org):
        body = dict(self.BODY, error="refused: no_template_applies")
        mock_org.client.request.side_effect = error_from_status_code(400, body)
        with pytest.raises(InvestigationError) as ei:
            inv.start_run({})
        assert "(reason_code" not in str(ei.value)


class TestPromote:
    def test_promotes_with_the_etag_that_was_read(self, inv, mock_org, hive):
        mock_org.client.request.return_value = VALID
        hive.get.side_effect = [
            HiveRecord(name="p", data={"description": "d", "status": "draft"}, etag="e1"),
            HiveRecord(name="p", data={"description": "d", "status": "active"}, etag="e2"),
        ]
        out = inv.promote_template("p")
        assert out["promoted"] is True and out["status"] == "active"
        record = hive.set.call_args.args[0]
        assert record.etag == "e1" and record.data["status"] == "active" and record.tags is None
        sent = parse_template_source(json.loads(mock_org.client.request.call_args.kwargs["raw_body"])["yaml"])
        assert sent["status"] == "active"  # what is validated is what is stored

    def test_a_record_that_does_not_read_back_identically_is_not_validated_as_something_else(self, inv, mock_org, hive):
        # A number where the engine reads text: the rendered YAML would read back as text, a different template.
        hive.get.return_value = HiveRecord(name="p", data={"description": 5, "status": "draft"}, etag="e1")
        with pytest.raises(ValidationError, match="reads back identically"):
            inv.promote_template("p")
        mock_org.client.request.assert_not_called()
        hive.set.assert_not_called()

    def test_an_invalid_draft_stays_a_draft(self, inv, mock_org, hive):
        mock_org.client.request.return_value = INVALID
        hive.get.return_value = HiveRecord(name="p", data={"status": "draft"}, etag="e1")
        out = inv.promote_template("p")
        assert out["promoted"] is False and out["validation"] == INVALID
        hive.set.assert_not_called()

    def test_already_active_is_a_no_op(self, inv, mock_org, hive):
        hive.get.return_value = HiveRecord(name="p", data={"status": "active"}, etag="e1")
        assert inv.promote_template("p")["promoted"] is False
        hive.set.assert_not_called()


class TestInstallDefaults:
    LIB = [
        {"name": "alpha", "version": 2, "status": "active", "yaml": "description: a\nstatus: active\ngather: {}\n"},
        {"name": "beta", "version": 1, "status": "active", "yaml": "description: b\ngather: {}\n"},
    ]

    def _kit(self, mock_org, library):
        def request(verb, path, **kw):
            if path.endswith("authoring-kit"):
                assert dict(kw["query_params"]) == {"sections": "library"}
                return {"library": library}
            return VALID
        mock_org.client.request.side_effect = request

    def test_writes_every_entry_as_a_draft_even_when_the_library_says_active(self, inv, mock_org, hive):
        self._kit(mock_org, self.LIB)
        drafts = [HiveRecord(name=n, data={"status": "draft"}, etag="e") for n in ("alpha", "beta")]
        hive.get.side_effect = [_not_found(), drafts[0], _not_found(), drafts[1]]
        out = inv.install_default_templates()
        assert [w["name"] for w in out["written"]] == ["alpha", "beta"]
        assert {w["status"] for w in out["written"]} == {"draft"}
        assert [c.args[0].data["status"] for c in hive.set.call_args_list] == ["draft", "draft"]
        assert out["skipped"] == [] and out["failed"] == []

    def test_existing_records_are_skipped_with_versions_not_overwritten(self, inv, mock_org, hive):
        self._kit(mock_org, self.LIB)
        hive.get.return_value = HiveRecord(name="x", data={"status": "active", "version": 1}, etag="e")
        out = inv.install_default_templates(["alpha"])
        hive.set.assert_not_called()
        assert out["written"] == []
        assert out["skipped"] == [{
            "name": "alpha", "reason": out["skipped"][0]["reason"], "library_version": 2,
            "installed_version": 1, "installed_status": "active", "update_available": True,
        }]
        assert "already installed" in out["skipped"][0]["reason"]

    def test_only_the_named_entries_are_installed(self, inv, mock_org, hive):
        self._kit(mock_org, self.LIB)
        hive.get.side_effect = [_not_found(), HiveRecord(name="beta", data={"status": "draft"}, etag="e")]
        out = inv.install_default_templates(["beta"])
        assert [w["name"] for w in out["written"]] == ["beta"]

    def test_unknown_name_is_refused_with_the_available_ones(self, inv, mock_org, hive):
        self._kit(mock_org, self.LIB)
        with pytest.raises(ValidationError, match="gamma.*alpha, beta"):
            inv.install_default_templates(["gamma"])
        hive.set.assert_not_called()

    def test_an_engine_without_a_library_says_so(self, inv, mock_org, hive):
        mock_org.client.request.return_value = {"kit_version": 2, "guide": "g"}
        with pytest.raises(ValidationError, match="no default template library"):
            inv.install_default_templates()

    def test_an_entry_that_does_not_validate_is_reported_failed(self, inv, mock_org, hive):
        def request(verb, path, **kw):
            return {"library": self.LIB} if path.endswith("authoring-kit") else INVALID
        mock_org.client.request.side_effect = request
        out = inv.install_default_templates(["alpha"])
        assert out["written"] == [] and out["failed"][0]["name"] == "alpha"
        assert out["failed"][0]["validation"] == INVALID
        hive.set.assert_not_called()

    def test_active_status_is_written_only_when_asked(self, inv, mock_org, hive):
        self._kit(mock_org, self.LIB)
        hive.get.side_effect = [_not_found(), HiveRecord(name="alpha", data={"status": "active"}, etag="e")]
        out = inv.install_default_templates(["alpha"], status="active")
        assert out["written"][0]["status"] == "active"


class TestParseDocument:
    def test_yaml_11_words_and_dates_are_sent_as_written(self):
        doc = parse_document("a: off\nb: yes\nc: no\nd: 2026-11-10\ne: true\nf: 012\ng: 1_000\nh: 1e3\n")
        assert doc == {"a": "off", "b": "yes", "c": "no", "d": "2026-11-10", "e": True, "f": 10, "g": 1000, "h": 1000.0}
        json.dumps(doc)

    def test_json_is_accepted(self):
        assert parse_document('{"steps": [{"id": "a", "n": 1}]}') == {"steps": [{"id": "a", "n": 1}]}

    def test_anchors_are_expanded_not_refused(self):
        assert parse_document("a: &x [1, 2]\nb: *x\n") == {"a": [1, 2], "b": [1, 2]}

    def test_garbage_is_a_validation_error(self):
        with pytest.raises(ValidationError):
            parse_document("a: [unclosed")

    def test_empty_is_a_validation_error(self):
        with pytest.raises(ValidationError):
            parse_document("  \n")

    @pytest.mark.parametrize("src", ["a: .nan\n", "a: [.inf]\n", "a: {b: -.inf}\n"])
    def test_values_json_cannot_carry_are_refused(self, src):
        with pytest.raises(ValidationError, match="JSON cannot carry"):
            parse_document(src)

    def test_a_nan_input_never_reaches_the_wire(self, inv, mock_org):
        with pytest.raises(ValidationError, match="JSON cannot carry"):
            inv._call("POST", "waves", body={"inputs": {"x": float("nan")}}, write=True)
        mock_org.client.request.assert_not_called()

    def test_a_set_tag_is_refused(self):
        with pytest.raises(ValidationError):
            parse_document("a: !!set {x}\n")


@pytest.mark.parametrize("spec", [None, {}])
def test_start_run_empty_trust_wire_contract(inv, mock_org, spec):
    mock_org.client.request.return_value = {"run": {"run_id": "r1"}}
    request = {"trigger": {"question": "fictional"}, "trust": spec}
    inv.start_run(request)
    sent = json.loads(_request_args(mock_org)[2]["raw_body"])
    assert "trust" not in sent
    assert "trust" in request  # the SDK does not mutate its caller's object


def test_wave_never_sends_unsupported_request_trust(inv, mock_org):
    with pytest.raises(ValidationError, match="only by run start"):
        inv.run_wave({"steps": [{"id": "s", "op": "entity.get"}], "trust": {"lookups": ["partners"]}})
    mock_org.client.request.assert_not_called()

class TestOrgPacksAndComposition:
    def test_pack_writes_exact_envelope_and_revision(self, inv, hive):
        source = '# retained comment\nname: fictional_pack\nversion: 1\n'
        inv.save_pack('fictional_pack', source)
        record = hive.set.call_args.args[0]
        assert record.data == {'yaml': source}
        assert record.etag == inv_mod._CREATE_ONLY_ETAG
        inv.save_pack('fictional_pack', source, etag='revision-1')
        assert hive.set.call_args.args[0].etag == 'revision-1'
        assert inv_mod.Hive.call_args.args[1] == 'investigation_pack'

    def test_pack_validation_and_read_delete(self, inv, hive):
        for name, source, etag in [(None, 'x', None), (123, 'x', None), ('bad/name', 'x', None), ('good', '', None), ('good', 'x', '')]:
            with pytest.raises(ValidationError):
                inv.save_pack(name, source, etag=etag)
        hive.set.assert_not_called()
        hive.get.return_value = HiveRecord(name='fictional_pack', data={'yaml': '# exact\n'}, etag='r', enabled=True)
        assert inv.get_pack('fictional_pack') == {'name': 'fictional_pack', 'yaml': '# exact\n', 'etag': 'r', 'enabled': True}
        inv.delete_pack('fictional_pack')
        hive.delete.assert_called_once_with('fictional_pack')

    def test_a_legacy_template_is_sent_verbatim_and_the_engine_refusal_is_preserved(self, inv, mock_org):
        """The SDK converts nothing: the engine says `legacy_template_format` and the report comes back untouched."""
        source = 'description: old\nfacts:\n  a: {op: entity.get}\nproofs: []\n'
        response = {'valid': False, 'errors': [{'code': 'legacy_template_format', 'path': 'facts', 'message': 'old format'}], 'warnings': []}
        mock_org.client.request.return_value = response
        assert inv.validate_plan(source) == response
        assert json.loads(_request_args(mock_org)[2]['raw_body']) == {'yaml': source}


def test_validate_and_initial_test_preserve_each_resolved_pack(inv, mock_org):
    pins = [
        {'scope': 'root', 'name': 'fictional_context', 'version': 1, 'digest': 'a' * 64},
        {'scope': 'root/assessment', 'name': 'fictional_context', 'version': 2, 'digest': 'b' * 64},
    ]
    report = {'valid': True, 'resolved_packs': pins,
              'ai_rules': ['ai_says_benign'],
              'trust_provenance': [{'kind': 'pack', 'name': 'fictional_context'}]}
    source = 'gather:\n  context: {use: fictional_context, pack_version: 1}\n'
    mock_org.client.request.return_value = report
    assert inv.validate_plan(source) == report
    assert json.loads(_request_args(mock_org)[2]['raw_body']) == {'yaml': source}
    initial = {'state': 'running', 'test_id': 'test-1', 'validation': report}
    mock_org.client.request.return_value = initial
    assert inv.test_plan([{'inputs': {}}], inline=source, wait_seconds=0) == initial
    assert json.loads(_request_args(mock_org)[2]['raw_body'])['inline'] == source


@pytest.mark.parametrize("method,key", [("iter_runs", "runs"), ("iter_actions", "actions")])
def test_pagination_rejects_multicursor_cycles(inv, mock_org, method, key):
    mock_org.client.request.side_effect = [
        {key: [], "next_cursor": "A"},
        {key: [], "next_cursor": "B"},
        {key: [], "next_cursor": "A"},
    ]
    with pytest.raises(ApiError, match="repeated cursor"):
        list(getattr(inv, method)())
    assert mock_org.client.request.call_count == 3


@pytest.mark.parametrize("method,key", [("iter_runs", "runs"), ("iter_actions", "actions")])
def test_pagination_bounds_cursor_history(inv, mock_org, monkeypatch, method, key):
    monkeypatch.setattr(inv_mod, "_MAX_PAGINATION_CURSORS", 2)
    mock_org.client.request.side_effect = [
        {key: [], "next_cursor": cursor} for cursor in ("A", "B", "C")
    ]
    with pytest.raises(ApiError, match="cursor history limit"):
        list(getattr(inv, method)())
    assert mock_org.client.request.call_count == 3


def test_scalar_fixture_rejects_unknown_kind_clearly():
    with pytest.raises(pytest.fail.Exception, match="Unknown scalar fixture kind"):
        TestTemplateSource().test_args_scalars_are_read_as_the_engine_reads_them(
            {"src": "example", "kind": "unrecognized-collection"})


@pytest.mark.parametrize("spec,expected", [
    ({"lookups": []}, None),
    ({"values": []}, None),
    ({"lookups": [], "values": []}, None),
    ({"lookups": ["partners"], "values": []}, {"lookups": ["partners"]}),
    ({"lookups": [], "values": ["partner.example.test"]}, {"values": ["partner.example.test"]}),
])
def test_start_run_normalizes_trust_without_mutating_caller(inv, mock_org, spec, expected):
    import copy
    request = {"trigger": {"question": "example"}, "trust": spec}
    original = copy.deepcopy(request)
    inv.start_run(request)
    sent = json.loads(_request_args(mock_org)[2]["raw_body"])
    if expected is None:
        assert "trust" not in sent
    else:
        assert sent["trust"] == expected
    assert request == original
    assert request["trust"] is spec


@pytest.mark.parametrize("spec", [
    "invalid", [], False, {"extra": []},
    {"lookups": "partners"}, {"values": "partner.example.test"},
    {"lookups": None}, {"values": None},
    {"lookups": [None]}, {"values": [None]},
    {"lookups": [1]}, {"values": [False]},
    {"lookups": [""]}, {"values": [""]},
    {"lookups": [" \t"]}, {"values": ["\n "]},
    {"lookups": ["partners"] * 65}, {"values": ["partner.example.test"] * 101},
])
def test_invalid_start_trust_is_rejected_before_request(inv, mock_org, spec):
    with pytest.raises(ValidationError, match="trust"):
        inv.start_run({"trigger": {"question": "example"}, "trust": spec})
    mock_org.client.request.assert_not_called()


def test_start_trust_accepts_exact_entry_limits(inv, mock_org):
    spec = {"lookups": [f"partners-{i}" for i in range(64)],
            "values": [f"partner-{i}.example.test" for i in range(100)]}
    inv.start_run({"trigger": {"question": "example"}, "trust": spec})
    assert json.loads(_request_args(mock_org)[2]["raw_body"])["trust"] == spec
