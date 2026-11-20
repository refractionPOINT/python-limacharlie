"""A replay that did not cover its whole window must say so on stderr.

Replay answers HTTP 200 when it stops early (server deadline, unreadable or
oversized data), with the matches found so far. An agent that read such a run's
"0 matches" as "the rule is clean" deployed a rule that fired thousands of times.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from limacharlie.cli import cli
from limacharlie.commands._replay_completeness import partial_reasons

_COMPLETE = {
    "stats": {"n_proc": 1200, "n_eval": 3400, "n_matched": 0, "stop_reason": ""},
    "results": [],
    "did_match": False,
}

# The shape replay returns when its request deadline fires: HTTP 200, the
# merged results so far, results_partial, stop_reason and an error.
_DEADLINE = {
    "stats": {
        "n_proc": 500,
        "n_matched": 0,
        "results_partial": True,
        "stop_reason": "request_deadline",
    },
    "results": [],
    "did_match": False,
    "error": "replay request deadline (9m0s) reached",
}


class TestPartialReasons:
    def test_complete_run_has_no_reason(self):
        assert partial_reasons(_COMPLETE) == []
        assert partial_reasons({**_COMPLETE, "stats": {**_COMPLETE["stats"], "stop_reason": "none"}}) == []

    def test_deadline_run_names_every_signal(self):
        reasons = partial_reasons(_DEADLINE)
        assert reasons == [
            "stats.results_partial is true",
            "stopped early (stats.stop_reason: request_deadline)",
            "error: replay request deadline (9m0s) reached",
        ]

    def test_skipped_events_alone_is_partial(self):
        data = {"stats": {"skipped_events": [{"id": "a", "bytes": 700000, "reason": "event_too_large"}]}}
        assert partial_reasons(data) == ["1 event(s) skipped (stats.skipped_events)"]

    def test_caller_limit_is_partial(self):
        # A run stopped at limit_event did not cover the window either.
        assert partial_reasons({"stats": {"stop_reason": "limit_event"}}) == [
            "stopped early (stats.stop_reason: limit_event)",
        ]

    @pytest.mark.parametrize("data", [None, [], "x", {"stats": None}, {"stats": "x"}])
    def test_unexpected_shapes_do_not_raise(self, data):
        assert partial_reasons(data) == []


@pytest.fixture
def replay_sdk():
    with patch("limacharlie.commands.dr.Client"), \
         patch("limacharlie.commands.dr.Organization"), \
         patch("limacharlie.commands.dr.ReplaySDK") as dr_sdk, \
         patch("limacharlie.commands.replay_cmd.Client"), \
         patch("limacharlie.commands.replay_cmd.Organization"), \
         patch("limacharlie.commands.replay_cmd.ReplaySDK") as run_sdk:
        dr_inst, run_inst = MagicMock(), MagicMock()
        dr_sdk.return_value = dr_inst
        run_sdk.return_value = run_inst
        yield dr_inst, run_inst


def _dr_replay(*extra):
    return ["--output", "json", "dr", "replay", "--name", "r", "--start", "1700000000", "--end", "1700003600", *extra]


def _replay_run(tmp_path, *extra):
    detect = tmp_path / "d.yaml"
    detect.write_text("event: NEW_PROCESS\nop: exists\npath: event\n")
    respond = tmp_path / "r.yaml"
    respond.write_text("- action: report\n  name: r\n")
    return ["--output", "json", "replay", "run", "--detect-file", str(detect), "--respond-file", str(respond),
            "--start", "1700000000", "--end", "1700003600", *extra]


class TestReplayCommandsWarn:
    def test_dr_replay_warns_on_partial(self, replay_sdk):
        dr_inst, _ = replay_sdk
        dr_inst.run.return_value = _DEADLINE
        result = CliRunner(mix_stderr=False).invoke(cli, _dr_replay())
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)["stats"]["results_partial"] is True
        assert "replay results are PARTIAL" in result.stderr
        assert "request_deadline" in result.stderr

    def test_dr_replay_quiet_on_complete(self, replay_sdk):
        dr_inst, _ = replay_sdk
        dr_inst.run.return_value = _COMPLETE
        result = CliRunner(mix_stderr=False).invoke(cli, _dr_replay())
        assert result.exit_code == 0, result.output
        assert result.stderr == ""

    def test_dr_replay_warns_even_with_quiet(self, replay_sdk):
        dr_inst, _ = replay_sdk
        dr_inst.run.return_value = _DEADLINE
        result = CliRunner(mix_stderr=False).invoke(cli, ["--quiet", *_dr_replay()])
        assert result.exit_code == 0, result.output
        assert "replay results are PARTIAL" in result.stderr

    def test_replay_run_warns_and_passes_scope(self, replay_sdk, tmp_path):
        _, run_inst = replay_sdk
        run_inst.run.return_value = _DEADLINE
        result = CliRunner(mix_stderr=False).invoke(
            cli, _replay_run(tmp_path, "--selector", '"prod" in tags', "--sid", "s-1"))
        assert result.exit_code == 0, result.output
        kwargs = run_inst.run.call_args.kwargs
        assert kwargs["selector"] == '"prod" in tags'
        assert kwargs["sid"] == "s-1"
        assert kwargs["detect"] == {"event": "NEW_PROCESS", "op": "exists", "path": "event"}
        assert "replay results are PARTIAL" in result.stderr

    def test_replay_run_without_scope_sends_none(self, replay_sdk, tmp_path):
        _, run_inst = replay_sdk
        run_inst.run.return_value = _COMPLETE
        result = CliRunner(mix_stderr=False).invoke(cli, _replay_run(tmp_path))
        assert result.exit_code == 0, result.output
        kwargs = run_inst.run.call_args.kwargs
        assert kwargs["selector"] is None and kwargs["sid"] is None
        assert result.stderr == ""
