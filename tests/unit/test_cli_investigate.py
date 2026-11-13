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
        for name in ("kit", "operators", "packs", "templates", "runs", "wave", "actions", "policy", "autopilot"):
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
            "name": "host_context", "brief": "who",
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
        f.write_text("description: x\n")
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
        f.write_text("description: x\n")
        sdk.save_template.return_value = {"saved": True, "status": "draft"}
        assert run(["investigate", "templates", "save", "my-plan", "--file", str(f), "--comment", "10 samples"]).exit_code == 0
        sdk.save_template.assert_called_with(
            "my-plan", "description: x\n", status="draft", overwrite=False, comment="10 samples", tags=None)
        run(["investigate", "templates", "save", "my-plan", "--file", str(f), "--status", "active", "--overwrite", "--tag", "t"])
        sdk.save_template.assert_called_with(
            "my-plan", "description: x\n", status="active", overwrite=True, comment=None, tags=["t"])

    def test_refused_save_exits_4_and_says_why(self, sdk, tmp_path):
        f = tmp_path / "plan.yaml"
        f.write_text("description: x\n")
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
        "test_id": "t1", "state": "done", "done": True, "samples_done": 2, "samples_total": 2,
        "results": [
            {"index": 0, "sample": {"detection_id": "d1"}, "state": "ok", "verdict": {"label": "false_positive", "p": 0.04},
             "expected": {"label": "false_positive"}, "agreement": "agree", "unknowns": [],
             "steps": [{"fact": "a", "status": "ok"}, {"fact": "b", "status": "unknown", "reason": "index_lag"}]},
            {"index": 1, "sample": {"case_id": "9"}, "state": "ok", "verdict": {"label": "true_positive", "p": 0.9},
             "expected": {"label": "false_positive"}, "agreement": "disagree", "unknowns": [{"fact": "b"}]},
        ],
        "summary": {"samples": 2, "agree": 1, "disagree": 1, "agreement_rate": 0.5, "unknown_reasons": {"index_lag": 1}},
    }

    def test_samples_are_built_from_every_flag(self, sdk, tmp_path):
        sdk.test_plan.return_value = dict(self.DONE)
        sf = tmp_path / "s.yaml"
        sf.write_text("- {detection_id: from-file}\n")
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
        f.write_text("description: draft\n")
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

    def test_table_output_shows_per_sample_verdicts_and_the_agreement_summary(self, sdk):
        sdk.test_plan.return_value = dict(self.DONE)
        result = run(["investigate", "templates", "test", "p", "--detection-id", "d"], fmt="table")
        assert result.exit_code == 0, result.stderr
        assert "agree" in result.stdout and "disagree" in result.stdout
        assert "agreement_rate=0.5" in result.stdout
        assert "unknown reasons: {'index_lag': 1}" in result.stdout


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
        f.write_text("description: x\n")
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
        assert kwargs["since"] == "2026-11-01T00:00:00Z" and kwargs["verdict"] is None

    def test_list_filters_pass_the_engines_values_through(self, sdk):
        sdk.list_runs.return_value = {"runs": [], "next_cursor": ""}
        run(["investigate", "runs", "list", "--verdict", "undecided", "--trigger", "detection", "--started-by", "a@x.io"])
        kwargs = sdk.list_runs.call_args.kwargs
        assert (kwargs["verdict"], kwargs["trigger"], kwargs["started_by"]) == ("undecided", "detection", "a@x.io")

    def test_list_help_names_the_engines_trigger_kinds(self):
        out = " ".join(CliRunner().invoke(cli, ["investigate", "runs", "list", "--help"]).output.split())
        assert "detection, message, entity, case, question" in out and "undecided" in out
        assert "dr-rule" not in out

    def test_strict_help_says_it_refuses_loosening_overrides(self):
        out = " ".join(CliRunner().invoke(cli, ["investigate", "templates", "test", "--help"]).output.split())
        assert "loosen" in out and "unknown as a failure" not in out

    def test_list_table_rows_and_cursor_on_stderr(self, sdk):
        sdk.list_runs.return_value = {"runs": [{
            "run_id": "r1", "state": "completed", "template": "p", "verdict": {"label": "false_positive", "p": 0.02},
            "started_by": {"identity": "user:u", "actor": "a@x.io"}, "created": "2026-11-10T00:00:00Z"}], "next_cursor": "c2"}
        result = run(["investigate", "runs", "list"], fmt="csv")
        assert "false_positive" in result.stdout and "a@x.io" in result.stdout and "p=" not in result.stdout
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
            "stop_when: ['host__resolve.found == false']\ndeadline_ms: 5000\ninputs: {a: '1'}\n")
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
        f.write_text('[{"id": "a", "op": "entity.get", "args": {}}]')
        sdk.run_wave.return_value = {}
        run(["investigate", "wave", "--file", str(f)])
        assert sdk.run_wave.call_args.args[0] == {"steps": [{"id": "a", "op": "entity.get", "args": {}}]}

    def test_a_refused_wave_prints_the_coded_errors_on_stdout_and_exits_4(self, sdk, tmp_path):
        f = tmp_path / "wave.json"
        f.write_text('{"steps": [{"id": "a", "op": "x"}]}')
        err = issue_error()
        sdk.run_wave.side_effect = err
        result = run(["investigate", "wave", "--file", str(f)])
        assert result.exit_code == 4
        body = out_json(result)
        assert body["valid"] is False and body["errors"] == err.issues and body["warnings"] == err.warnings

    def test_validate_only_with_an_invalid_report_exits_4(self, sdk, tmp_path):
        f = tmp_path / "wave.json"
        f.write_text('{"steps": [{"id": "a", "op": "x"}]}')
        sdk.run_wave.return_value = {"valid": False, "errors": [{"code": "unknown_operator"}], "warnings": []}
        assert run(["investigate", "wave", "--file", str(f), "--validate-only"]).exit_code == 4

    def test_a_wave_failure_without_issues_is_a_plain_error(self, sdk, tmp_path):
        f = tmp_path / "wave.json"
        f.write_text('{"steps": [{"id": "a", "op": "x"}]}')
        sdk.run_wave.side_effect = InvestigationError("timed out", status_code=504, exit_code=1)
        result = run(["investigate", "wave", "--file", str(f)])
        assert result.exit_code == 1
        assert json.loads(result.stderr)["error"] == "timed out"


class TestActionsAndPolicy:
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

    def test_approve_and_deny(self, sdk):
        sdk.decide_action.return_value = {"state": "executing"}
        run(["investigate", "actions", "approve", "r1", "a1"])
        sdk.decide_action.assert_called_with("r1", "a1", "approve")
        run(["investigate", "actions", "deny", "r1", "a1", "--note", "known admin"])
        sdk.decide_action.assert_called_with("r1", "a1", "deny", note="known admin")

    def test_policy_commands(self, sdk):
        sdk.get_effective_policy.return_value = {}
        run(["investigate", "policy", "get", "--category", "c", "--priority", "4", "--target-tag", "a", "--target-tag", "b", "--class", "tag",
             "--template", "t"])
        sdk.get_effective_policy.assert_called_with(
            category="c", priority=4, severity=None, target_tags=["a", "b"], action_class="tag", template="t")
        run(["investigate", "policy", "status"])
        sdk.get_autonomy.assert_called_once()
        run(["investigate", "policy", "pause"])
        sdk.set_autonomy.assert_called_with("pause")
        run(["investigate", "policy", "resume"])
        sdk.set_autonomy.assert_called_with("resume")


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
            "steps:\n  - {id: a, op: entity.get, args: {mode: off, flag: yes, since: 2026-11-10}}\n")
        sdk.run_wave.return_value = {}
        result = run(["investigate", "wave", "--file", str(f)])
        assert result.exit_code == 0, result.stderr
        assert sdk.run_wave.call_args.args[0]["steps"][0]["args"] == {"mode": "off", "flag": "yes", "since": "2026-11-10"}

    def test_samples_file_words_and_dates_are_not_converted(self, sdk, tmp_path):
        f = tmp_path / "samples.yaml"
        f.write_text("- inputs: {since: 2026-11-10, quiet: off}\n  expected: false_positive\n")
        sdk.test_plan.return_value = {"state": "done", "done": True}
        result = run(["investigate", "templates", "test", "my-plan", "--samples-file", str(f)])
        assert result.exit_code == 0, result.stderr
        assert sdk.test_plan.call_args.args[0] == [
            {"inputs": {"since": "2026-11-10", "quiet": "off"}, "expected": "false_positive"}]

    def test_an_unparseable_wave_file_is_a_coded_json_error(self, sdk, tmp_path):
        f = tmp_path / "wave.yaml"
        f.write_text("steps: [unclosed")
        result = run(["investigate", "wave", "--file", str(f)])
        assert result.exit_code == 4
        doc = json.loads(result.stderr)
        assert doc["errors"][0]["code"] == "invalid_input" and doc["errors"][0]["path"] == "--file"
        sdk.run_wave.assert_not_called()

    def test_a_nan_in_a_wave_file_is_a_coded_json_error(self, sdk, tmp_path):
        f = tmp_path / "wave.yaml"
        f.write_text("inputs: {x: .nan}\nsteps: []\n")
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
        f.write_text("just: a mapping\n")
        result = run(["investigate", "templates", "test", "my-plan", "--samples-file", str(f)])
        assert result.exit_code == 4
        assert json.loads(result.stderr)["errors"][0]["path"] == "--samples-file"

    def test_a_missing_file_is_a_coded_json_error(self, sdk, tmp_path):
        result = run(["investigate", "wave", "--file", str(tmp_path / "nope.yaml")])
        assert result.exit_code == 4
        assert json.loads(result.stderr)["errors"][0]["code"] == "invalid_input"

    def test_table_mode_still_fails_with_text(self, sdk, tmp_path):
        f = tmp_path / "wave.yaml"
        f.write_text("steps: [unclosed")
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
    ], "verdict": {"label": "inconclusive", "decided": True, "prior": 0.3, "p": 0.1,
                     "evidence": [{"rule": "rule-1", "weight": -2, "facts": ["zero"]}]},
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
    assert row["llm_cost"] == "0 (unpriced)"
    assert row["prior"] == 0.3
    assert '"weight":-2' in row["evidence"]
    assert '"label":"no"' in row["step_diagnostics"]


def test_test_cost_and_summary_output(capsys, monkeypatch):
    from limacharlie.commands import investigate as mod
    monkeypatch.setattr(mod, "_fmt", lambda ctx: "table")
    monkeypatch.setattr(mod, "command_output", lambda *args: None)
    mod._print_test(None, {"summary": {"inconclusive": 2, "cost": {"llm_usd": 0.25, "llm_unpriced": True}}}, False)
    output = capsys.readouterr().out
    assert "inconclusive=2" in output
    assert "LLM cost: 0.25 (unpriced)" in output
    mod._print_test(None, {"summary": {"cost": {}}}, False)
    assert "LLM cost: unknown" in capsys.readouterr().out
    for cost in ([], "invalid", 1, None):
        assert mod._test_rows({"results": [{"cost": cost}]})[0]["llm_cost"] is None
        mod._print_test(None, {"summary": {"cost": cost}}, False)
    assert mod._test_rows({"results": [{"cost": {"llm_usd": 0}}]})[0]["llm_cost"] == 0
    assert mod._test_rows({"results": [{"cost": {"llm_unpriced": True}}]})[0]["llm_cost"] == "0 (unpriced)"
    assert list(mod._test_rows({"results": [{}]})[0])[:9] == ["index", "sample", "state", "verdict", "p", "expected", "agreement", "unknowns", "wall_ms"]


class TestAutopilot:
    def test_status_keeps_spend_counters_and_automation_flag(self, sdk):
        status = {"config": {"sources": {}}, "day": {"charged_micro_usd": 1500000, "spent_micro_usd": 1000000, "reserved_micro_usd": 500000},
                  "month": {"charged_micro_usd": 2500000, "spent_micro_usd": 2000000, "reserved_micro_usd": 500000}, "budget_exhausted": False,
                  "counters": {"seen": 3, "skipped_budget": 1, "queued": 1, "active": 1}, "automation_available": False}
        sdk.get_autopilot.return_value = status
        result = run(["investigate", "autopilot", "status"])
        assert result.exit_code == 0, result.stderr
        assert out_json(result) == status

    def test_configure_from_settings_file_and_stdin(self, sdk, tmp_path):
        config = {"sources": {"mailsec": {"enabled": True, "mode": "shadow", "template": "mailsec-generic-triage"}},
                  "daily_cap_micro_usd": 10000000, "monthly_cap_micro_usd": 100000000, "max_concurrent": 5, "run_cap_micro_usd": 500000}
        sdk.set_autopilot.return_value = {"config": config, "automation_available": False}
        f = tmp_path / "autopilot.json"
        f.write_text(json.dumps(config))
        for args, stdin in [(["--settings", json.dumps(config)], None), (["--file", str(f)], None),
                            (["--file", "-"], json.dumps(config))]:
            result = run(["investigate", "autopilot", "configure", *args], input=stdin)
            assert result.exit_code == 0, result.stderr
            assert out_json(result)["config"] == config
            sdk.set_autopilot.assert_called_with(config)
        assert sdk.set_autopilot.call_count == 3

    @pytest.mark.parametrize("args", [[], ["--settings", "{}", "--file", "unused"],
                                      ["--settings", "[]"], ["--settings", "null"],
                                      ["--settings", "{broken"], ["--settings", '{"run_cap_micro_usd":NaN}']])
    def test_bad_settings_are_refused_before_sdk(self, sdk, args):
        result = run(["investigate", "autopilot", "configure", *args])
        assert result.exit_code == 4
        assert json.loads(result.stderr)["errors"][0]["code"] == "invalid_input"
        sdk.set_autopilot.assert_not_called()

    def test_alert_links_and_cursor_survive_output(self, sdk):
        alerts = [{"id": "a1", "source": "mailsec", "group_id": "g1", "run_id": "r1", "state": "investigated", "reason": "", "created": "2026-11-13T12:00:00Z"},
                  {"id": "a2", "source": "mailsec", "group_id": "g2", "run_id": "", "state": "skipped_budget", "reason": "daily budget"}]
        sdk.list_autopilot_alerts.return_value = {"alerts": alerts, "next_cursor": "next+cursor"}
        result = run(["investigate", "autopilot", "alerts", "--source", "mailsec", "--limit", "20", "--cursor", "previous"])
        assert result.exit_code == 0, result.stderr
        sdk.list_autopilot_alerts.assert_called_once_with(source="mailsec", state=None, group_id=None, run_id=None, from_=None, to=None, limit=20, cursor="previous")
        assert out_json(result) == {"alerts": alerts, "next_cursor": "next+cursor"}
        table = run(["investigate", "autopilot", "alerts"], fmt="table")
        assert table.exit_code == 0, table.stderr
        assert "g1" in table.stdout and "r1" in table.stdout and "skipped_budget" in table.stdout
        assert "next+cursor" in table.stderr

    def test_engine_refusal_keeps_structured_diagnostics(self, sdk):
        sdk.set_autopilot.side_effect = issue_error()
        result = run(["investigate", "autopilot", "configure", "--settings", "{}"])
        assert result.exit_code != 0
        assert json.loads(result.stderr)["errors"][0]["code"] == "unknown_field"


class TestScoreboard:
    route_id = "a" * 64

    def test_scoreboard_preserves_unpriced_and_incomplete_metadata(self, sdk):
        result = {"routes": [{"route_id": self.route_id, "state": "shadow", "cost_micro_usd": None}], "truncated": True}
        sdk.get_scoreboard.return_value = result
        response = run(["investigate", "scoreboard", "--product", "mailsec"])
        assert response.exit_code == 0, response.stderr
        assert out_json(response) == result
        sdk.get_scoreboard.assert_called_once_with(product="mailsec")

    def test_enabling_requires_explicit_confirm(self, sdk):
        response = run(["investigate", "routes", "enable", self.route_id, "--product", "mailsec"])
        assert response.exit_code != 0 and "--confirm" in response.stderr
        sdk.decide_route.assert_not_called()
        sdk.decide_route.return_value = {"route": {"state": "enabled"}}
        response = run(["investigate", "routes", "enable", self.route_id, "--product", "mailsec", "--confirm"])
        assert response.exit_code == 0, response.stderr
        sdk.decide_route.assert_called_once_with(self.route_id, "mailsec", "enable")

    def test_disable_and_configure(self, sdk):
        sdk.decide_route.return_value = {"route": {"state": "shadow"}}
        response = run(["investigate", "routes", "disable", self.route_id, "--product", "mailsec"])
        assert response.exit_code == 0, response.stderr
        sdk.decide_route.assert_called_with(self.route_id, "mailsec", "disable")
        response = run(["investigate", "routes", "configure", self.route_id, "--product", "mailsec", "--min-agreeing", "250", "--spot-check-ppm", "100000"])
        assert response.exit_code == 0, response.stderr
        sdk.decide_route.assert_called_with(self.route_id, "mailsec", "configure", min_agreeing=250, spot_check_ppm=100000)

    def test_configure_requires_setting_and_refuses_out_of_range_sample(self, sdk):
        for options in ([], ["--spot-check-ppm", "-1"], ["--spot-check-ppm", "1000001"], ["--min-agreeing", "0"]):
            response = run(["investigate", "routes", "configure", self.route_id, "--product", "mailsec", *options])
            assert response.exit_code != 0
        sdk.decide_route.assert_not_called()

    def test_run_label_sends_independent_assessment_and_revision(self, sdk):
        sdk.submit_run_label.return_value = {"outcome": {"assessment": "benign", "revision": 2}}
        response = run(["investigate", "runs", "label", "run-1", "--assessment", "benign", "--revision", "2"])
        assert response.exit_code == 0, response.stderr
        sdk.submit_run_label.assert_called_once_with("run-1", "benign", 2)
        assert out_json(response)["outcome"]["revision"] == 2

    @pytest.mark.parametrize("options", [["--assessment", "false_positive", "--revision", "1"],
                                         ["--assessment", "benign", "--revision", "0"],
                                         ["--assessment", "benign"]])
    def test_run_label_requires_valid_assessment_and_revision(self, sdk, options):
        assert run(["investigate", "runs", "label", "run-1", *options]).exit_code != 0
        sdk.submit_run_label.assert_not_called()


@pytest.mark.parametrize("options,answer", [([], None), (["--preference-only"], False), (["--was-engine-wrong"], True)])
def test_revert_does_not_infer_a_wrong_engine_label(sdk, options, answer):
    sdk.decide_action.return_value = {"state": "reverted"}
    result = run(["investigate", "actions", "revert", "r1", "a1", *options])
    assert result.exit_code == 0, result.stderr
    sdk.decide_action.assert_called_once_with("r1", "a1", "revert", note=None, was_engine_wrong=answer)


def test_autopilot_status_filters_and_full_overview_survive(sdk):
    response = {"sources_available": ["mailsec"], "sources": {"mailsec": {"seen": 40}},
                "alerts_by_day": [{"day": "2026-11-01", "count": 40}], "alerts_per_day": 40,
                "overview": {"total": 40}, "period": {"from": "2026-11-01T00:00:00Z", "to": "2026-11-08T00:00:00Z"}}
    sdk.get_autopilot.return_value = response
    result = run(["investigate", "autopilot", "status", "--source", "mailsec", "--period", "7d"])
    assert result.exit_code == 0, result.stderr
    assert out_json(result) == response
    sdk.get_autopilot.assert_called_once_with(source="mailsec", period="7d", from_=None, to=None)


def test_autopilot_status_requires_both_explicit_bounds(sdk):
    result = run(["investigate", "autopilot", "status", "--from", "2026-11-01T00:00:00Z"])
    assert result.exit_code == 4
    sdk.get_autopilot.assert_not_called()


def test_autopilot_alert_page_preserves_total_truncated_and_filters(sdk):
    page = {"alerts": [{"id": "a1", "run_id": "r1"}], "total": 250, "next_cursor": "signed+bound", "truncated": True}
    sdk.list_autopilot_alerts.return_value = page
    result = run(["investigate", "autopilot", "alerts", "--source", "mailsec", "--state", "completed",
                  "--group-id", "g1", "--run-id", "r1", "--from", "2026-11-01T00:00:00Z",
                  "--to", "2026-11-08T00:00:00Z", "--limit", "50", "--cursor", "signed+bound"])
    assert result.exit_code == 0, result.stderr
    assert out_json(result) == page
    sdk.list_autopilot_alerts.assert_called_once_with(source="mailsec", state="completed", group_id="g1", run_id="r1",
                                                      from_="2026-11-01T00:00:00Z", to="2026-11-08T00:00:00Z", limit=50, cursor="signed+bound")
    table = run(["investigate", "autopilot", "alerts"], fmt="table")
    assert "total: 250" in table.stderr and "truncated: true" in table.stderr


@pytest.mark.parametrize("token", ["1.0", "1e6", "1E6", '"1000000"', "null", "true"])
def test_autopilot_settings_refuse_noninteger_micro_usd_before_write(token):
    # Keep the real SDK validator under the CLI so syntax normalization cannot
    # turn decimal/exponent user settings into accepted integer wire values.
    with patch("limacharlie.commands.investigate.Client") as client, \
            patch("limacharlie.commands.investigate.Organization") as org:
        org.return_value.client = client.return_value
        org.return_value.oid = "fictional-org"
        result = run(["investigate", "autopilot", "configure", "--settings", '{"daily_cap_micro_usd":' + token + '}'])
        assert result.exit_code != 0
        client.return_value.request.assert_not_called()


def test_route_configure_all_integer_ppm_options(sdk):
    sdk.decide_route.return_value = {"route": {}}
    result = run(["investigate", "routes", "configure", "a" * 64, "--product", "mailsec",
                  "--spot-check-ppm", "50000", "--error-target-ppm", "15000", "--blind-share-ppm", "100000"])
    assert result.exit_code == 0, result.stderr
    sdk.decide_route.assert_called_once_with("a" * 64, "mailsec", "configure", spot_check_ppm=50000, error_target_ppm=15000, blind_share_ppm=100000)


def test_human_engine_formatting_is_exact_and_never_mutates_wire_data():
    from copy import deepcopy
    from limacharlie.commands.investigate import _human_engine_values
    raw = {"daily_cap_micro_usd": 10000000, "spent_micro_usd": 1, "unknown_micro_usd": None,
           "nested": [{"spot_check_ppm": 50000, "error_target_ppm": 15000, "blind_share_ppm": 1}]}
    before = deepcopy(raw)
    human = _human_engine_values(raw)
    assert human == {"daily_cap_micro_usd": "$10.00", "spent_micro_usd": "$0.000001", "unknown_micro_usd": "unknown",
                     "nested": [{"spot_check_ppm": "5%", "error_target_ppm": "1.5%", "blind_share_ppm": "0.0001%"}]}
    assert raw == before


@pytest.mark.parametrize("fmt", ["table", "csv"])
def test_autopilot_human_status_money_and_ppm(sdk, fmt):
    sdk.get_autopilot.return_value = {"daily_cap_micro_usd": 10000000, "spent_micro_usd": 1,
                                     "unknown_micro_usd": None, "error_target_ppm": 15000}
    result = run(["investigate", "autopilot", "status"], fmt=fmt)
    assert result.exit_code == 0, result.stderr
    assert "$10.00" in result.stdout and "$0.000001" in result.stdout
    assert "unknown" in result.stdout and "1.5%" in result.stdout


def test_human_alert_values_and_raw_structured_values(sdk):
    page = {"alerts": [{"id": "a1", "spent_micro_usd": 50000, "spot_check_ppm": 50000}],
            "total": 1, "next_cursor": "", "truncated": False}
    sdk.list_autopilot_alerts.return_value = page
    human = run(["investigate", "autopilot", "alerts"], fmt="table")
    assert human.exit_code == 0, human.stderr
    assert "$0.05" in human.stdout and "5%" in human.stdout
    structured = run(["investigate", "autopilot", "alerts"], fmt="json")
    assert out_json(structured) == page
    sdk.get_autopilot.return_value = {"spent_micro_usd": 1, "unknown_micro_usd": None, "spot_check_ppm": 1}
    for fmt in ("json", "jsonl"):
        result = run(["investigate", "autopilot", "status"], fmt=fmt)
        assert json.loads(result.stdout) == sdk.get_autopilot.return_value


def test_error_target_ppm_cli_uses_canonical_maximum(sdk):
    result = run(["investigate", "routes", "configure", "a" * 64, "--product", "mailsec", "--error-target-ppm", "100001"])
    assert result.exit_code != 0
    sdk.decide_route.assert_not_called()
