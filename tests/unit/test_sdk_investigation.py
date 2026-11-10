"""Tests for limacharlie.sdk.investigation (Investigation Engine)."""

import json
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


VALID = {"valid": True, "errors": [], "warnings": [{"code": "unused_fact", "path": "facts.x", "message": "m"}]}
INVALID = {"valid": False, "errors": [{"code": "unknown_field", "path": "facts.a", "message": "m", "suggestion": "b"}], "warnings": []}

SRC = "description: test plan\nfacts:\n  a:\n    op: entity.get\n    args: {entity_id: $entity}\n"


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

    def test_autonomy_switch(self, inv, mock_org):
        mock_org.client.request.return_value = {}
        inv.set_autonomy("pause")
        assert _request_args(mock_org)[:2] == ("POST", "investigate/oid-1/autonomy/pause")
        with pytest.raises(ValidationError):
            inv.set_autonomy("stop")

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
            inv.get_autonomy()
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

class TestTemplateSource:
    def test_yaml_1_1_surprises_stay_text(self):
        data = parse_template_source("a: yes\nb: off\nc: 2026-11-10\nd: true\ne: [on]\nf: 10:30\ng: 012\nh: 1_000\n")
        assert data == {"a": "yes", "b": "off", "c": "2026-11-10", "d": True, "e": ["on"],
                        "f": "10:30", "g": "012", "h": "1_000"}

    def test_yaml_1_2_numbers_are_numbers(self):
        data = parse_template_source("a: 12\nb: -3\nc: 1.5\nd: 1e3\ne: 0x1f\nf: 0o17\ng: 0\nh: .5\ni: null\n")
        assert data == {"a": 12, "b": -3, "c": 1.5, "d": 1000.0, "e": 31, "f": 15, "g": 0, "h": 0.5, "i": None}
        assert type(data["a"]) is int

    def test_dump_round_trips_text_that_looks_like_something_else(self):
        data = {"a": "yes", "c": "2026-11-10", "n": "0308"}
        assert parse_template_source(dump_template(data)) == data

    def test_dump_keeps_key_order(self):
        text = dump_template({"zebra": 1, "alpha": 2})
        assert text.index("zebra") < text.index("alpha")

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
        data = {"description": "test plan", "facts": {"a": {"op": "entity.get", "args": {"entity_id": "$entity"}}}, "status": "draft"}
        landed = HiveRecord(name="my-plan", data=data, etag="e9")
        hive.get.side_effect = [_not_found(), landed, landed]
        hive.set.side_effect = error_from_status_code(400, {"error": "lc_error_code:ETAG_MISMATCH"})
        assert inv.save_template("my-plan", SRC)["saved"] is True

    def test_a_write_that_failed_and_did_not_land_is_an_error(self, inv, mock_org, hive):
        mock_org.client.request.return_value = VALID
        hive.get.side_effect = [_not_found(), _not_found()]
        hive.set.side_effect = error_from_status_code(400, {"error": "lc_error_code:ETAG_MISMATCH"})
        with pytest.raises(ApiError):
            inv.save_template("my-plan", SRC)


class TestTemplateRecordPermissions:
    def test_a_refused_hive_operation_names_the_investigation_plan_permissions(self, inv, hive):
        hive.get.side_effect = error_from_status_code(400, {"error": "lc_error_code:UNAUTHORIZED - nope"})
        with pytest.raises(InvestigationError) as ei:
            inv.get_template("x")
        assert "investigation_plan.get" in ei.value.suggestion and ei.value.status_code == 403

    def test_other_hive_failures_are_not_rewritten(self, inv, hive):
        hive.delete.side_effect = error_from_status_code(500, "boom")
        with pytest.raises(ApiError) as ei:
            inv.delete_template("x")
        assert not isinstance(ei.value, InvestigationError)


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
        {"name": "alpha", "version": 2, "status": "active", "yaml": "description: a\nstatus: active\nfacts: {}\n"},
        {"name": "beta", "version": 1, "status": "active", "yaml": "description: b\nfacts: {}\n"},
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
