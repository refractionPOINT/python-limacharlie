"""Tests for the ``limacharlie investigate`` CLI group."""

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from limacharlie.cli import cli
from limacharlie.errors import AuthenticationError, error_from_status_code
from limacharlie.sdk.investigation import InvestigationError


@pytest.fixture
def sdk():
    """A mocked Investigation instance behind the CLI (no Client, no network)."""
    with patch("limacharlie.commands.investigate.Client"), \
            patch("limacharlie.commands.investigate.Organization"), \
            patch("limacharlie.commands.investigate.Investigation") as cls:
        inst = MagicMock()
        cls.return_value = inst
        yield inst


def run(args, input=None, fmt="json"):
    result = CliRunner(mix_stderr=False).invoke(cli, ["--output", fmt] + args, input=input)
    return result


def out_json(result):
    return json.loads(result.stdout)


def issue_error(status=400, issues=None):
    issues = issues or [{"code": "unknown_field", "path": "steps[0].select[0]", "message": "no field", "suggestion": "hosts_30d"}]
    return InvestigationError(
        "the wave is invalid", status_code=status, issues=issues, warnings=[{"code": "operator_denied"}],
        response_body={"error": "the wave is invalid", "error_code": "bad_request", "errors": issues},
        exit_code=1,
    )


class TestHelp:
    def test_group_and_nested_help(self):
        runner = CliRunner()
        out = runner.invoke(cli, ["investigate", "--help"]).output
        for name in ("kit", "operators", "packs", "templates", "runs", "wave", "actions", "settings"):
            assert name in out
        out = runner.invoke(cli, ["investigate", "templates", "--help"]).output
        for name in ("list", "get", "validate", "test", "save", "promote", "delete", "install-defaults"):
            assert name in out

    def test_ai_help_carries_the_agent_workflow(self):
        result = CliRunner().invoke(cli, ["investigate", "--ai-help"])
        assert result.exit_code == 0
        assert "promote" in result.output and "validate" in result.output

    def test_kit_section_is_a_closed_set(self):
        result = CliRunner().invoke(cli, ["investigate", "kit", "--section", "bogus"])
        assert result.exit_code != 0


class TestKitAndCatalogues:
    def test_kit_sections_are_passed_through(self, sdk):
        sdk.get_authoring_kit.return_value = {"guide": "g", "size": {"approx_tokens": 10}}
        result = run(["investigate", "kit", "--section", "guide", "--section", "library"])
        assert result.exit_code == 0, result.stderr
        sdk.get_authoring_kit.assert_called_once_with(["guide", "library"])
        assert out_json(result)["guide"] == "g"

    def test_no_section_asks_for_the_default_kit(self, sdk):
        sdk.get_authoring_kit.return_value = {}
        run(["investigate", "kit"])
        sdk.get_authoring_kit.assert_called_once_with(None)

    def test_operators_brief_and_name_filters(self, sdk):
        sdk.list_operators.return_value = {
            "operators": [
                {"name": "ioc.prevalence", "class": "index", "description": "how widespread", "available": True, "why": "", "args": [1], "output": {}},
                {"name": "entity.get", "class": "free", "description": "an entity", "available": False, "why": "denied", "args": [2]},
            ],
            "extension_requests": ["ext/a"],
        }
        data = out_json(run(["investigate", "operators", "--brief", "--name", "entity.get"]))
        assert data["operators"] == [{"name": "entity.get", "class": "free", "description": "an entity", "available": False, "why": "denied"}]
        assert data["extension_requests"] == ["ext/a"]
        data = out_json(run(["investigate", "operators", "--match", "WIDESPREAD"]))
        assert [o["name"] for o in data["operators"]] == ["ioc.prevalence"]
        assert "args" in data["operators"][0]

    def test_packs_brief_is_a_compact_index(self, sdk):
        sdk.list_packs.return_value = {"packs": [{
            "name": "host_context", "brief": "who", "description": "long", "version": 1,
            "params": [{"name": "sid", "type": "string", "required": True, "description": "Sensor id."}],
            "exports": [{"name": "hostname", "type": "string", "ref": "<id>__card.display_name", "brief": "name", "description": "long"}],
        }]}
        data = out_json(run(["investigate", "packs", "--brief", "--name", "host_context"]))
        sdk.list_packs.assert_called_once_with("host_context")
        assert data["packs"] == [{
            "name": "host_context", "brief": "who", "version": 1,
            "params": [{"name": "sid", "type": "string", "required": True}],
            "exports": [{"name": "hostname", "type": "string", "ref": "<id>__card.display_name", "brief": "name"}],
        }]


class TestTemplates:
    def test_list_filters_by_status(self, sdk):
        sdk.list_engine_templates.return_value = {"templates": [
            {"name": "a", "status": "active"}, {"name": "b", "status": "draft"}, {"name": "c"}]}
        data = out_json(run(["investigate", "templates", "list", "--status", "draft"]))
        assert [t["name"] for t in data["templates"]] == ["b", "c"]  # no status means draft

    def test_get_yaml_prints_only_the_source(self, sdk):
        sdk.get_template.return_value = {"name": "a", "yaml": "description: x\n"}
        result = run(["investigate", "templates", "get", "a", "--yaml"])
        assert result.stdout == "description: x\n"

    def test_validate_exit_code_follows_the_report(self, sdk, tmp_path):
        f = tmp_path / "plan.yaml"
        f.write_text("description: x\n", encoding="utf-8")
        sdk.validate_plan.return_value = {"valid": True, "errors": [], "warnings": []}
        assert run(["investigate", "templates", "validate", "--file", str(f)]).exit_code == 0
        sdk.validate_plan.assert_called_with("description: x\n")
        report = {"valid": False, "errors": [{"code": "unknown_field", "path": "p", "message": "m", "suggestion": "s"}], "warnings": []}
        sdk.validate_plan.return_value = report
        result = run(["investigate", "templates", "validate", "--file", str(f)])
        assert result.exit_code == 4
        assert out_json(result)["errors"] == report["errors"]

    def test_validate_reads_stdin(self, sdk):
        sdk.validate_plan.return_value = {"valid": True, "errors": []}
        run(["investigate", "templates", "validate", "--file", "-"], input="description: piped\n")
        sdk.validate_plan.assert_called_with("description: piped\n")

    def test_save_is_a_draft_unless_a_person_says_otherwise(self, sdk, tmp_path):
        f = tmp_path / "plan.yaml"
        f.write_text("description: x\n", encoding="utf-8")
        sdk.save_template.return_value = {"saved": True, "status": "draft"}
        assert run(["investigate", "templates", "save", "my-plan", "--file", str(f), "--comment", "10 samples"]).exit_code == 0
        sdk.save_template.assert_called_with(
            "my-plan", "description: x\n", status="draft", overwrite=False, comment="10 samples", tags=None)
        run(["investigate", "templates", "save", "my-plan", "--file", str(f), "--status", "active", "--overwrite", "--tag", "t"])
        sdk.save_template.assert_called_with(
            "my-plan", "description: x\n", status="active", overwrite=True, comment=None, tags=["t"])

    def test_refused_save_exits_4_and_says_why(self, sdk, tmp_path):
        f = tmp_path / "plan.yaml"
        f.write_text("description: x\n", encoding="utf-8")
        sdk.save_template.return_value = {"saved": False, "reason": "already exists", "validation": {"errors": []}}
        result = run(["investigate", "templates", "save", "my-plan", "--file", str(f)])
        assert result.exit_code == 4
        assert out_json(result)["reason"] == "already exists"

    def test_promote_and_delete_need_confirm(self, sdk):
        for verb in ("promote", "delete"):
            result = run(["investigate", "templates", verb, "my-plan"])
            assert result.exit_code != 0 and "--confirm" in result.stderr
        sdk.promote_template.assert_not_called()
        sdk.delete_template.assert_not_called()

    def test_promote_confirmed(self, sdk):
        sdk.promote_template.return_value = {"promoted": True, "status": "active"}
        assert run(["investigate", "templates", "promote", "my-plan", "--confirm"]).exit_code == 0
        sdk.promote_template.assert_called_once_with("my-plan")
        sdk.promote_template.return_value = {"promoted": False, "reason": "does not validate"}
        assert run(["investigate", "templates", "promote", "my-plan", "--confirm"]).exit_code == 4

    def test_install_defaults_arguments_and_failure_exit(self, sdk):
        sdk.install_default_templates.return_value = {"written": [], "skipped": [], "failed": []}
        run(["investigate", "templates", "install-defaults", "--name", "a", "--name", "b", "--overwrite"])
        sdk.install_default_templates.assert_called_with(["a", "b"], overwrite=True, status="draft")
        run(["investigate", "templates", "install-defaults"])
        sdk.install_default_templates.assert_called_with(None, overwrite=False, status="draft")
        sdk.install_default_templates.return_value = {"written": [], "skipped": [], "failed": [{"name": "a"}]}
        assert run(["investigate", "templates", "install-defaults"]).exit_code == 1


class TestTemplateTest:
    DONE = {
        "test_id": "t1", "state": "done", "done": True, "samples_done": 3, "samples_total": 3,
        "results": [
            {"index": 0, "sample": {"detection_id": "d1"}, "state": "ok",
             "verdict": {"outcome": "closed_by_rule", "label": "false_positive", "decided": True, "decided_by": {"kind": "rule", "rule": "known_sender"}},
             "expected": {"label": "false_positive"}, "agreement": {"rule": "agree", "ai": "none"}, "unknowns": [],
             "steps": [{"fact": "a", "status": "ok"}, {"fact": "b", "status": "unknown", "reason": "index_lag"}]},
            {"index": 1, "sample": {"case_id": "9"}, "state": "ok",
             "verdict": {"outcome": "escalated_by_rule", "label": "true_positive", "decided": True, "decided_by": {"kind": "rule", "rule": "clicked_link"}},
             "expected": {"label": "false_positive"}, "agreement": {"rule": "disagree", "ai": "none"}, "unknowns": [{"fact": "b"}]},
            {"index": 2, "sample": {"case_id": "10"}, "state": "ok",
             "verdict": {"outcome": "ai_recommends_benign", "label": "inconclusive", "decided": False,
                         "recommendation": {"label": "benign", "self_rated_confidence": 0.8, "citations": ["b.x"], "by": "ai_review"},
                         "missing": [{"step": "b", "reason": "index_lag", "needed_by": ["known_sender"], "ask": "Has it written before?"}]},
             "expected": {"label": "false_positive"}, "agreement": {"rule": "none", "ai": "agree"}},
        ],
        "summary": {"samples": 3, "ran": 3, "decided_by_rules": 2, "rule_share": 0.67,
                    "by_outcome": {"closed_by_rule": 1, "escalated_by_rule": 1, "ai_recommends_benign": 1},
                    "rules": {"known_sender": {"decided": 1, "agree": 1, "disagree": 0}, "clicked_link": {"decided": 1, "agree": 0, "disagree": 1}},
                    "ai": {"recommended": 1, "agree": 1, "disagree": 0, "unclear": 0}, "unknown_reasons": {"index_lag": 1}},
    }

    def test_samples_are_built_from_every_flag(self, sdk, tmp_path):
        sdk.test_plan.return_value = dict(self.DONE)
        sf = tmp_path / "s.yaml"
        sf.write_text("- {detection_id: from-file}\n", encoding="utf-8")
        result = run([
            "investigate", "templates", "test", "my-plan", "--detection-id", "d1", "--case-id", "9",
            "--detect-cat", "cat-a", "--last", "3", "--sample", '{"inputs": {"k": "v"}, "expected": "false_positive"}',
            "--samples-file", str(sf), "--strict", "--mode", "full", "--wait", "2",
        ])
        assert result.exit_code == 0, result.stderr
        args, kwargs = sdk.test_plan.call_args
        assert args[0] == [
            {"detection_id": "d1"}, {"case_id": "9"}, {"detect_cat": "cat-a", "last": 3},
            {"inputs": {"k": "v"}, "expected": "false_positive"}, {"detection_id": "from-file"},
        ]
        assert kwargs == {"template": "my-plan", "inline": None, "overrides": None, "strict": True, "mode": "full", "wait_seconds": 2}

    def test_inline_file_is_sent_as_the_plan(self, sdk, tmp_path):
        sdk.test_plan.return_value = dict(self.DONE)
        f = tmp_path / "plan.yaml"
        f.write_text("description: draft\n", encoding="utf-8")
        run(["investigate", "templates", "test", "--file", str(f), "--detection-id", "d1"])
        assert sdk.test_plan.call_args.kwargs["inline"] == "description: draft\n"
        assert sdk.test_plan.call_args.kwargs["template"] is None

    def test_usage_errors_before_any_call(self, sdk):
        assert run(["investigate", "templates", "test", "--detection-id", "d"]).exit_code != 0  # no plan
        assert run(["investigate", "templates", "test", "a", "--file", "f", "--detection-id", "d"]).exit_code != 0
        assert run(["investigate", "templates", "test", "a"]).exit_code != 0  # no sample
        assert run(["investigate", "templates", "test", "--test-id", "t", "a"]).exit_code != 0
        sdk.test_plan.assert_not_called()

    def test_json_drops_the_steps_that_succeeded(self, sdk):
        sdk.test_plan.return_value = dict(self.DONE)
        results = out_json(run(["investigate", "templates", "test", "p", "--detection-id", "d1"]))["results"]
        assert "steps" not in results[0]
        assert results[0]["problem_steps"] == [{"fact": "b", "status": "unknown", "reason": "index_lag"}]
        assert results[0]["steps_total"] == 2
        full = out_json(run(["investigate", "templates", "test", "p", "--detection-id", "d1", "--include-steps"]))["results"]
        assert len(full[0]["steps"]) == 2

    def test_a_running_test_is_waited_for_and_a_timeout_leaves_the_handle(self, sdk):
        running = {"test_id": "t1", "state": "running", "done": False, "samples_done": 0}
        sdk.test_plan.return_value = running
        sdk.wait_for_test.return_value = dict(self.DONE)
        result = run(["investigate", "templates", "test", "p", "--detection-id", "d", "--timeout", "30"])
        sdk.wait_for_test.assert_called_once_with(running, timeout=30.0)
        assert out_json(result)["state"] == "done"

        sdk.wait_for_test.return_value = running
        result = run(["investigate", "templates", "test", "p", "--detection-id", "d"])
        assert result.exit_code == 0
        assert "--test-id t1" in result.stderr

    def test_no_wait_returns_the_started_test(self, sdk):
        sdk.test_plan.return_value = {"test_id": "t1", "state": "running", "done": False}
        result = run(["investigate", "templates", "test", "p", "--detection-id", "d", "--no-wait"])
        sdk.wait_for_test.assert_not_called()
        assert out_json(result)["test_id"] == "t1"

    def test_resume_by_test_id(self, sdk):
        sdk.get_test_plan.return_value = dict(self.DONE)
        result = run(["investigate", "templates", "test", "--test-id", "t1"])
        assert result.exit_code == 0
        assert sdk.get_test_plan.call_args.args == ("t1",)
        sdk.test_plan.assert_not_called()

    def test_invalid_and_failed_tests_have_exit_codes(self, sdk):
        invalid = {"test_id": "t", "state": "invalid", "done": True,
                   "validation": {"valid": False, "errors": [{"code": "bad_expression", "path": "x", "message": "m"}]}}
        sdk.test_plan.return_value = invalid
        result = run(["investigate", "templates", "test", "p", "--detection-id", "d"])
        assert result.exit_code == 4
        assert out_json(result)["validation"]["errors"][0]["code"] == "bad_expression"
        sdk.test_plan.return_value = {"test_id": "t", "state": "failed", "done": True, "error": "gone"}
        assert run(["investigate", "templates", "test", "p", "--detection-id", "d"]).exit_code == 1

    def test_table_output_shows_who_decided_each_sample_and_the_per_rule_summary(self, sdk):
        sdk.test_plan.return_value = dict(self.DONE)
        result = run(["investigate", "templates", "test", "p", "--detection-id", "d"], fmt="table")
        assert result.exit_code == 0, result.stderr
        out = result.stdout
        assert "closed_by_rule" in out and "known_sender" in out and "ai_recommends_benign" in out
        assert "disagree" in out
        assert "decided_by_rules=2" in out and "rule_share=0.67" in out
        assert "rule clicked_link: decided=1 agree=0 disagree=1" in out
        assert "rule known_sender: decided=1 agree=1 disagree=0" in out
        assert "ai: recommended=1, agree=1, disagree=0, unclear=0" in out
        assert "outcomes: {'closed_by_rule': 1" in out
        assert "unknown reasons: {'index_lag': 1}" in out
        assert "agreement_rate" not in out


class TestRuns:
    def test_start_builds_the_request(self, sdk):
        sdk.start_run.return_value = {"run": {"run_id": "r1"}, "joined": False}
        result = run([
            "investigate", "runs", "start", "--template", "my-plan", "--detection-id", "d1",
            "--input", "hash=0e123", "--inputs-json", '{"n": 3}', "--urgency", "high", "--mode", "full",
            "--case-mode", "none", "--idempotency-key", "k", "--wait", "20",
        ])
        assert result.exit_code == 0, result.stderr
        sdk.start_run.assert_called_once_with({
            "trigger": {"detection_id": "d1"}, "plan": {"template": "my-plan"},
            "inputs": {"hash": "0e123", "n": 3}, "urgency": "high", "mode": "full", "case": "none",
            "idempotency_key": "k", "wait_seconds": 20,
        })

    def test_start_plan_choices(self, sdk, tmp_path):
        sdk.start_run.return_value = {"run": {"run_id": "r1"}}
        run(["investigate", "runs", "start", "--auto", "--case-id", "5"])
        # The engine refuses plan.auto for a person's run; no plan at all is what asks it to pick by applies_to.
        assert sdk.start_run.call_args.args[0] == {"trigger": {"case_id": "5"}}
        f = tmp_path / "p.yaml"
        f.write_text("description: x\n", encoding="utf-8")
        run(["investigate", "runs", "start", "--file", str(f), "--question", "why?"])
        assert sdk.start_run.call_args.args[0] == {"trigger": {"question": "why?"}, "plan": {"inline": "description: x\n"}}

    def test_start_auto_sends_the_alert_attributes_applies_to_matches_on(self, sdk):
        sdk.start_run.return_value = {"run": {"run_id": "r1"}}
        result = run(["investigate", "runs", "start", "--auto", "--detection-id", "d", "--category", "encoded-ps",
                      "--severity", "high", "--priority", "7", "--tag", "a", "--tag", "b"])
        assert result.exit_code == 0, result.stderr
        assert sdk.start_run.call_args.args[0] == {"trigger": {
            "detection_id": "d", "category": "encoded-ps", "severity": "high", "priority": 7, "tags": ["a", "b"]}}

    def test_start_urgency_is_the_engines_set(self, sdk):
        sdk.start_run.return_value = {"run": {"run_id": "r1"}}
        for urgency in ("low", "medium", "high", "critical"):
            assert run(["investigate", "runs", "start", "--template", "a", "--detection-id", "d", "--urgency", urgency]).exit_code == 0
            assert sdk.start_run.call_args.args[0]["urgency"] == urgency
        sdk.start_run.reset_mock()
        assert run(["investigate", "runs", "start", "--template", "a", "--detection-id", "d", "--urgency", "normal"]).exit_code != 0
        sdk.start_run.assert_not_called()

    def test_start_help_describes_auto_and_urgency_as_the_engine_does(self):
        out = " ".join(CliRunner().invoke(cli, ["investigate", "runs", "start", "--help"]).output.split())
        assert "low|medium|high|critical" in out
        assert "normal" not in out
        assert "applies_to" in out and "sends no plan" in out

    def test_start_usage_errors(self, sdk):
        assert run(["investigate", "runs", "start", "--detection-id", "d"]).exit_code != 0
        assert run(["investigate", "runs", "start", "--template", "a", "--auto", "--detection-id", "d"]).exit_code != 0
        assert run(["investigate", "runs", "start", "--template", "a"]).exit_code != 0
        assert run(["investigate", "runs", "start", "--template", "a", "--detection-id", "d", "--input", "novalue"]).exit_code != 0
        sdk.start_run.assert_not_called()

    def test_start_follow_streams_the_new_run(self, sdk):
        sdk.start_run.return_value = {"run": {"run_id": "r1"}, "joined": False}

        def events(run_id, **kw):
            state = kw["state"]
            state.update(next=2, done=True)
            yield {"seq": 1, "type": "step", "data": {}}
            yield {"seq": 2, "type": "verdict", "data": {}}
        sdk.iter_run_events.side_effect = events
        result = run(["investigate", "runs", "start", "--template", "p", "--detection-id", "d", "--follow"])
        assert result.exit_code == 0
        assert sdk.iter_run_events.call_args.args == ("r1",)
        assert [json.loads(line).get("seq") for line in result.stdout.splitlines()] == [None, 1, 2]

    def test_follow_in_a_structured_format_is_json_lines_from_the_first_line(self, sdk):
        sdk.start_run.return_value = {"run": {"run_id": "r1"}, "joined": False}

        def events(run_id, **kw):
            kw["state"].update(next=1, done=True)
            yield {"seq": 1, "type": "step", "data": {}}
        sdk.iter_run_events.side_effect = events
        result = run(["investigate", "runs", "start", "--template", "p", "--detection-id", "d", "--follow"])
        lines = result.stdout.splitlines()
        assert [json.loads(line) for line in lines] == [
            {"run": {"run_id": "r1"}, "joined": False}, {"seq": 1, "type": "step", "data": {}}]

    def test_list_pages_with_a_cursor_envelope(self, sdk):
        sdk.list_runs.return_value = {"runs": [{"run_id": "r1"}], "next_cursor": "c2"}
        result = run(["investigate", "runs", "list", "--state", "running", "--limit", "10", "--cursor", "c1", "--since", "2026-11-01T00:00:00Z"])
        assert out_json(result) == {"runs": [{"run_id": "r1"}], "next_cursor": "c2"}
        kwargs = sdk.list_runs.call_args.kwargs
        assert kwargs["state"] == "running" and kwargs["limit"] == 10 and kwargs["cursor"] == "c1"
        assert kwargs["since"] == "2026-11-01T00:00:00Z" and kwargs["verdict"] is None and kwargs["outcome"] is None

    def test_list_filters_pass_the_engines_values_through(self, sdk):
        sdk.list_runs.return_value = {"runs": [], "next_cursor": ""}
        run(["investigate", "runs", "list", "--verdict", "undecided", "--trigger", "detection", "--started-by", "a@x.io"])
        kwargs = sdk.list_runs.call_args.kwargs
        assert (kwargs["verdict"], kwargs["trigger"], kwargs["started_by"]) == ("undecided", "detection", "a@x.io")

    @pytest.mark.parametrize("outcome", ["closed_by_rule", "escalated_by_rule", "closed_by_ai", "escalated_by_ai",
                                         "ai_recommends_benign", "ai_recommends_malicious", "couldnt_tell", "conflict", "undecided"])
    def test_list_filters_by_outcome(self, sdk, outcome):
        sdk.list_runs.return_value = {"runs": [], "next_cursor": ""}
        assert run(["investigate", "runs", "list", "--outcome", outcome]).exit_code == 0
        assert sdk.list_runs.call_args.kwargs["outcome"] == outcome

    def test_list_refuses_a_label_as_an_outcome_before_any_call(self, sdk):
        result = run(["investigate", "runs", "list", "--outcome", "false_positive"])
        assert result.exit_code == 2
        sdk.list_runs.assert_not_called()

    def test_list_all_keeps_the_outcome_filter(self, sdk):
        sdk.iter_runs.return_value = iter([])
        run(["investigate", "runs", "list", "--all", "--outcome", "couldnt_tell"])
        assert sdk.iter_runs.call_args.kwargs["outcome"] == "couldnt_tell"

    def test_list_help_names_the_engines_trigger_kinds(self):
        out = " ".join(CliRunner().invoke(cli, ["investigate", "runs", "list", "--help"]).output.split())
        assert "detection, message, entity, case, question" in out and "undecided" in out
        assert "--outcome" in out and "ai_recommends_benign" in out
        assert "dr-rule" not in out

    def test_strict_help_says_it_refuses_loosening_overrides(self):
        out = " ".join(CliRunner().invoke(cli, ["investigate", "templates", "test", "--help"]).output.split())
        assert "loosen" in out and "unknown as a failure" not in out

    def test_list_table_rows_and_cursor_on_stderr(self, sdk):
        sdk.list_runs.return_value = {"runs": [{
            "run_id": "r1", "state": "completed", "template": "p",
            "verdict": {"outcome": "closed_by_rule", "label": "false_positive", "decided": True, "decided_by": {"kind": "rule", "rule": "known_sender", "say": "s"}},
            "started_by": {"identity": "user:u", "actor": "a@x.io"}, "created": "2026-11-10T00:00:00Z"}], "next_cursor": "c2"}
        result = run(["investigate", "runs", "list"], fmt="csv")
        assert "closed_by_rule" in result.stdout and "known_sender" in result.stdout
        assert "false_positive" in result.stdout and "a@x.io" in result.stdout
        header = result.stdout.splitlines()[0]
        assert "outcome" in header and "decided_by" in header
        assert "next_cursor: c2" in result.stderr

    def test_list_all_follows_every_page(self, sdk):
        sdk.iter_runs.return_value = iter([{"run_id": "a"}, {"run_id": "b"}])
        data = out_json(run(["investigate", "runs", "list", "--all", "--template", "p"]))
        assert data == {"runs": [{"run_id": "a"}, {"run_id": "b"}], "next_cursor": ""}
        assert sdk.iter_runs.call_args.kwargs["template"] == "p"

    def test_events_single_poll(self, sdk):
        sdk.get_run_events.return_value = {"events": [{"seq": 4}], "next": 4, "done": False}
        data = out_json(run(["investigate", "runs", "events", "r1", "--after", "3", "--wait", "5", "--limit", "20"]))
        sdk.get_run_events.assert_called_once_with("r1", after=3, wait=5, limit=20)
        assert data["next"] == 4

    def test_follow_streams_one_json_event_per_line_and_ends_ok_when_done(self, sdk):
        def events(run_id, **kw):
            kw["state"].update(next=2, done=True, timed_out=False)
            yield {"seq": 1, "at": "t", "type": "step", "data": {"a": 1}}
            yield {"seq": 2, "at": "t", "type": "run_done", "data": {}}
        sdk.iter_run_events.side_effect = events
        result = run(["investigate", "runs", "events", "r1", "--follow", "--after", "0"])
        assert result.exit_code == 0
        assert [json.loads(line)["seq"] for line in result.stdout.splitlines()] == [1, 2]
        assert sdk.iter_run_events.call_args.kwargs["wait"] == 10
        assert sdk.iter_run_events.call_args.kwargs["timeout"] == 900

    def test_follow_timeout_exits_1_with_the_resume_point(self, sdk):
        def events(run_id, **kw):
            kw["state"].update(next=7, done=False, timed_out=True)
            yield {"seq": 7, "at": "t", "type": "step", "data": {}}
        sdk.iter_run_events.side_effect = events
        result = run(["investigate", "runs", "events", "r1", "--follow", "--timeout", "5"])
        assert result.exit_code == 1
        assert "--after 7" in result.stderr

    def test_follow_text_lines_in_table_mode(self, sdk):
        def events(run_id, **kw):
            kw["state"].update(next=1, done=True)
            yield {"seq": 1, "at": "2026-11-10T00:00:00Z", "type": "step", "data": {"fact": "a"}}
        sdk.iter_run_events.side_effect = events
        result = run(["investigate", "runs", "events", "r1", "--follow"], fmt="table")
        assert result.stdout.strip() == '1\t2026-11-10T00:00:00Z\tstep\t{"fact":"a"}'

    def test_delete_requires_confirmation_before_constructing_sdk(self, sdk):
        result = run(["investigate", "runs", "delete", "r1"])
        assert result.exit_code == 2
        assert "--confirm" in result.stderr
        sdk.delete_run.assert_not_called()
        from limacharlie.commands.investigate import Investigation
        Investigation.assert_not_called()

    def test_delete_passes_run_id_and_prints_response(self, sdk):
        sdk.delete_run.return_value = {"deleted": True}
        result = run(["investigate", "runs", "delete", "run:1", "--confirm"])
        assert result.exit_code == 0, result.stderr
        assert out_json(result) == {"deleted": True}
        sdk.delete_run.assert_called_once_with("run:1")
        sdk.cancel_run.assert_not_called()

    def test_delete_error_uses_normal_engine_rendering(self, sdk):
        err = issue_error()
        sdk.delete_run.side_effect = err
        result = run(["investigate", "runs", "delete", "r1", "--confirm"])
        assert result.exit_code == err.exit_code
        assert result.stdout == ""
        assert json.loads(result.stderr)["error_code"] == err.error_code
        sdk.delete_run.assert_called_once_with("r1")

    def test_delete_is_discoverable_and_explained(self):
        from limacharlie.discovery import PROFILES
        assert "investigate runs delete" in PROFILES["investigation_engine"]["commands"]
        result = CliRunner().invoke(cli, ["investigate", "runs", "delete", "--ai-help"])
        assert result.exit_code == 0
        assert "investigation.set" in result.output and "--confirm" in result.output

    def test_get_steps_case_cancel(self, sdk):
        sdk.get_run.return_value = {"run_id": "r1"}
        run(["investigate", "runs", "get", "r1"])
        sdk.get_run.assert_called_once_with("r1")
        run(["investigate", "runs", "steps", "r1", "--values"])
        sdk.get_run_steps.assert_called_once_with("r1", values=True)
        run(["investigate", "runs", "case", "r1"])
        sdk.get_run_case.assert_called_once_with("r1")
        run(["investigate", "runs", "cancel", "r1", "--revert-leases"])
        sdk.cancel_run.assert_called_once_with("r1", revert_leases=True)


class TestWave:
    def test_flags_are_merged_into_the_file(self, sdk, tmp_path):
        f = tmp_path / "wave.yaml"
        f.write_text(
            "steps:\n  - {id: host, use: host_context, args: {sid: abc}}\n"
            "stop_when: ['host__resolve.found == false']\ndeadline_ms: 5000\ninputs: {a: '1'}\n", encoding="utf-8")
        sdk.run_wave.return_value = {"results": [], "compact": True}
        result = run(["investigate", "wave", "--file", str(f), "--stop-when", "x == 1", "--deadline-ms", "9000",
                      "--input", "b=2", "--full", "--validate-only"])
        assert result.exit_code == 0, result.stderr
        assert sdk.run_wave.call_args.args[0] == {
            "steps": [{"id": "host", "use": "host_context", "args": {"sid": "abc"}}],
            "stop_when": ["host__resolve.found == false", "x == 1"], "deadline_ms": 9000,
            "inputs": {"a": "1", "b": "2"}, "full": True, "validate_only": True,
        }

    def test_a_bare_list_is_the_steps(self, sdk, tmp_path):
        f = tmp_path / "wave.json"
        f.write_text('[{"id": "a", "op": "entity.get", "args": {}}]', encoding="utf-8")
        sdk.run_wave.return_value = {}
        run(["investigate", "wave", "--file", str(f)])
        assert sdk.run_wave.call_args.args[0] == {"steps": [{"id": "a", "op": "entity.get", "args": {}}]}

    def test_a_refused_wave_prints_the_coded_errors_on_stdout_and_exits_4(self, sdk, tmp_path):
        f = tmp_path / "wave.json"
        f.write_text('{"steps": [{"id": "a", "op": "x"}]}', encoding="utf-8")
        err = issue_error()
        sdk.run_wave.side_effect = err
        result = run(["investigate", "wave", "--file", str(f)])
        assert result.exit_code == 4
        body = out_json(result)
        assert body["valid"] is False and body["errors"] == err.issues and body["warnings"] == err.warnings

    def test_validate_only_with_an_invalid_report_exits_4(self, sdk, tmp_path):
        f = tmp_path / "wave.json"
        f.write_text('{"steps": [{"id": "a", "op": "x"}]}', encoding="utf-8")
        sdk.run_wave.return_value = {"valid": False, "errors": [{"code": "unknown_operator"}], "warnings": []}
        assert run(["investigate", "wave", "--file", str(f), "--validate-only"]).exit_code == 4

    def test_a_wave_failure_without_issues_is_a_plain_error(self, sdk, tmp_path):
        f = tmp_path / "wave.json"
        f.write_text('{"steps": [{"id": "a", "op": "x"}]}', encoding="utf-8")
        sdk.run_wave.side_effect = InvestigationError("timed out", status_code=504, exit_code=1)
        result = run(["investigate", "wave", "--file", str(f)])
        assert result.exit_code == 1
        assert json.loads(result.stderr)["error"] == "timed out"


class TestActionsAndSettings:
    def test_actions_list_all_walks_every_page(self, sdk):
        sdk.iter_actions.return_value = iter([{"id": "a1", "run_id": "r1"}, {"id": "a2", "run_id": "r2"}])
        data = out_json(run(["investigate", "actions", "list", "--state", "awaiting_approval,proposed", "--class", "tag", "--all"]))
        assert [a["id"] for a in data["actions"]] == ["a1", "a2"] and data["next_cursor"] == ""
        assert sdk.iter_actions.call_args.kwargs == {
            "state": "awaiting_approval,proposed", "action_class": "tag", "run_id": None, "limit": None, "cursor": None}
        sdk.list_actions.assert_not_called()

    def test_one_page_keeps_the_cursor(self, sdk):
        sdk.list_actions.return_value = {"actions": [], "next_cursor": "c9"}
        assert out_json(run(["investigate", "actions", "list"]))["next_cursor"] == "c9"
        assert sdk.list_actions.call_count == 1

    def test_the_inbox_rows_say_why_an_action_waits_and_carry_no_removed_mode(self, sdk):
        sdk.list_actions.return_value = {"actions": [
            {"run_id": "r1", "id": "a1", "class": "contain.network", "state": "awaiting_approval",
             "approval": {"form": "when", "when": "x", "value": "unknown"}, "approval_reason": "approval_condition",
             "run": {"template": "t"}},
        ], "next_cursor": ""}
        result = run(["--output", "csv", "investigate", "actions", "list"])
        assert result.exit_code == 0
        header = result.output.splitlines()[0].split(",")
        assert "mode" not in header and {"approval", "approval_reason"} <= set(header)
        assert "approval_condition" in result.output and "when" in result.output

    def test_approve_and_deny(self, sdk):
        sdk.decide_action.return_value = {"state": "executing"}
        run(["investigate", "actions", "approve", "r1", "a1"])
        sdk.decide_action.assert_called_with("r1", "a1", "approve")
        run(["investigate", "actions", "deny", "r1", "a1", "--note", "known admin"])
        sdk.decide_action.assert_called_with("r1", "a1", "deny", note="known admin")

    def test_settings_get_shows_what_the_engine_enforces(self, sdk):
        sdk.get_settings.return_value = {"paused": True, "set_by": "a@example.com", "set_at": "2026-11-25T18:00:00Z"}
        result = run(["investigate", "settings", "get"])
        assert result.exit_code == 0
        assert out_json(result) == {"paused": True, "set_by": "a@example.com", "set_at": "2026-11-25T18:00:00Z"}
        sdk.get_settings.assert_called_once_with()

    def test_pause_and_resume_write_the_settings_record(self, sdk):
        sdk.pause_actions.return_value = {"paused": True, "changed": True}
        result = run(["investigate", "settings", "pause"])
        assert result.exit_code == 0 and out_json(result) == {"paused": True, "changed": True}
        sdk.resume_actions.return_value = {"paused": False, "changed": True}
        result = run(["investigate", "settings", "resume"])
        assert result.exit_code == 0 and out_json(result)["paused"] is False
        sdk.pause_actions.assert_called_once_with()
        sdk.resume_actions.assert_called_once_with()

    def test_the_policy_group_and_its_commands_are_gone(self):
        runner = CliRunner()
        assert "policy" not in runner.invoke(cli, ["investigate", "--help"]).output.split()
        for args in (["policy", "get"], ["policy", "ai"], ["policy", "ai-set", "t", "off", "--confirm"],
                     ["policy", "status"], ["policy", "pause"], ["policy", "resume"]):
            assert runner.invoke(cli, ["investigate", *args]).exit_code == 2, args

    def test_the_help_texts_name_no_removed_concept(self):
        runner = CliRunner()
        for args in (["runs", "start"], ["runs", "steps"], ["settings", "get"], ["settings", "pause"], ["settings", "resume"]):
            out = " ".join(runner.invoke(cli, ["investigate", *args, "--help"]).output.split())
            for gone in ("threshold", "belief", "autonomy", "autonomy-manual-pause", "policy ai"):
                assert gone not in out, (args, gone)

    def test_the_agent_workflow_teaches_the_act_entry(self):
        out = " ".join(CliRunner().invoke(cli, ["investigate", "--ai-help"]).output.split())
        for needle in ("approval", "lease", "on_lease_end", "do: close.false_positive", "ai_may_decide", "investigate settings"):
            assert needle in out, needle
        for gone in ("investigate policy", "autonomy-manual-pause"):
            assert gone not in out, gone

    def test_a_refused_pause_is_reported_with_its_permission_hint(self, sdk):
        from limacharlie.sdk import investigation as m
        sdk.pause_actions.side_effect = m.InvestigationError(
            "lc_error_code:UNAUTHORIZED - nope", status_code=403, suggestion=m._POLICY_PERMISSION_HINT, exit_code=2)
        result = run(["investigate", "settings", "pause"])
        assert result.exit_code == 2
        doc = json.loads(result.stderr)
        assert doc["status"] == 403 and "investigation_policy.set" in doc["suggestion"]


class TestErrorReporting:
    def test_machine_formats_get_the_engine_error_as_a_document_on_stderr(self, sdk):
        err = issue_error()
        sdk.get_run.side_effect = err
        result = run(["investigate", "runs", "get", "r1"])
        assert result.exit_code == err.exit_code
        assert result.stdout == ""
        body = json.loads(result.stderr)
        assert body["error_code"] == "bad_request" and body["status"] == 400
        assert body["errors"] == err.issues and body["warnings"] == err.warnings

    def test_disabled_feature_error_names_the_cause(self, sdk):
        from limacharlie.sdk import investigation as m
        exc = m._wrap_error(error_from_status_code(404, {"error": "not found"}))
        sdk.list_runs.side_effect = exc
        result = run(["investigate", "runs", "list"])
        assert result.exit_code == 3
        assert "gated per deployment" in json.loads(result.stderr)["suggestion"]

    def test_a_refused_start_shows_its_reason_code_in_both_modes(self, sdk):
        from limacharlie.sdk import investigation as m
        body = {"error": "no active template applies", "error_code": "bad_request", "http_status": 400,
                "reason_code": "no_template_applies"}
        sdk.start_run.side_effect = m._wrap_error(error_from_status_code(400, body))
        args = ["investigate", "runs", "start", "--auto", "--detection-id", "d1"]
        doc = json.loads(run(args).stderr)
        assert doc["reason_code"] == "no_template_applies" and doc["error_code"] == "bad_request"
        assert doc["error"] == "no active template applies"
        table = run(args, fmt="table")
        assert table.exit_code != 0 and "reason_code: no_template_applies" in str(table.exception)

    def test_table_mode_raises_the_error_for_the_normal_text_rendering(self, sdk):
        sdk.get_run.side_effect = issue_error()
        result = run(["investigate", "runs", "get", "r1"], fmt="table")
        assert result.exit_code != 0
        assert isinstance(result.exception, InvestigationError)


class TestYaml12Input:
    """Wave and sample files keep YAML 1.2 scalars: values reach the engine as written."""

    def test_wave_file_words_and_dates_are_not_converted(self, sdk, tmp_path):
        f = tmp_path / "wave.yaml"
        f.write_text(
            "steps:\n  - {id: a, op: entity.get, args: {mode: off, flag: yes, since: 2026-11-10}}\n", encoding="utf-8")
        sdk.run_wave.return_value = {}
        result = run(["investigate", "wave", "--file", str(f)])
        assert result.exit_code == 0, result.stderr
        assert sdk.run_wave.call_args.args[0]["steps"][0]["args"] == {"mode": "off", "flag": "yes", "since": "2026-11-10"}

    def test_samples_file_words_and_dates_are_not_converted(self, sdk, tmp_path):
        f = tmp_path / "samples.yaml"
        f.write_text("- inputs: {since: 2026-11-10, quiet: off}\n  expected: false_positive\n", encoding="utf-8")
        sdk.test_plan.return_value = {"state": "done", "done": True}
        result = run(["investigate", "templates", "test", "my-plan", "--samples-file", str(f)])
        assert result.exit_code == 0, result.stderr
        assert sdk.test_plan.call_args.args[0] == [
            {"inputs": {"since": "2026-11-10", "quiet": "off"}, "expected": "false_positive"}]

    def test_an_unparseable_wave_file_is_a_coded_json_error(self, sdk, tmp_path):
        f = tmp_path / "wave.yaml"
        f.write_text("steps: [unclosed", encoding="utf-8")
        result = run(["investigate", "wave", "--file", str(f)])
        assert result.exit_code == 4
        doc = json.loads(result.stderr)
        assert doc["errors"][0]["code"] == "invalid_input" and doc["errors"][0]["path"] == "--file"
        sdk.run_wave.assert_not_called()

    def test_a_nan_in_a_wave_file_is_a_coded_json_error(self, sdk, tmp_path):
        f = tmp_path / "wave.yaml"
        f.write_text("inputs: {x: .nan}\nsteps: []\n", encoding="utf-8")
        result = run(["investigate", "wave", "--file", str(f)])
        assert result.exit_code == 4
        error = json.loads(result.stderr)["errors"][0]
        assert error["code"] == "invalid_input" and error["path"] == "--file" and "JSON cannot carry" in error["message"]
        sdk.run_wave.assert_not_called()

    @pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
    def test_a_nonfinite_number_in_inputs_json_is_a_coded_json_error(self, sdk, value):
        result = run(["investigate", "runs", "start", "--template", "my-plan", "--detection-id", "d1", "--inputs-json", '{"x": %s}' % value])
        assert result.exit_code == 4
        error = json.loads(result.stderr)["errors"][0]
        assert error["code"] == "invalid_input" and error["path"] == "--inputs-json"
        sdk.start_run.assert_not_called()

    def test_a_wrong_shape_is_a_coded_json_error(self, sdk, tmp_path):
        f = tmp_path / "samples.yaml"
        f.write_text("just: a mapping\n", encoding="utf-8")
        result = run(["investigate", "templates", "test", "my-plan", "--samples-file", str(f)])
        assert result.exit_code == 4
        assert json.loads(result.stderr)["errors"][0]["path"] == "--samples-file"

    def test_a_missing_file_is_a_coded_json_error(self, sdk, tmp_path):
        result = run(["investigate", "wave", "--file", str(tmp_path / "nope.yaml")])
        assert result.exit_code == 4
        assert json.loads(result.stderr)["errors"][0]["code"] == "invalid_input"

    def test_table_mode_still_fails_with_text(self, sdk, tmp_path):
        f = tmp_path / "wave.yaml"
        f.write_text("steps: [unclosed", encoding="utf-8")
        result = run(["investigate", "wave", "--file", str(f)], fmt="table")
        assert result.exit_code == 1 and isinstance(result.exception, InvestigationError)


class TestEveryFailureIsStructured:
    def test_a_coded_hive_refusal_renders_as_json_with_its_code_and_exit_code(self, sdk):
        sdk.promote_template.side_effect = error_from_status_code(
            400, {"error": "lc_error_code:API_KEY_NOT_ALLOWED - an API key cannot promote a template"})
        result = run(["investigate", "templates", "promote", "my-plan", "--confirm"])
        assert result.exit_code == 1
        doc = json.loads(result.stderr)
        assert doc["error_code"] == "API_KEY_NOT_ALLOWED" and "cannot promote" in doc["error"]
        assert doc["status"] == 400

    def test_other_sdk_errors_keep_their_own_exit_code(self, sdk):
        sdk.get_template.side_effect = AuthenticationError("bad key")
        result = run(["investigate", "templates", "get", "my-plan"])
        assert result.exit_code == AuthenticationError.exit_code
        assert json.loads(result.stderr)["error"] == "bad key"

    def test_table_mode_leaves_the_error_to_the_cli(self, sdk):
        sdk.promote_template.side_effect = error_from_status_code(400, {"error": "lc_error_code:X - y"})
        result = run(["investigate", "templates", "promote", "my-plan", "--confirm"], fmt="table")
        assert result.exception is not None and not result.stderr.startswith("{")


def test_safe_test_diagnostics_survive_compaction_and_tables():
    from limacharlie.commands.investigate import _compact_test, _test_rows
    sample = {"steps": [
        {"fact": "zero", "status": "ok", "complete": True, "counts": {"rows": 0}},
        {"fact": "positive", "status": "ok", "complete": False, "counts": {"rows": 2}},
        {"fact": "judge", "status": "ok", "complete": True,
         "judgement": {"label": "no", "confidence": 0.8, "model": "fixture"}},
    ], "verdict": {"outcome": "couldnt_tell", "label": "inconclusive", "decided": False,
                   "missing": [{"step": "zero", "reason": "index_lag", "needed_by": ["rule-1"], "ask": "Is it?"}]},
       "agreement": {"rule": "none", "ai": "none"},
       "cost": {"llm_usd": 0, "llm_unpriced": True}}
    compact = _compact_test({"results": [sample]}, False)["results"][0]
    assert len(compact["step_diagnostics"]) == 3
    assert compact["step_diagnostics"][0]["counts"]["rows"] == 0
    assert compact["step_diagnostics"][1]["complete"] is False
    assert compact["step_diagnostics"][2]["judgement"]["label"] == "no"
    assert json.loads(_test_rows({"results": [sample]})[0]["step_diagnostics"]) == compact["step_diagnostics"]
    assert "steps" not in compact
    assert len(sample["steps"]) == 3
    row = _test_rows({"results": [sample]})[0]
    assert row["ai_cost"] == "0 (unpriced)"
    assert row["outcome"] == "couldnt_tell" and row["decided_by"] is None and row["missing"] == 1
    assert (row["rule_agreement"], row["ai_agreement"]) == ("none", "none")
    for gone in ("p", "prior", "evidence", "decided"):
        assert gone not in row
    assert '"label":"no"' in row["step_diagnostics"]


def test_test_cost_and_summary_output(capsys, monkeypatch):
    from limacharlie.commands import investigate as mod
    monkeypatch.setattr(mod, "_fmt", lambda ctx: "table")
    monkeypatch.setattr(mod, "command_output", lambda *args: None)
    mod._print_test(None, {"summary": {"samples": 2, "rule_share": 0.5, "cost": {"llm_usd": 0.25, "llm_unpriced": True}}}, False)
    output = capsys.readouterr().out
    assert "samples=2, rule_share=0.5" in output
    assert "AI cost: 0.25 (unpriced)" in output
    mod._print_test(None, {"summary": {"cost_per_sample": {"steps": 6.5, "llm_usd": 0.002, "wall_ms": 2400}}}, False)
    assert "per sample: steps=6.5, llm_usd=0.002, wall_ms=2400" in capsys.readouterr().out
    mod._print_test(None, {"summary": {"rules": ["not", "a", "mapping"], "cost_per_sample": "bad"}}, False)
    assert "rule " not in capsys.readouterr().out
    mod._print_test(None, {"summary": {"cost": {}}}, False)
    assert "AI cost: unknown" in capsys.readouterr().out
    for cost in ([], "invalid", 1, None):
        assert mod._test_rows({"results": [{"cost": cost}]})[0]["ai_cost"] is None
        mod._print_test(None, {"summary": {"cost": cost}}, False)
    assert mod._test_rows({"results": [{"cost": {"llm_usd": 0}}]})[0]["ai_cost"] == 0
    assert mod._test_rows({"results": [{"cost": {"llm_unpriced": True}}]})[0]["ai_cost"] == "0 (unpriced)"
    assert list(mod._test_rows({"results": [{}]})[0])[:10] == [
        "index", "state", "outcome", "decided_by", "expected", "rule_agreement", "ai_agreement", "ai_recommends", "missing", "unknowns"]


def test_run_explicit_trust_additions(sdk):
    sdk.start_run.return_value = {"run": {"run_id": "r1"}}
    result = run(["investigate", "runs", "start", "--template", "mail", "--detection-id", "d",
                  "--trust-lookup", "partners", "--trust-lookup", "corporate",
                  "--trust-value", "partner.example.test", "--trust-value", "https://portal.example.test/a"])
    assert result.exit_code == 0, result.stderr
    assert sdk.start_run.call_args.args[0]["trust"] == {"lookups": ["partners", "corporate"],
        "values": ["partner.example.test", "https://portal.example.test/a"]}


def test_run_without_trust_omits_the_optional_field(sdk):
    sdk.start_run.return_value = {"run": {"run_id": "r1"}}
    result = run(["investigate", "runs", "start", "--template", "mail", "--detection-id", "d"])
    assert result.exit_code == 0, result.stderr
    assert "trust" not in sdk.start_run.call_args.args[0]

class TestOrgPacks:
    def test_pack_save_exact_file_and_etag(self, sdk, tmp_path):
        source = '# preserve\nname: fictional_pack\nversion: 1\n'
        path = tmp_path / 'pack.yaml'
        path.write_text(source, encoding="utf-8")
        sdk.save_pack.return_value = {'saved': True}
        assert run(['investigate', 'pack', 'save', 'fictional_pack', '--file', str(path), '--etag', 'r1']).exit_code == 0
        sdk.save_pack.assert_called_once_with('fictional_pack', source, etag='r1')

    def test_pack_delete_requires_confirmation(self, sdk):
        assert run(['investigate', 'pack', 'delete', 'fictional_pack']).exit_code != 0
        sdk.delete_pack.assert_not_called()
        sdk.delete_pack.return_value = {'deleted': True}
        assert run(['investigate', 'pack', 'delete', 'fictional_pack', '--confirm']).exit_code == 0
        sdk.delete_pack.assert_called_once_with('fictional_pack')

    def test_pack_get_and_create(self, sdk, tmp_path):
        sdk.get_pack.return_value = {"name": "fictional_pack", "yaml": "# exact\n", "etag": "r1"}
        assert out_json(run(["investigate", "pack", "get", "fictional_pack"]))["yaml"] == "# exact\n"
        sdk.get_pack.assert_called_once_with("fictional_pack")
        path = tmp_path / "pack.yaml"
        path.write_text("name: fictional_pack\nversion: 1\n", encoding="utf-8")
        sdk.save_pack.return_value = {"saved": True}
        assert run(["investigate", "pack", "save", "fictional_pack", "--file", str(path)]).exit_code == 0
        sdk.save_pack.assert_called_once_with("fictional_pack", path.read_text(encoding="utf-8"), etag=None)

    def test_brief_pack_preserves_provenance(self, sdk):
        metadata = {"version": 1, "digest": "a" * 64, "source": "org", "trust": {"lookups": ["fictional"]},
                    "trust_provenance": [{"kind": "pack", "name": "fictional_pack"}]}
        sdk.list_packs.return_value = {"packs": [{"name": "fictional_pack", **metadata}]}
        row = out_json(run(["investigate", "packs", "--brief"]))["packs"][0]
        assert {key: row[key] for key in metadata} == metadata


def test_validation_and_test_json_preserve_resolved_packs(sdk, tmp_path):
    from limacharlie.commands.investigate import _compact_test
    pins = [
        {'scope': 'root', 'name': 'fictional_context', 'version': 1, 'digest': 'a' * 64},
        {'scope': 'root/assessment', 'name': 'fictional_context', 'version': 2, 'digest': 'b' * 64},
    ]
    report = {'valid': True, 'resolved_packs': pins, 'ai_rules': ['ai_says_benign'],
              'trust_provenance': [{'kind': 'pack', 'name': 'fictional_context'}]}
    path = tmp_path / 'plan.yaml'
    path.write_text('gather:\n  context: {use: fictional_context, pack_version: 1}\n', encoding="utf-8")
    sdk.validate_plan.return_value = report
    assert out_json(run(['investigate', 'templates', 'validate', '--file', str(path)])) == report
    initial = {'state': 'running', 'validation': report, 'resolved_packs': pins,
               'results': [{**report, 'steps': [{'fact': 'context', 'status': 'ok'}]}]}
    compact = _compact_test(initial, False)
    assert compact['validation'] == report
    assert compact['resolved_packs'] == pins
    for key in ('resolved_packs', 'ai_rules', 'trust_provenance'):
        assert compact['results'][0][key] == report[key]
    assert 'steps' in initial['results'][0]  # compaction does not mutate its input


@pytest.mark.parametrize("seconds,expected", [(0, None), (12, 12.0)])
def test_start_follow_timeout_is_configurable(sdk, seconds, expected):
    sdk.start_run.return_value = {"run": {"run_id": "r1"}}

    def events(*args, **kwargs):
        kwargs["state"]["done"] = True
        return iter(())

    sdk.iter_run_events.side_effect = events
    result = run(["investigate", "runs", "start", "--template", "p", "--detection-id", "d",
                  "--follow", "--timeout", str(seconds)])
    assert result.exit_code == 0, result.stderr
    assert sdk.iter_run_events.call_args.kwargs["timeout"] == expected


@pytest.mark.parametrize("command", ["start", "events"])
def test_stream_error_reports_resume_after_last_received_page(sdk, command):
    sdk.start_run.return_value = {"run": {"run_id": "r1"}}

    def events(*args, **kwargs):
        kwargs["state"]["next"] = 99
        yield {"seq": 7, "type": "step", "data": {}}
        raise InvestigationError("stream unavailable", status_code=503)

    sdk.iter_run_events.side_effect = events
    args = (["start", "--template", "p", "--detection-id", "d"] if command == "start"
            else ["events", "r1"])
    result = run(["investigate", "runs", *args, "--follow"])
    assert result.exit_code == 1
    assert "--after 7" in result.stderr
    assert "stream unavailable" in result.stderr
    assert json.loads(result.stdout.splitlines()[-1])["seq"] == 7


def test_start_follow_rejects_negative_timeout_before_start(sdk):
    result = run(["investigate", "runs", "start", "--template", "p", "--detection-id", "d", "--follow", "--timeout", "-1"])
    assert result.exit_code == 2
    sdk.start_run.assert_not_called()


@pytest.mark.parametrize("flag,value,expected", [
    ("--trust-lookup", "partners", {"lookups": ["partners"]}),
    ("--trust-value", "partner.example.test", {"values": ["partner.example.test"]}),
])
def test_run_trust_omits_unused_keys(sdk, flag, value, expected):
    sdk.start_run.return_value = {"run": {"run_id": "r1"}}
    result = run(["investigate", "runs", "start", "--template", "mail", "--detection-id", "d", flag, value])
    assert result.exit_code == 0, result.stderr
    assert sdk.start_run.call_args.args[0]["trust"] == expected


def test_start_ai_help_explains_run_only_additive_trust(sdk):
    result = run(["investigate", "runs", "start", "--ai-help"])
    assert result.exit_code == 0
    assert "--trust-lookup" in result.stdout and "--trust-value" in result.stdout
    assert "template trust" in result.stdout and "this run only" in result.stdout
    assert "identity starting the run" in result.stdout
    sdk.start_run.assert_not_called()


QUEUE = {
    "queued": 1240, "claimed": 2, "running": 25, "max_parallel_runs": 25,
    "by_rule": [{"rule": "suspicious-powershell", "queued": 1200}, {"rule": "other", "queued": 40}],
    "by_template": [{"template": "suspicious-process", "queued": 1200}],
}


def not_available():
    return InvestigationError(
        "The run queue is not available on this deployment yet.", status_code=501,
        response_body={"error": "x", "error_code": "not_implemented"}, exit_code=1,
    )


class TestQueue:
    def test_help_lists_the_queue(self):
        runner = CliRunner()
        assert "queue" in runner.invoke(cli, ["investigate", "--help"]).output
        assert "flush" in runner.invoke(cli, ["investigate", "queue", "--help"]).output

    def test_queue_shows_the_engine_answer(self, sdk):
        sdk.get_queue.return_value = QUEUE
        result = run(["investigate", "queue"])
        assert result.exit_code == 0, result.stderr
        assert out_json(result) == QUEUE
        sdk.flush_queue.assert_not_called()

    def test_queue_shows_as_a_table(self, sdk):
        sdk.get_queue.return_value = QUEUE
        result = run(["investigate", "queue"], fmt="table")
        assert result.exit_code == 0, result.stderr
        assert "1240" in result.stdout

    def test_queue_501_is_said_plainly(self, sdk):
        sdk.get_queue.side_effect = not_available()
        result = run(["investigate", "queue"])
        assert result.exit_code == 1
        assert "not available on this deployment yet" in result.stderr
        assert json.loads(result.stderr)["status"] == 501

    def test_queue_501_in_table_mode_is_text(self, sdk):
        sdk.get_queue.side_effect = not_available()
        result = run(["investigate", "queue"], fmt="table")
        assert result.exit_code != 0
        assert "not available on this deployment yet" in str(result.exception)

    @pytest.mark.parametrize(
        "args, scope",
        [
            (["--rule", "suspicious-powershell"], {"rule": "suspicious-powershell", "template": None, "all": False}),
            (["--template", "suspicious-process"], {"rule": None, "template": "suspicious-process", "all": False}),
            (["--all"], {"rule": None, "template": None, "all": True}),
        ],
    )
    def test_flush_asks_then_flushes_one_scope(self, sdk, args, scope):
        sdk.get_queue.return_value = QUEUE
        sdk.flush_queue.return_value = {"flush_id": "f1", "flushed": 1200, "done": True}
        result = run(["investigate", "queue", "flush", *args, "--note", "rule fixed"], input="y\n")
        assert result.exit_code == 0, result.stderr
        sdk.flush_queue.assert_called_once_with(note="rule fixed", **scope)
        assert '"flushed": 1200' in result.stdout  # (the runner echoes the typed answer into stdout)
        assert "cannot be undone" in result.stderr

    @pytest.mark.parametrize(
        "args, count",
        [(["--rule", "suspicious-powershell"], "1200"), (["--template", "suspicious-process"], "1200"),
         (["--rule", "other"], "40"), (["--all"], "1240"), (["--rule", "unknown"], "0")],
    )
    def test_the_confirmation_says_how_many_starts_are_cancelled(self, sdk, args, count):
        sdk.get_queue.return_value = QUEUE
        result = run(["investigate", "queue", "flush", *args], input="n\n")
        assert f"cancels {count} queued start(s)" in result.stderr
        assert "running investigations are not touched" in result.stderr
        assert "cannot be undone" in result.stderr

    def test_declining_flushes_nothing(self, sdk):
        sdk.get_queue.return_value = QUEUE
        result = run(["investigate", "queue", "flush", "--all"], input="n\n")
        assert result.exit_code != 0
        sdk.flush_queue.assert_not_called()

    def test_no_answer_flushes_nothing(self, sdk):
        sdk.get_queue.return_value = QUEUE
        result = run(["investigate", "queue", "flush", "--all"], input="")
        assert result.exit_code != 0
        sdk.flush_queue.assert_not_called()

    def test_yes_skips_the_question_and_the_queue_read(self, sdk):
        sdk.flush_queue.return_value = {"flush_id": "f1", "flushed": 7, "done": False}
        result = run(["investigate", "queue", "flush", "--template", "t", "--yes"])
        assert result.exit_code == 0, result.stderr
        sdk.get_queue.assert_not_called()
        sdk.flush_queue.assert_called_once_with(rule=None, template="t", all=False, note=None)
        assert "continues" in result.stderr or "finishes in the engine" in result.stderr

    @pytest.mark.parametrize("args", [[], ["--rule", "r", "--all"], ["--rule", "r", "--template", "t"], ["--note", "x"]])
    def test_flush_needs_exactly_one_scope(self, sdk, args):
        result = run(["investigate", "queue", "flush", "--yes", *args])
        assert result.exit_code == 2
        sdk.flush_queue.assert_not_called()
        sdk.get_queue.assert_not_called()

    def test_flush_501_is_said_plainly_and_nothing_is_asked_twice(self, sdk):
        sdk.flush_queue.side_effect = not_available()
        result = run(["investigate", "queue", "flush", "--all", "--yes"])
        assert result.exit_code == 1
        assert "not available on this deployment yet" in result.stderr

    def test_flush_on_a_deployment_without_the_queue_fails_before_asking(self, sdk):
        sdk.get_queue.side_effect = not_available()
        result = run(["investigate", "queue", "flush", "--all"], input="y\n")
        assert result.exit_code == 1
        assert "not available on this deployment yet" in result.stderr
        sdk.flush_queue.assert_not_called()

    def test_explain_texts_exist(self):
        out = CliRunner().invoke(cli, ["investigate", "queue", "flush", "--ai-help"]).output
        assert "cannot be undone" in out
