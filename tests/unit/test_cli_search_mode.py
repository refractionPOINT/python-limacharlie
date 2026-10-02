"""CLI-level tests for the search consumption mode (``--mode``).

Invokes the real commands through Click's CliRunner with only the HTTP layer
mocked, so each test exercises flag parsing, the SDK call, the request that
reaches the wire, and what comes back out.

Two claims are under test. First, that ``--mode`` is a submission-time hint
and nothing more: it appears on the POST that opens the search and on no other
request, and the mode a page actually ran as comes back in that page's stats
rather than being assumed from what was asked for.

Second, that the CLI picks its own default rather than inheriting the SDK's.
The SDK defaults to batch because scripts read every page; a person at a
terminal wants the first rows quickly, so the CLI defaults to interactive and
switches to batch only where the run is evidently a bulk retrieval. Every test
here that exercises a default states which side of that line it is on, because
under CliRunner stdout is never a terminal and the answer would otherwise be
an accident of the harness.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from limacharlie.commands.search import _BULK_OUTPUT_FORMATS, _build_fresh_query_cmd
from limacharlie.search_checkpoint import CheckpointReader, _meta_path
from limacharlie.cli import cli


@pytest.fixture
def checkpoints_dir(tmp_path):
    """Temporary checkpoints metadata directory."""
    cp_dir = tmp_path / "checkpoints_meta"
    cp_dir.mkdir()
    return cp_dir


@pytest.fixture(autouse=True)
def patch_checkpoint_dir(checkpoints_dir):
    """Keep checkpoint metadata out of the developer's real config area."""
    with patch("limacharlie.search_checkpoint.get_data_dir", return_value=str(checkpoints_dir)):
        yield


@pytest.fixture
def mock_org():
    """Mock Organization whose client records every request made."""
    client = MagicMock()
    client.oid = "test-oid"
    client.get_jwt.return_value = "fake-jwt"
    org = MagicMock()
    org.oid = "test-oid"
    org.client = client
    org.get_urls.return_value = {"search": "abc123.replay-search.limacharlie.io"}
    return org


def _page(rows=1, next_token=None, stats=None):
    """One events-type SearchResult, optionally linked to a following page."""
    result = {
        "type": "events",
        "rows": [{"mtd": {"ts": 1700000000000 + i, "stream": "event"},
                  "data": {"routing": {"event_type": "NEW_PROCESS"}}}
                 for i in range(rows)],
    }
    if next_token is not None:
        result["nextToken"] = next_token
    if stats is not None:
        result["stats"] = stats
    return result


def _responses(*pages):
    """Submission response, one poll response per page, then DELETE cleanup."""
    out = [{"queryId": "q-mode"}]
    out.extend({"results": [p], "completed": True} for p in pages)
    out.append({})
    return out


def _invoke(mock_org, args, responses=None, mix_stderr=True, tty=False):
    """Run the CLI with the search HTTP layer mocked.

    ``tty`` says whether the run should look like one with a person watching.
    CliRunner always hands the command a non-terminal stdout, so without this
    every invocation would look like redirected output. Tests that set it pass
    an explicit ``--output`` too, so the rendered format is stated rather than
    auto-detected from the real (non-terminal) stdout.
    """
    if responses is not None:
        mock_org.client.request.side_effect = responses
    runner = CliRunner(mix_stderr=mix_stderr)
    with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
         patch("limacharlie.commands.search.Organization", return_value=mock_org), \
         patch("limacharlie.commands.search._stdout_is_terminal", return_value=tty):
        return runner.invoke(cli, args)


def _posts(mock_org):
    """Parsed bodies of every POST the run made."""
    return [json.loads(c[1]["raw_body"])
            for c in mock_org.client.request.call_args_list if c[0][0] == "POST"]


def _gets(mock_org):
    """Every GET the run made."""
    return [c for c in mock_org.client.request.call_args_list if c[0][0] == "GET"]


class TestSearchRunMode:
    """``search run --mode`` and what it puts on the submission."""

    def test_a_run_at_a_terminal_defaults_to_interactive(self, mock_org):
        """The headline case: someone typed this and is waiting for rows."""
        result = _invoke(mock_org, [
            "--oid", "test-oid", "--output", "table",
            "search", "run", "--query", "* | * | *",
            "--start", "1700000000", "--end", "1700086400",
            "--stream", "event",
        ], _responses(_page()), tty=True)

        assert result.exit_code == 0, result.output
        assert _posts(mock_org) == [{
            "oid": "test-oid",
            "query": "* | * | *",
            "startTime": "1700000000",
            "endTime": "1700086400",
            "paginated": True,
            "stream": "event",
            "mode": "interactive",
        }]

    def test_the_cli_never_leaves_the_mode_to_the_sdk_default(self, mock_org):
        """The SDK defaults to batch for the scripts that call it. The CLI
        resolves its own mode on every path, so that default can never reach a
        command line."""
        result = _invoke(mock_org, [
            "--oid", "test-oid", "--output", "table",
            "search", "run", "--query", "* | * | *",
            "--start", "1700000000", "--end", "1700086400",
        ], _responses(_page()), tty=True)

        assert result.exit_code == 0, result.output
        assert _posts(mock_org)[0]["mode"] == "interactive"

    @pytest.mark.parametrize("mode", ["batch", "interactive"])
    def test_mode_flag_is_sent_verbatim(self, mock_org, mode):
        result = _invoke(mock_org, [
            "--oid", "test-oid", "--output", "json",
            "search", "run", "--query", "* | * | *",
            "--start", "1700000000", "--end", "1700086400",
            "--mode", mode,
        ], _responses(_page()))

        assert result.exit_code == 0, result.output
        assert _posts(mock_org)[0]["mode"] == mode

    def test_mode_does_not_disturb_the_rest_of_the_submission(self, mock_org):
        result = _invoke(mock_org, [
            "--oid", "test-oid", "--output", "json",
            "search", "run", "--query", "* | NEW_PROCESS | *",
            "--start", "1700000000", "--end", "1700086400",
            "--stream", "detect", "--mode", "batch",
        ], _responses(_page()), tty=True)

        assert result.exit_code == 0, result.output
        assert _posts(mock_org) == [{
            "oid": "test-oid",
            "query": "* | NEW_PROCESS | *",
            "startTime": "1700000000",
            "endTime": "1700086400",
            "paginated": True,
            "stream": "detect",
            "mode": "batch",
        }]

    @pytest.mark.parametrize("bad", ["Batch", "BATCH", "Interactive", "turbo", "", "fast"])
    def test_an_unrecognised_mode_is_refused_without_a_request(self, mock_org, bad):
        """The server would ignore the value and run the search as interactive,
        which spends the query and reports nothing wrong. The CLI refuses it
        first, so a typo costs an error message instead of a silent downgrade."""
        result = _invoke(mock_org, [
            "--oid", "test-oid",
            "search", "run", "--query", "* | * | *",
            "--start", "1700000000", "--end", "1700086400",
            "--mode", bad,
        ])

        assert result.exit_code != 0
        assert "--mode" in result.output
        mock_org.client.request.assert_not_called()

    def test_the_refusal_names_the_modes_that_exist(self, mock_org):
        result = _invoke(mock_org, [
            "--oid", "test-oid",
            "search", "run", "--query", "* | * | *",
            "--start", "1700000000", "--end", "1700086400",
            "--mode", "Batch",
        ])

        assert "interactive" in result.output
        assert "batch" in result.output

    def test_both_modes_are_listed_in_the_help(self, mock_org):
        result = _invoke(mock_org, ["search", "run", "--help"])

        assert result.exit_code == 0
        assert "--mode" in result.output
        assert "interactive" in result.output
        assert "batch" in result.output


class TestDefaultModeSplit:
    """Which side of the bulk-retrieval line each run lands on.

    The rule: interactive, unless the run is driven by a checkpoint, or
    stdout is not a terminal, or the output format exists to be consumed by
    something other than a reader.
    """

    def _mode_of(self, mock_org, fmt=None, tty=False, mode=None,
                 global_flags=(), run_flags=()):
        """Run one search and report the mode that reached the submission."""
        args = ["--oid", "test-oid"]
        if fmt is not None:
            args += ["--output", fmt]
        args += list(global_flags)
        args += ["search", "run", "--query", "* | * | *",
                 "--start", "1700000000", "--end", "1700086400"]
        if mode is not None:
            args += ["--mode", mode]
        args += list(run_flags)

        result = _invoke(mock_org, args, _responses(_page()), tty=tty)
        assert result.exit_code == 0, result.output
        return _posts(mock_org)[0]["mode"]

    @pytest.mark.parametrize("fmt", ["table", "json", "yaml"])
    def test_a_readable_format_at_a_terminal_is_interactive(self, mock_org, fmt):
        """table is what a terminal renders by default; json and yaml are both
        readable and a person may reasonably ask for either on screen."""
        assert self._mode_of(mock_org, fmt=fmt, tty=True) == "interactive"

    @pytest.mark.parametrize("fmt", ["jsonl", "csv", "toon"])
    def test_an_export_format_is_batch_even_at_a_terminal(self, mock_org, fmt):
        """jsonl is this CLI's own recommendation for 100K+ events, csv is an
        export, and toon exists to be fed to an LLM. None is read a page at a
        time, so asking for one states the intent on its own."""
        assert self._mode_of(mock_org, fmt=fmt, tty=True) == "batch"

    @pytest.mark.parametrize("fmt", ["table", "json", "yaml", "jsonl", "csv"])
    def test_redirected_output_is_batch_whatever_the_format(self, mock_org, fmt):
        """Nobody is reading pages as they arrive when stdout is a file or a
        pipe, so the format stops mattering."""
        assert self._mode_of(mock_org, fmt=fmt, tty=False) == "batch"

    def test_an_unset_output_format_follows_the_terminal(self, mock_org):
        """With no --output the format is auto-detected from the same signal,
        so the two agree rather than fighting."""
        assert self._mode_of(mock_org, tty=False) == "batch"

    @pytest.mark.parametrize("fmt", ["table", "json", "yaml", "jsonl", "csv", "toon"])
    def test_mode_overrides_the_default_on_every_format(self, mock_org, fmt):
        assert self._mode_of(mock_org, fmt=fmt, tty=False,
                             mode="interactive") == "interactive"
        mock_org.client.request.reset_mock()
        assert self._mode_of(mock_org, fmt=fmt, tty=True,
                             mode="batch") == "batch"

    def test_a_reading_flag_does_not_flip_the_default(self, mock_org):
        """--expand and --raw are ways of reading results, not exporting them,
        so they leave the terminal default alone."""
        assert self._mode_of(mock_org, fmt="table", tty=True,
                             run_flags=("--expand",)) == "interactive"

    def test_an_ambiguous_format_prefers_interactive(self, mock_org):
        """json is the one genuinely ambiguous format: it is what an unset
        --output resolves to when piped, and also a perfectly readable thing
        to ask for on screen. At a terminal it stays interactive, because an
        over-large page in front of someone waiting is the worse failure."""
        assert self._mode_of(mock_org, fmt="json", tty=True) == "interactive"

    def test_quiet_needs_no_rule_because_it_submits_nothing(self, mock_org):
        """--quiet short-circuits the output path without ever iterating the
        results generator, so the search is never submitted and there is no
        mode to pick. Recorded so that a future change to --quiet shows up
        here rather than as a silently batch-shaped run."""
        result = _invoke(mock_org, [
            "--oid", "test-oid", "--output", "table", "--quiet",
            "search", "run", "--query", "* | * | *",
            "--start", "1700000000", "--end", "1700086400",
        ], _responses(_page()), tty=True)

        assert result.exit_code == 0, result.output
        assert _posts(mock_org) == []


class TestModeIsSubmittedOnce:
    """Continuation pages inherit the mode and never resend it."""

    def test_three_pages_make_one_submission(self, mock_org):
        result = _invoke(mock_org, [
            "--oid", "test-oid", "--output", "json",
            "search", "run", "--query", "* | * | *",
            "--start", "1700000000", "--end", "1700086400",
            "--mode", "batch",
        ], _responses(_page(next_token="tok-1"), _page(next_token="tok-2"), _page()))

        assert result.exit_code == 0, result.output
        posts = _posts(mock_org)
        assert len(posts) == 1
        assert posts[0]["mode"] == "batch"

    def test_continuation_requests_carry_only_the_token(self, mock_org):
        result = _invoke(mock_org, [
            "--oid", "test-oid", "--output", "json",
            "search", "run", "--query", "* | * | *",
            "--start", "1700000000", "--end", "1700086400",
            "--mode", "batch",
        ], _responses(_page(next_token="tok-1"), _page()))

        assert result.exit_code == 0, result.output
        gets = _gets(mock_org)
        assert len(gets) == 2
        assert gets[0][1].get("query_params") is None
        assert gets[1][1]["query_params"] == {"token": "tok-1"}
        for get in gets:
            assert "raw_body" not in get[1]
            assert "mode" not in (get[1].get("query_params") or {})


class TestModeSurvivesACheckpoint:
    """A checkpoint records the mode because a resume submits a fresh search."""

    def _run_with_checkpoint(self, mock_org, tmp_path, extra_args=(), pages=1):
        data_path = str(tmp_path / "cp.jsonl")
        args = [
            "--oid", "test-oid", "--output", "json",
            "search", "run", "--query", "* | * | *",
            "--start", "1700000000", "--end", "1700086400",
            "--checkpoint", data_path,
        ]
        args.extend(extra_args)
        pages_spec = [_page(next_token=f"tok-{i}") for i in range(pages - 1)] + [_page()]
        result = _invoke(mock_org, args, _responses(*pages_spec))
        assert result.exit_code == 0, result.output
        return data_path

    def test_the_mode_is_recorded(self, mock_org, tmp_path):
        data_path = self._run_with_checkpoint(mock_org, tmp_path, ["--mode", "batch"])

        assert CheckpointReader.read_metadata(data_path)["mode"] == "batch"

    def test_a_run_without_a_mode_records_the_resolved_batch(self, mock_org, tmp_path):
        """A checkpointed run is a bulk retrieval by construction, so it
        resolves to batch, and what lands in the metadata is that resolved
        mode rather than the empty flag."""
        data_path = self._run_with_checkpoint(mock_org, tmp_path)

        assert CheckpointReader.read_metadata(data_path)["mode"] == "batch"

    def test_a_checkpointed_run_is_batch_even_at_a_terminal(self, mock_org, tmp_path):
        """Pages go to the file as they arrive and nothing renders until the
        search ends, so there is nobody reading them however it was started."""
        data_path = str(tmp_path / "cp_tty.jsonl")
        result = _invoke(mock_org, [
            "--oid", "test-oid", "--output", "table",
            "search", "run", "--query", "* | * | *",
            "--start", "1700000000", "--end", "1700086400",
            "--checkpoint", data_path,
        ], _responses(_page()), tty=True)

        assert result.exit_code == 0, result.output
        assert _posts(mock_org)[0]["mode"] == "batch"

    def test_mode_overrides_the_checkpoint_default_and_is_what_gets_recorded(
            self, mock_org, tmp_path):
        data_path = self._run_with_checkpoint(mock_org, tmp_path,
                                              ["--mode", "interactive"])

        assert _posts(mock_org)[0]["mode"] == "interactive"
        assert CheckpointReader.read_metadata(data_path)["mode"] == "interactive"

    def test_recording_the_mode_leaves_the_rest_of_the_metadata_alone(
            self, mock_org, tmp_path):
        data_path = self._run_with_checkpoint(mock_org, tmp_path, ["--mode", "batch"])

        meta = CheckpointReader.read_metadata(data_path)
        assert meta["query"] == "* | * | *"
        assert meta["start_time"] == 1700000000
        assert meta["end_time"] == 1700086400
        assert meta["completed"] is True
        assert meta["version"] == 1


class TestResumeCarriesTheMode:
    """A resume opens a new search, so it has to re-state the mode."""

    def _interrupted_checkpoint(self, mock_org, tmp_path, mode=None):
        """Run one page, then interrupt on the second, leaving a resumable
        checkpoint with a stored token."""
        data_path = str(tmp_path / "resume.jsonl")
        calls = {"n": 0}

        def side_effect(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                return {"queryId": "q-init"}
            if calls["n"] == 2:
                return {"results": [_page(next_token="tok-1")], "completed": True}
            if calls["n"] == 3:
                raise KeyboardInterrupt()
            return {}

        mock_org.client.request.side_effect = side_effect
        args = [
            "--oid", "test-oid", "--output", "json",
            "search", "run", "--query", "* | * | *",
            "--start", "1700000000", "--end", "1700086400",
            "--checkpoint", data_path,
        ]
        if mode is not None:
            args.extend(["--mode", mode])
        _invoke(mock_org, args, mix_stderr=False)

        meta = CheckpointReader.read_metadata(data_path)
        assert meta["completed"] is False
        assert meta["last_token"] == "tok-1"
        mock_org.client.request.reset_mock()
        mock_org.client.request.side_effect = None
        return data_path

    def test_resume_resends_the_recorded_mode(self, mock_org, tmp_path):
        data_path = self._interrupted_checkpoint(mock_org, tmp_path, mode="batch")

        result = _invoke(mock_org, [
            "--oid", "test-oid", "--output", "json",
            "search", "run", "--resume", "--checkpoint", data_path,
        ], _responses(_page()))

        assert result.exit_code == 0, result.output
        assert _posts(mock_org)[0]["mode"] == "batch"

    def test_resume_of_a_run_that_named_no_mode_repeats_the_recorded_batch(
            self, mock_org, tmp_path):
        """The original run resolved to batch and recorded it, so the resume
        repeats that rather than re-deriving it from this invocation."""
        data_path = self._interrupted_checkpoint(mock_org, tmp_path)
        assert CheckpointReader.read_metadata(data_path)["mode"] == "batch"

        result = _invoke(mock_org, [
            "--oid", "test-oid", "--output", "json",
            "search", "run", "--resume", "--checkpoint", data_path,
        ], _responses(_page()))

        assert result.exit_code == 0, result.output
        assert _posts(mock_org)[0]["mode"] == "batch"

    def test_resume_of_an_interactive_run_repeats_interactive(self, mock_org, tmp_path):
        """The recorded mode wins over the checkpoint-driven default, so a run
        that was deliberately interactive is not silently promoted."""
        data_path = self._interrupted_checkpoint(mock_org, tmp_path,
                                                 mode="interactive")

        result = _invoke(mock_org, [
            "--oid", "test-oid", "--output", "json",
            "search", "run", "--resume", "--checkpoint", data_path,
        ], _responses(_page()))

        assert result.exit_code == 0, result.output
        assert _posts(mock_org)[0]["mode"] == "interactive"

    def test_a_checkpoint_predating_the_field_falls_back_to_the_default(
            self, mock_org, tmp_path):
        """Metadata written before the mode was recorded has no ``mode`` key at
        all. Reading it must not fail, and with nothing recorded the resume is
        treated as the bulk retrieval it is."""
        data_path = self._interrupted_checkpoint(mock_org, tmp_path, mode="batch")
        meta_file = _meta_path(data_path)
        with open(meta_file, "r", encoding="utf-8") as handle:
            meta = json.load(handle)
        del meta["mode"]
        with open(meta_file, "w", encoding="utf-8") as handle:
            json.dump(meta, handle)

        result = _invoke(mock_org, [
            "--oid", "test-oid", "--output", "json",
            "search", "run", "--resume", "--checkpoint", data_path,
        ], _responses(_page()), tty=True)

        assert result.exit_code == 0, result.output
        assert _posts(mock_org)[0]["mode"] == "batch"

    def test_mode_on_the_resume_overrides_the_recorded_one(self, mock_org, tmp_path):
        """Allowed, unlike --query or --start, because the mode moves the page
        boundaries and nothing else: the rows already on disk and the rows
        still to come are the same either way."""
        data_path = self._interrupted_checkpoint(mock_org, tmp_path, mode="batch")

        result = _invoke(mock_org, [
            "--oid", "test-oid", "--output", "json",
            "search", "run", "--resume", "--checkpoint", data_path,
            "--mode", "interactive",
        ], _responses(_page()))

        assert result.exit_code == 0, result.output
        assert _posts(mock_org)[0]["mode"] == "interactive"

    def test_the_override_does_not_rewrite_what_the_checkpoint_recorded(
            self, mock_org, tmp_path):
        """The override applies to this leg only, the same way --limit does."""
        data_path = self._interrupted_checkpoint(mock_org, tmp_path, mode="batch")

        _invoke(mock_org, [
            "--oid", "test-oid", "--output", "json",
            "search", "run", "--resume", "--checkpoint", data_path,
            "--mode", "interactive",
        ], _responses(_page()))

        assert CheckpointReader.read_metadata(data_path)["mode"] == "batch"

    def test_the_resume_still_hands_the_server_the_stored_cursor(
            self, mock_org, tmp_path):
        """Re-stating the mode must not disturb how a resume skips ahead."""
        data_path = self._interrupted_checkpoint(mock_org, tmp_path, mode="batch")

        result = _invoke(mock_org, [
            "--oid", "test-oid", "--output", "json",
            "search", "run", "--resume", "--checkpoint", data_path,
        ], _responses(_page()))

        assert result.exit_code == 0, result.output
        gets = _gets(mock_org)
        assert gets[0][1]["query_params"] == {"token": "tok-1"}

    def test_the_rerun_command_offered_on_a_rejected_token_keeps_the_mode(self):
        """When a token is refused the CLI prints a command to start over. It
        has to carry the mode, or following it silently changes the run."""
        cmd = _build_fresh_query_cmd(
            {"query": "* | * | *", "start_time": 1, "end_time": 2,
             "stream": "event", "limit": 5, "mode": "batch"},
            "/tmp/cp.jsonl",
        )
        assert "--mode batch" in cmd

    def test_the_rerun_command_omits_a_mode_that_was_never_set(self):
        cmd = _build_fresh_query_cmd(
            {"query": "* | * | *", "start_time": 1, "end_time": 2, "mode": None},
            "/tmp/cp.jsonl",
        )
        assert "--mode" not in cmd


class TestSavedRunMode:
    """A saved query is executed like any other search and takes a mode."""

    def _saved_record(self):
        record = MagicMock()
        record.data = {"query": "* | * | *", "start": 1700000000, "end": 1700086400,
                       "stream": "event"}
        return record

    def _invoke_saved(self, mock_org, args, responses, tty=False):
        mock_org.client.request.side_effect = responses
        hive = MagicMock()
        hive.get.return_value = self._saved_record()
        runner = CliRunner()
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org), \
             patch("limacharlie.commands.search.Hive", return_value=hive), \
             patch("limacharlie.commands.search._stdout_is_terminal", return_value=tty):
            return runner.invoke(cli, args)

    def test_saved_run_sends_the_mode(self, mock_org):
        result = self._invoke_saved(mock_org, [
            "--oid", "test-oid", "--output", "json",
            "search", "saved-run", "--name", "my-query", "--mode", "batch",
        ], _responses(_page()))

        assert result.exit_code == 0, result.output
        assert _posts(mock_org)[0]["mode"] == "batch"

    def test_saved_run_at_a_terminal_defaults_to_interactive(self, mock_org):
        """saved-run has no --checkpoint, so it follows the same rule as a
        plain run: a person reading the output gets interactive."""
        result = self._invoke_saved(mock_org, [
            "--oid", "test-oid", "--output", "table",
            "search", "saved-run", "--name", "my-query",
        ], _responses(_page()), tty=True)

        assert result.exit_code == 0, result.output
        assert _posts(mock_org)[0]["mode"] == "interactive"

    def test_saved_run_redirected_defaults_to_batch(self, mock_org):
        result = self._invoke_saved(mock_org, [
            "--oid", "test-oid", "--output", "json",
            "search", "saved-run", "--name", "my-query",
        ], _responses(_page()), tty=False)

        assert result.exit_code == 0, result.output
        assert _posts(mock_org)[0]["mode"] == "batch"

    def test_saved_run_export_format_defaults_to_batch(self, mock_org):
        result = self._invoke_saved(mock_org, [
            "--oid", "test-oid", "--output", "jsonl",
            "search", "saved-run", "--name", "my-query",
        ], _responses(_page()), tty=True)

        assert result.exit_code == 0, result.output
        assert _posts(mock_org)[0]["mode"] == "batch"

    def test_saved_run_refuses_an_unrecognised_mode(self, mock_org):
        result = self._invoke_saved(mock_org, [
            "--oid", "test-oid",
            "search", "saved-run", "--name", "my-query", "--mode", "Batch",
        ], _responses(_page()))

        assert result.exit_code != 0
        assert "--mode" in result.output


class TestPageStatsReachTheCaller:
    """What the page ran as comes back with the page."""

    _STATS = {
        "eventsMatched": 2,
        "eventsScanned": 40,
        "searchMode": "batch",
        "pageSize": 1000,
        "paginatedByteCap": 1048576,
    }

    def test_json_output_carries_all_three_fields(self, mock_org):
        result = _invoke(mock_org, [
            "--oid", "test-oid", "--output", "json",
            "search", "run", "--query", "* | * | *",
            "--start", "1700000000", "--end", "1700086400",
            "--mode", "batch",
        ], _responses(_page(stats=self._STATS)))

        assert result.exit_code == 0, result.output
        stats = json.loads(result.output)[0]["stats"]
        assert stats["searchMode"] == "batch"
        assert stats["pageSize"] == 1000
        assert stats["paginatedByteCap"] == 1048576

    def test_an_unpaginated_search_carries_none_of_them(self, mock_org):
        """The server omits all three when the search did not paginate, and the
        CLI does not fill them in."""
        result = _invoke(mock_org, [
            "--oid", "test-oid", "--output", "json",
            "search", "run", "--query", "* | * | * | COUNT(event) as n",
            "--start", "1700000000", "--end", "1700086400",
        ], _responses(_page(stats={"eventsMatched": 2, "eventsScanned": 40})))

        assert result.exit_code == 0, result.output
        stats = json.loads(result.output)[0]["stats"]
        assert "searchMode" not in stats
        assert "pageSize" not in stats
        assert "paginatedByteCap" not in stats

    def test_jsonl_output_carries_them_too(self, mock_org):
        result = _invoke(mock_org, [
            "--oid", "test-oid", "--output", "jsonl",
            "search", "run", "--query", "* | * | *",
            "--start", "1700000000", "--end", "1700086400",
            "--mode", "batch",
        ], _responses(_page(stats=self._STATS)))

        assert result.exit_code == 0, result.output
        lines = [line for line in result.output.strip().split("\n") if line.strip()]
        assert json.loads(lines[0])["stats"]["pageSize"] == 1000

    def test_an_applied_mode_that_differs_from_the_request_is_reported_as_is(
            self, mock_org):
        """The mode is enabled per organization and the server may choose one
        itself, so asking for batch and getting interactive is a normal
        outcome, not an error."""
        stats = dict(self._STATS, searchMode="interactive")
        result = _invoke(mock_org, [
            "--oid", "test-oid", "--output", "json",
            "search", "run", "--query", "* | * | *",
            "--start", "1700000000", "--end", "1700086400",
            "--mode", "batch",
        ], _responses(_page(stats=stats)))

        assert result.exit_code == 0, result.output
        assert json.loads(result.output)[0]["stats"]["searchMode"] == "interactive"

    def test_the_stats_line_reports_the_applied_mode(self, mock_org):
        """Table output summarises the page on stderr. Without the mode on that
        line the user has no way to see the hint was not taken."""
        result = _invoke(mock_org, [
            "--oid", "test-oid", "--output", "table",
            "search", "run", "--query", "* | * | *",
            "--start", "1700000000", "--end", "1700086400",
            "--mode", "batch",
        ], _responses(_page(stats=dict(self._STATS, searchMode="interactive"))),
            mix_stderr=False)

        assert result.exit_code == 0, result.output
        assert "mode: interactive" in result.stderr

    def test_the_stats_line_omits_the_mode_when_the_page_reports_none(self, mock_org):
        result = _invoke(mock_org, [
            "--oid", "test-oid", "--output", "table",
            "search", "run", "--query", "* | * | *",
            "--start", "1700000000", "--end", "1700086400",
        ], _responses(_page(stats={"eventsMatched": 2, "eventsScanned": 40})),
            mix_stderr=False)

        assert result.exit_code == 0, result.output
        assert "Stats:" in result.stderr
        assert "mode" not in result.stderr


class TestTheFormatSplitStaysInStepWithTheOutputChoices:
    """``--output`` and the bulk-format set are two hand-maintained lists.

    A format added to one and not the other is silently classified by
    omission, which lands it on the interactive side with nothing to say so.
    """

    def _output_choices(self):
        for param in cli.params:
            if param.name == "output_format":
                return set(param.type.choices)
        raise AssertionError("the --output option is gone; this rule needs rewriting")

    def test_every_bulk_format_is_a_real_output_choice(self):
        assert _BULK_OUTPUT_FORMATS <= self._output_choices()

    def test_every_output_choice_is_deliberately_classified(self):
        """The readable side is spelled out rather than inferred, so adding a
        format to --output without deciding which side it belongs on fails
        here instead of defaulting quietly."""
        readable = {"table", "json", "yaml"}
        assert _BULK_OUTPUT_FORMATS | readable == self._output_choices()
        assert not (_BULK_OUTPUT_FORMATS & readable)
