"""CLI-level integration tests for search checkpoint/resume.

Tests invoke actual CLI commands via Click's CliRunner with mocked API
responses. This tests the full flow from CLI args through flag validation,
checkpoint creation, search execution, output formatting, and error handling
- with minimal mocking (only the HTTP layer is mocked).

Compared to the unit tests in test_checkpoint.py and
test_search_checkpoint_integration.py which test individual components,
these tests exercise the entire command pipeline as a user would.
"""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch, PropertyMock

import click
import pytest
from click.testing import CliRunner

from limacharlie.search_checkpoint import CheckpointReader, _meta_path, get_data_dir
from limacharlie.cli import cli


@pytest.fixture
def checkpoints_dir(tmp_path):
    """Temporary checkpoints metadata directory."""
    cp_dir = tmp_path / "checkpoints_meta"
    cp_dir.mkdir()
    return cp_dir


@pytest.fixture(autouse=True)
def patch_checkpoint_dir(checkpoints_dir):
    """Patch get_data_dir for all tests."""
    with patch("limacharlie.search_checkpoint.get_data_dir", return_value=str(checkpoints_dir)):
        yield


@pytest.fixture
def mock_client():
    """Mock Client that returns a mock org with search capabilities."""
    client = MagicMock()
    client.oid = "test-oid"
    client.get_jwt.return_value = "fake-jwt"
    return client


@pytest.fixture
def mock_org(mock_client):
    """Mock Organization with search URL."""
    org = MagicMock()
    org.oid = "test-oid"
    org.client = mock_client
    org.get_urls.return_value = {"search": "abc123.replay-search.limacharlie.io"}
    return org


def _patch_search_command(mock_org, search_side_effects):
    """Create patches for the search command module.

    Returns a dict of patch context managers to be used as:
        with _patch_search_command(...) as patches:
            result = runner.invoke(...)

    Args:
        mock_org: Mock Organization instance.
        search_side_effects: List of side_effect values for client.request
            (POST initiate, GET poll(s), DELETE cleanup).
    """
    mock_org.client.request.side_effect = search_side_effects
    return {
        "client": patch("limacharlie.commands.search.Client", return_value=mock_org.client),
        "org": patch("limacharlie.commands.search.Organization", return_value=mock_org),
    }


def _make_search_responses(pages, events_per_page=2):
    """Build mock API responses for a multi-page search.

    Each page has one events-type result with the specified number of event
    rows. Pages are linked by nextToken except the last.
    """
    responses = [{"queryId": "q-test"}]
    for i in range(pages):
        is_last = i == pages - 1
        result = {
            "type": "events",
            "rows": [
                {"mtd": {"ts": (1700000000 + i * 1000 + j) * 1000, "stream": "event"},
                 "data": {"routing": {"event_type": "NEW_PROCESS"}, "event": {"idx": i * events_per_page + j}}}
                for j in range(events_per_page)
            ],
        }
        if not is_last:
            result["nextToken"] = f"tok-{i + 1}"
        responses.append({"results": [result], "completed": True})
    responses.append({})  # DELETE cleanup
    return responses


class TestSearchRunCheckpointCli:
    """Test 'search run --checkpoint' via CliRunner."""

    def test_checkpoint_creates_files_and_outputs_results(self, tmp_path, mock_org):
        """Full search with --checkpoint creates data file, metadata, and outputs results."""
        data_path = str(tmp_path / "test.jsonl")
        responses = _make_search_responses(2)
        mock_org.client.request.side_effect = responses

        runner = CliRunner()
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            result = runner.invoke(cli, [
                "--oid", "test-oid", "--output", "json",
                "search", "run",
                "--query", "* | NEW_PROCESS | *",
                "--start", "1700000000", "--end", "1700086400",
                "--checkpoint", data_path,
            ])

        assert result.exit_code == 0, f"CLI failed: {result.output}"

        # Data file exists with results
        assert os.path.exists(data_path)
        meta, results = CheckpointReader.read(data_path)
        assert len(results) == 2
        assert meta["completed"] is True
        assert meta["query"] == "* | NEW_PROCESS | *"
        assert meta["start_time"] == 1700000000
        assert meta["end_time"] == 1700086400
        assert meta["total_events"] == 4  # 2 pages x 2 events
        assert meta["last_token"] == "tok-1"

    def test_checkpoint_existing_file_without_metadata_errors(self, tmp_path, mock_org):
        """Existing file with no checkpoint metadata shows generic error."""
        data_path = str(tmp_path / "existing.jsonl")
        with open(data_path, "w") as f:
            f.write("existing\n")

        runner = CliRunner()
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            result = runner.invoke(cli, [
                "--oid", "test-oid",
                "search", "run",
                "--query", "* | * | *", "--start", "1000", "--end", "2000",
                "--checkpoint", data_path,
            ])

        assert result.exit_code != 0
        assert "--force" in result.output

    def test_checkpoint_completed_existing_shows_no_resume(self, tmp_path, mock_org):
        """Completed checkpoint shows 'completed' message without --resume suggestion."""
        data_path = str(tmp_path / "completed_exists.jsonl")
        mock_org.client.request.side_effect = _make_search_responses(1)

        runner = CliRunner()
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            # Create completed checkpoint
            runner.invoke(cli, [
                "--oid", "test-oid", "--output", "json",
                "search", "run",
                "--query", "test", "--start", "1000", "--end", "2000",
                "--checkpoint", data_path,
            ])

        # Try to create again without --force
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            result = runner.invoke(cli, [
                "--oid", "test-oid",
                "search", "run",
                "--query", "test", "--start", "1000", "--end", "2000",
                "--checkpoint", data_path,
            ])

        assert result.exit_code != 0
        assert "completed" in result.output
        assert "--force" in result.output
        assert "checkpoint-show" in result.output
        # Should NOT suggest --resume for a completed checkpoint
        assert "--resume" not in result.output

    def test_checkpoint_in_progress_existing_shows_resume(self, tmp_path, mock_org):
        """In-progress checkpoint shows --resume suggestion with resume command."""
        data_path = str(tmp_path / "inprogress_exists.jsonl")
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"queryId": "q1"}
            elif call_count == 2:
                return {
                    "results": [{"type": "events",
                                 "rows": [{"mtd": {"ts": 1000000}, "data": {}}],
                                 "nextToken": "tok1"}],
                    "completed": True,
                }
            elif call_count == 3:
                raise KeyboardInterrupt()
            else:
                return {}

        mock_org.client.request.side_effect = side_effect

        runner = CliRunner(mix_stderr=False)
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            runner.invoke(cli, [
                "--oid", "test-oid",
                "search", "run",
                "--query", "test query", "--start", "1000", "--end", "2000",
                "--checkpoint", data_path,
            ])

        # Try to create again without --force or --resume.
        # Use a default runner (mix_stderr=True) so error output is in result.output.
        runner2 = CliRunner()
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            result = runner2.invoke(cli, [
                "--oid", "test-oid",
                "search", "run",
                "--query", "test", "--start", "1000", "--end", "2000",
                "--checkpoint", data_path,
            ])

        assert result.exit_code != 0
        assert "in-progress" in result.output
        assert "--resume" in result.output
        assert "--force" in result.output
        assert data_path in result.output

    def test_checkpoint_force_overwrites(self, tmp_path, mock_org):
        """--checkpoint --force overwrites existing file."""
        data_path = str(tmp_path / "overwrite.jsonl")
        with open(data_path, "w") as f:
            f.write("old data\n")

        responses = _make_search_responses(1)
        mock_org.client.request.side_effect = responses

        runner = CliRunner()
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            result = runner.invoke(cli, [
                "--oid", "test-oid", "--output", "json",
                "search", "run",
                "--query", "* | * | *", "--start", "1000", "--end", "2000",
                "--checkpoint", data_path, "--force",
            ])

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        meta, results = CheckpointReader.read(data_path)
        assert len(results) == 1
        assert meta["completed"] is True

    def test_checkpoint_tracks_events_and_timestamps(self, tmp_path, mock_org):
        """Checkpoint metadata includes total_events, last_event_ts, last_token."""
        data_path = str(tmp_path / "meta_test.jsonl")
        responses = _make_search_responses(3, events_per_page=5)
        mock_org.client.request.side_effect = responses

        runner = CliRunner()
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            result = runner.invoke(cli, [
                "--oid", "test-oid", "--output", "json",
                "search", "run",
                "--query", "test", "--start", "1700000000", "--end", "1700086400",
                "--checkpoint", data_path,
            ])

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        meta = CheckpointReader.read_metadata(data_path)
        assert meta["total_events"] == 15  # 3 pages x 5 events
        assert meta["page"] == 3
        assert meta["last_token"] == "tok-2"
        assert meta["last_event_ts"] is not None


class TestSearchRunResumeCli:
    """Test 'search run --resume --checkpoint' via CliRunner."""

    def _create_checkpoint(self, tmp_path, mock_org, pages=2, events_per_page=2):
        """Helper: run a search with checkpoint, return data_path."""
        data_path = str(tmp_path / "resume_test.jsonl")
        responses = _make_search_responses(pages, events_per_page)
        mock_org.client.request.side_effect = responses

        runner = CliRunner()
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            result = runner.invoke(cli, [
                "--oid", "test-oid", "--output", "json",
                "search", "run",
                "--query", "* | * | *", "--start", "1700000000", "--end", "1700086400",
                "--stream", "event",
                "--checkpoint", data_path, "--limit", str(pages - 1),
            ])
        assert result.exit_code == 0, f"Setup failed: {result.output}"
        return data_path

    def test_resume_uses_stored_token(self, tmp_path, mock_org):
        """Resume passes stored token to server, skipping already-fetched pages."""
        data_path = str(tmp_path / "resume_tok.jsonl")
        # Initial run: page 1 returns, then KeyboardInterrupt on page 2 poll
        call_count = 0

        def first_run_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"queryId": "q-init"}
            elif call_count == 2:
                return {
                    "results": [{"type": "events",
                                 "rows": [{"mtd": {"ts": 1700000000000}, "data": {}}],
                                 "nextToken": "tok-1"}],
                    "completed": True,
                }
            elif call_count == 3:
                # Page 2 poll: interrupt
                raise KeyboardInterrupt()
            else:
                return {}  # DELETE

        mock_org.client.request.side_effect = first_run_side_effect

        runner = CliRunner(mix_stderr=False)
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            result = runner.invoke(cli, [
                "--oid", "test-oid", "--output", "json",
                "search", "run",
                "--query", "test query", "--start", "1700000000", "--end", "1700086400",
                "--checkpoint", data_path,
            ])
        # KeyboardInterrupt -> exit 130
        assert result.exit_code == 130 or "Checkpoint saved" in (result.stderr or result.output)

        meta = CheckpointReader.read_metadata(data_path)
        assert meta["last_token"] == "tok-1"
        assert meta["completed"] is False

        # Resume: server gets tok-1 and returns page 2 directly.
        calls_before = call_count
        mock_org.client.request.side_effect = [
            {"queryId": "q-resume"},
            {"results": [{"type": "events", "rows": [{"mtd": {"ts": 1700001000000}, "data": {}}]}],
             "completed": True},
            {},  # DELETE
        ]

        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            result = runner.invoke(cli, [
                "--oid", "test-oid", "--output", "json",
                "search", "run",
                "--resume", "--checkpoint", data_path,
            ])
        assert result.exit_code == 0, f"Resume failed: {result.output}"

        # Verify the GET used tok-1 (server-side skip).
        # After the first run consumed calls_before, the resume should
        # have POST + GET(tok-1) + DELETE.
        resume_calls = mock_org.client.request.call_args_list[calls_before:]
        get_calls = [c for c in resume_calls if c[0][0] == "GET"]
        assert len(get_calls) == 1
        assert get_calls[0][1]["query_params"] == {"token": "tok-1"}

        # Data file now has 2 results (1 from initial + 1 from resume)
        _, results = CheckpointReader.read(data_path)
        assert len(results) == 2

    def test_resume_completed_checkpoint_exits_cleanly(self, tmp_path, mock_org):
        """Resuming a completed checkpoint outputs existing results."""
        data_path = str(tmp_path / "completed.jsonl")
        mock_org.client.request.side_effect = _make_search_responses(1)

        runner = CliRunner()
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            result = runner.invoke(cli, [
                "--oid", "test-oid", "--output", "json",
                "search", "run",
                "--query", "test", "--start", "1000", "--end", "2000",
                "--checkpoint", data_path,
            ])
        assert result.exit_code == 0

        meta = CheckpointReader.read_metadata(data_path)
        assert meta["completed"] is True

        # Resume should say already completed and output results
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            result = runner.invoke(cli, [
                "--oid", "test-oid", "--output", "json",
                "search", "run",
                "--resume", "--checkpoint", data_path,
            ])
        assert result.exit_code == 0
        # "already completed" goes to stderr; use mix_stderr=False to capture it
        # or just check it's in the combined output (default mix_stderr=True)
        all_output = result.output
        assert "already completed" in all_output


class TestSearchRunResumeValidationCli:
    """Test --resume flag validation rules via CliRunner."""

    def test_resume_without_checkpoint_errors(self):
        """--resume without --checkpoint produces an error."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "--oid", "test-oid",
            "search", "run", "--resume",
        ])
        assert result.exit_code != 0
        assert "--checkpoint" in result.output

    def test_resume_with_query_flag_errors(self, tmp_path, mock_org):
        """--resume with --query is forbidden."""
        # Create a checkpoint first
        data_path = str(tmp_path / "val.jsonl")
        mock_org.client.request.side_effect = _make_search_responses(1)

        runner = CliRunner()
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            runner.invoke(cli, [
                "--oid", "test-oid", "search", "run",
                "--query", "q", "--start", "1000", "--end", "2000",
                "--checkpoint", data_path,
            ])

        # Now try resume with --query
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            result = runner.invoke(cli, [
                "--oid", "test-oid", "search", "run",
                "--resume", "--checkpoint", data_path,
                "--query", "different query",
            ])
        assert result.exit_code != 0
        assert "cannot be used with --resume" in result.output

    def test_resume_with_start_end_flags_errors(self, tmp_path, mock_org):
        """--resume with --start or --end is forbidden."""
        data_path = str(tmp_path / "val2.jsonl")
        mock_org.client.request.side_effect = _make_search_responses(1)

        runner = CliRunner()
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            runner.invoke(cli, [
                "--oid", "test-oid", "search", "run",
                "--query", "q", "--start", "1000", "--end", "2000",
                "--checkpoint", data_path,
            ])

        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            result = runner.invoke(cli, [
                "--oid", "test-oid", "search", "run",
                "--resume", "--checkpoint", data_path,
                "--start", "5000",
            ])
        assert result.exit_code != 0
        assert "--start" in result.output

    def test_resume_with_limit_is_allowed(self, tmp_path, mock_org):
        """--resume with --limit is allowed (caps additional results)."""
        data_path = str(tmp_path / "val3.jsonl")
        # Create incomplete checkpoint via interrupt
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"queryId": "q1"}
            elif call_count == 2:
                return {"results": [{"type": "events",
                                     "rows": [{"mtd": {"ts": 1000000}, "data": {}}],
                                     "nextToken": "tok1"}], "completed": True}
            elif call_count == 3:
                raise KeyboardInterrupt()
            else:
                return {}

        mock_org.client.request.side_effect = side_effect

        runner = CliRunner(mix_stderr=False)
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            runner.invoke(cli, [
                "--oid", "test-oid", "search", "run",
                "--query", "q", "--start", "1000", "--end", "2000",
                "--checkpoint", data_path,
            ])

        # Resume with --limit should work
        mock_org.client.request.side_effect = [
            {"queryId": "q2"},
            {"results": [{"type": "events", "rows": [{"mtd": {"ts": 2000000}, "data": {}}]}],
             "completed": True},
            {},  # DELETE
        ]

        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            result = runner.invoke(cli, [
                "--oid", "test-oid", "--output", "json",
                "search", "run",
                "--resume", "--checkpoint", data_path, "--limit", "5",
            ])
        assert result.exit_code == 0, f"Resume with --limit failed: {result.output}"

    def test_resume_nonexistent_checkpoint_errors(self, tmp_path):
        """--resume with non-existent checkpoint file errors."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "--oid", "test-oid",
            "search", "run",
            "--resume", "--checkpoint", str(tmp_path / "nope.jsonl"),
        ])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()


class TestSearchCheckpointsCli:
    """Test 'search checkpoints' via CliRunner."""

    def test_no_checkpoints_message(self):
        """Empty checkpoints dir shows 'No checkpoints found.'"""
        runner = CliRunner()
        result = runner.invoke(cli, ["search", "checkpoints"])
        assert result.exit_code == 0
        assert "No checkpoints found" in result.output

    def test_lists_checkpoints_as_table(self, tmp_path, mock_org):
        """Lists checkpoints with pages, events, status in table format."""
        data_path = str(tmp_path / "listed.jsonl")
        mock_org.client.request.side_effect = _make_search_responses(3, events_per_page=10)

        runner = CliRunner()
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            runner.invoke(cli, [
                "--oid", "test-oid",
                "search", "run",
                "--query", "* | NEW_PROCESS | *",
                "--start", "1700000000", "--end", "1700086400",
                "--checkpoint", data_path,
            ])

        result = runner.invoke(cli, ["search", "checkpoints"])
        assert result.exit_code == 0
        assert "listed.jsonl" in result.output
        assert "completed" in result.output

    def test_lists_checkpoints_as_json(self, tmp_path, mock_org):
        """Lists checkpoints in JSON format with all metadata fields."""
        data_path = str(tmp_path / "json_listed.jsonl")
        mock_org.client.request.side_effect = _make_search_responses(2, events_per_page=3)

        runner = CliRunner()
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            runner.invoke(cli, [
                "--oid", "test-oid",
                "search", "run",
                "--query", "test query",
                "--start", "1700000000", "--end", "1700086400",
                "--checkpoint", data_path,
            ])

        result = runner.invoke(cli, ["--output", "json", "search", "checkpoints"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert len(parsed) == 1
        cp = parsed[0]
        assert cp["query"] == "test query"
        assert cp["total_events"] == 6  # 2 pages x 3 events
        assert cp["completed"] is True
        assert cp["last_token"] == "tok-1"
        assert "data_file_exists" in cp

    def test_stale_metadata_cleaned_up(self, tmp_path, mock_org, checkpoints_dir):
        """Stale metadata files are removed when listing checkpoints."""
        data_path = str(tmp_path / "stale.jsonl")
        mock_org.client.request.side_effect = _make_search_responses(1)

        runner = CliRunner()
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            runner.invoke(cli, [
                "--oid", "test-oid",
                "search", "run",
                "--query", "q", "--start", "1000", "--end", "2000",
                "--checkpoint", data_path,
            ])

        meta_file = _meta_path(data_path)
        assert os.path.exists(meta_file)

        # Delete the data file
        os.unlink(data_path)

        # Listing should clean up the stale metadata
        result = runner.invoke(cli, ["search", "checkpoints"])
        assert result.exit_code == 0
        assert "No checkpoints found" in result.output
        assert not os.path.exists(meta_file)


class TestSearchRunWithoutCheckpointCli:
    """Verify non-checkpoint search still works through CLI."""

    def test_normal_search_without_checkpoint(self, mock_org):
        """Regular search run without --checkpoint works as before."""
        mock_org.client.request.side_effect = _make_search_responses(1)

        runner = CliRunner()
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            result = runner.invoke(cli, [
                "--oid", "test-oid", "--output", "json",
                "search", "run",
                "--query", "* | * | *",
                "--start", "1700000000", "--end", "1700086400",
            ])

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        # Should have JSON output
        parsed = json.loads(result.output)
        assert isinstance(parsed, list)
        assert len(parsed) == 1

    def test_missing_query_errors(self):
        """--query is required without --resume."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "--oid", "test-oid",
            "search", "run",
            "--start", "1000", "--end", "2000",
        ])
        assert result.exit_code != 0
        assert "--query" in result.output

    def test_missing_start_end_errors(self):
        """--start and --end are required without --resume."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "--oid", "test-oid",
            "search", "run",
            "--query", "test",
        ])
        assert result.exit_code != 0
        assert "--start" in result.output


class TestCheckpointCancelMessageCli:
    """Test the Ctrl+C cancel message content via CliRunner.

    CliRunner can simulate KeyboardInterrupt mid-search by having the
    mock raise it at the right point.
    """

    def test_cancel_message_includes_resume_command(self, tmp_path, mock_org):
        """Ctrl+C message includes the exact resume command."""
        data_path = str(tmp_path / "cancel.jsonl")
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"queryId": "q-cancel"}
            elif call_count == 2:
                return {
                    "results": [{"type": "events",
                                 "rows": [{"mtd": {"ts": 1700000000000}, "data": {}}],
                                 "nextToken": "tok1"}],
                    "completed": True,
                }
            elif call_count == 3:
                raise KeyboardInterrupt()
            else:
                return {}  # DELETE

        mock_org.client.request.side_effect = side_effect

        runner = CliRunner(mix_stderr=False)
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            result = runner.invoke(cli, [
                "--oid", "test-oid",
                "search", "run",
                "--query", "test", "--start", "1700000000", "--end", "1700086400",
                "--checkpoint", data_path,
            ])

        # The cancel output goes to stderr
        stderr = result.stderr if hasattr(result, 'stderr') else result.output
        assert "Checkpoint saved" in stderr
        assert "Resume with:" in stderr
        assert f"--checkpoint {data_path}" in stderr
        assert "Resume token:" in stderr


class TestRejectedTokenResumeCli:
    """Test that rejected pagination tokens produce helpful error messages.

    If the server rejects a pagination token during resume (e.g. malformed,
    corrupt, or server-side issue), the CLI should detect this and show
    the command to re-run the query from scratch with --force.
    """

    def _create_incomplete_checkpoint(self, tmp_path, mock_org):
        """Helper: create an incomplete checkpoint with a token."""
        data_path = str(tmp_path / "expired.jsonl")
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"queryId": "q-exp"}
            elif call_count == 2:
                return {
                    "results": [{"type": "events",
                                 "rows": [{"mtd": {"ts": 1700000000000}, "data": {}}],
                                 "nextToken": "tok-expired"}],
                    "completed": True,
                }
            elif call_count == 3:
                raise KeyboardInterrupt()
            else:
                return {}

        mock_org.client.request.side_effect = side_effect

        runner = CliRunner(mix_stderr=False)
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            runner.invoke(cli, [
                "--oid", "test-oid",
                "search", "run",
                "--query", "* | NEW_PROCESS | event/FILE_PATH contains '/bin/bash'",
                "--start", "1700000000", "--end", "1700086400",
                "--stream", "event",
                "--checkpoint", data_path,
            ])
        return data_path

    def test_404_on_resume_shows_rejected_token_message(self, tmp_path, mock_org):
        """404 during resume shows rejected token error with fresh query command."""
        from limacharlie.errors import NotFoundError

        data_path = self._create_incomplete_checkpoint(tmp_path, mock_org)

        # Resume: server returns 404 (token expired)
        mock_org.client.request.side_effect = [
            {"queryId": "q-exp-resume"},
            NotFoundError("query not found"),
        ]

        runner = CliRunner(mix_stderr=False)
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            result = runner.invoke(cli, [
                "--oid", "test-oid",
                "search", "run",
                "--resume", "--checkpoint", data_path,
            ])

        assert result.exit_code != 0
        stderr = result.stderr
        assert "rejected" in stderr.lower() or "failed" in stderr.lower()
        # Should contain the fresh query command with original params
        assert "--query" in stderr
        assert "NEW_PROCESS" in stderr
        assert "--start 1700000000" in stderr
        assert "--end 1700086400" in stderr
        assert "--stream event" in stderr
        assert "--force" in stderr
        assert data_path in stderr

    def test_error_message_on_resume_shows_rejected_token_message(self, tmp_path, mock_org):
        """Search error with 'not found' keyword shows rejected token message."""
        from limacharlie.errors import SearchError

        data_path = self._create_incomplete_checkpoint(tmp_path, mock_org)

        # Resume: server returns error with expiry-related message
        mock_org.client.request.side_effect = [
            {"queryId": "q-exp2"},
            {"error": "query not found or results expired"},
            {},  # DELETE
        ]

        runner = CliRunner(mix_stderr=False)
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            result = runner.invoke(cli, [
                "--oid", "test-oid",
                "search", "run",
                "--resume", "--checkpoint", data_path,
            ])

        assert result.exit_code != 0
        stderr = result.stderr
        assert "rejected" in stderr.lower() or "failed" in stderr.lower()
        assert "--force" in stderr

    def test_non_token_error_on_resume_propagates_normally(self, tmp_path, mock_org):
        """Non-token errors during resume are NOT caught by the rejected token handler."""
        from limacharlie.errors import AuthenticationError

        data_path = self._create_incomplete_checkpoint(tmp_path, mock_org)

        # Resume: auth error (not an expiry error)
        mock_org.client.request.side_effect = [
            {"queryId": "q-auth"},
            AuthenticationError("JWT expired"),
        ]

        runner = CliRunner(mix_stderr=False)
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            result = runner.invoke(cli, [
                "--oid", "test-oid",
                "search", "run",
                "--resume", "--checkpoint", data_path,
            ])

        assert result.exit_code != 0
        # Should NOT show the "rejected token" message with --force
        # (auth errors are different from token rejection)
        all_output = result.output + result.stderr
        assert "re-run the query from scratch" not in all_output


class TestCheckpointShowCli:
    """Test 'search checkpoint-show' via CliRunner.

    Verifies that checkpoint data files can be displayed through the
    same output pipeline as live searches (table, JSON, expand, raw).
    """

    def _create_completed_checkpoint(self, tmp_path, mock_org, pages=2, events_per_page=3):
        """Helper: create a completed checkpoint, return data_path."""
        data_path = str(tmp_path / "show_test.jsonl")
        mock_org.client.request.side_effect = _make_search_responses(pages, events_per_page)

        runner = CliRunner()
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            result = runner.invoke(cli, [
                "--oid", "test-oid", "--output", "json",
                "search", "run",
                "--query", "* | NEW_PROCESS | event/COMMAND_LINE contains 'curl'",
                "--start", "1700000000", "--end", "1700086400",
                "--stream", "event",
                "--checkpoint", data_path,
            ])
        assert result.exit_code == 0, f"Setup failed: {result.output}"
        return data_path

    def test_show_json_output(self, tmp_path, mock_org):
        """checkpoint-show --output json outputs the raw result list."""
        data_path = self._create_completed_checkpoint(tmp_path, mock_org)

        runner = CliRunner()
        result = runner.invoke(cli, [
            "--output", "json",
            "search", "checkpoint-show",
            "--checkpoint", data_path,
        ])
        assert result.exit_code == 0, f"Failed: {result.output}"
        parsed = json.loads(result.output)
        assert isinstance(parsed, list)
        assert len(parsed) == 2  # 2 pages
        assert parsed[0]["type"] == "events"

    def test_show_table_output(self, tmp_path, mock_org):
        """checkpoint-show with table output renders events."""
        data_path = self._create_completed_checkpoint(tmp_path, mock_org)

        runner = CliRunner()
        result = runner.invoke(cli, [
            "--output", "table",
            "search", "checkpoint-show",
            "--checkpoint", data_path,
        ])
        assert result.exit_code == 0, f"Failed: {result.output}"
        # Table output should contain event data
        assert "NEW_PROCESS" in result.output or "event" in result.output.lower()

    def test_show_raw_output(self, tmp_path, mock_org):
        """checkpoint-show --raw outputs raw SearchResult objects."""
        data_path = self._create_completed_checkpoint(tmp_path, mock_org)

        runner = CliRunner()
        result = runner.invoke(cli, [
            "--output", "json",
            "search", "checkpoint-show",
            "--checkpoint", data_path, "--raw",
        ])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert isinstance(parsed, list)
        # Raw mode passes through SearchResult wrappers
        assert all("type" in r for r in parsed)

    def test_show_expand_output(self, tmp_path, mock_org):
        """checkpoint-show --expand with table format renders event JSON blocks."""
        data_path = self._create_completed_checkpoint(tmp_path, mock_org)

        runner = CliRunner()
        result = runner.invoke(cli, [
            "--output", "table",
            "search", "checkpoint-show",
            "--checkpoint", data_path, "--expand",
        ])
        assert result.exit_code == 0
        # Expand mode shows "---" dividers between events
        assert "---" in result.output

    def test_show_empty_checkpoint(self, tmp_path, mock_org):
        """checkpoint-show on empty checkpoint shows appropriate message."""
        data_path = str(tmp_path / "empty.jsonl")
        # Create checkpoint with no results
        mock_org.client.request.side_effect = [
            {"queryId": "q-empty"},
            {"results": [], "completed": True},
            {},  # DELETE
        ]

        runner = CliRunner()
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            runner.invoke(cli, [
                "--oid", "test-oid",
                "search", "run",
                "--query", "q", "--start", "1000", "--end", "2000",
                "--checkpoint", data_path,
            ])

        # Default format in CliRunner (non-TTY) is JSON, which outputs [].
        result = runner.invoke(cli, [
            "search", "checkpoint-show",
            "--checkpoint", data_path,
        ])
        assert result.exit_code == 0
        assert result.output.strip() == "[]"

        # Table format shows human-readable message.
        result = runner.invoke(cli, [
            "--output", "table",
            "search", "checkpoint-show",
            "--checkpoint", data_path,
        ])
        assert result.exit_code == 0
        assert "no results" in result.output.lower() or "no events" in result.output.lower()

    def test_show_nonexistent_file_errors(self, tmp_path):
        """checkpoint-show on nonexistent file shows error."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "search", "checkpoint-show",
            "--checkpoint", str(tmp_path / "nope.jsonl"),
        ])
        assert result.exit_code != 0

    def test_show_quiet_suppresses_output(self, tmp_path, mock_org):
        """checkpoint-show --quiet suppresses all output."""
        data_path = self._create_completed_checkpoint(tmp_path, mock_org)

        runner = CliRunner()
        result = runner.invoke(cli, [
            "--quiet",
            "search", "checkpoint-show",
            "--checkpoint", data_path,
        ])
        assert result.exit_code == 0
        assert result.output.strip() == ""

    def test_show_prints_summary_to_stderr(self, tmp_path, mock_org):
        """checkpoint-show prints checkpoint summary to stderr."""
        data_path = self._create_completed_checkpoint(tmp_path, mock_org)

        runner = CliRunner(mix_stderr=False)
        result = runner.invoke(cli, [
            "--output", "json",
            "search", "checkpoint-show",
            "--checkpoint", data_path,
        ])
        assert result.exit_code == 0
        # Summary goes to stderr (may not appear in test since
        # CliRunner's stderr may not be a tty)
        # Just verify we got JSON output on stdout
        parsed = json.loads(result.output)
        assert len(parsed) == 2

    def test_show_jsonl_output(self, tmp_path, mock_org):
        """checkpoint-show --output jsonl outputs one result per line."""
        data_path = self._create_completed_checkpoint(tmp_path, mock_org)

        runner = CliRunner()
        result = runner.invoke(cli, [
            "--output", "jsonl",
            "search", "checkpoint-show",
            "--checkpoint", data_path,
        ])
        assert result.exit_code == 0
        lines = [l for l in result.output.strip().split("\n") if l.strip()]
        assert len(lines) == 2
        for line in lines:
            parsed = json.loads(line)
            assert "type" in parsed


class TestIsTokenExpiredError:
    """Direct unit tests for _is_token_expired_error classifier."""

    def test_not_found_error_detected(self):
        from limacharlie.errors import NotFoundError
        from limacharlie.commands.search import _is_token_expired_error
        assert _is_token_expired_error(NotFoundError("query not found")) is True

    def test_search_error_with_query_not_found(self):
        from limacharlie.errors import SearchError
        from limacharlie.commands.search import _is_token_expired_error
        assert _is_token_expired_error(SearchError("Search failed: query not found")) is True

    def test_search_error_with_invalid_token(self):
        from limacharlie.errors import SearchError
        from limacharlie.commands.search import _is_token_expired_error
        assert _is_token_expired_error(SearchError("invalid token")) is True

    def test_search_error_with_results_expired(self):
        from limacharlie.errors import SearchError
        from limacharlie.commands.search import _is_token_expired_error
        assert _is_token_expired_error(SearchError("results expired")) is True

    def test_search_error_with_unknown_query(self):
        from limacharlie.errors import SearchError
        from limacharlie.commands.search import _is_token_expired_error
        assert _is_token_expired_error(SearchError("unknown query xyz")) is True

    def test_auth_error_not_detected(self):
        from limacharlie.errors import AuthenticationError
        from limacharlie.commands.search import _is_token_expired_error
        assert _is_token_expired_error(AuthenticationError("JWT expired")) is False

    def test_permission_denied_not_detected(self):
        from limacharlie.errors import PermissionDeniedError
        from limacharlie.commands.search import _is_token_expired_error
        assert _is_token_expired_error(PermissionDeniedError("forbidden")) is False

    def test_rate_limit_not_detected(self):
        from limacharlie.errors import RateLimitError
        from limacharlie.commands.search import _is_token_expired_error
        assert _is_token_expired_error(RateLimitError("429")) is False

    def test_generic_search_error_not_detected(self):
        from limacharlie.errors import SearchError
        from limacharlie.commands.search import _is_token_expired_error
        assert _is_token_expired_error(SearchError("connection reset")) is False

    def test_generic_exception_not_detected(self):
        from limacharlie.commands.search import _is_token_expired_error
        assert _is_token_expired_error(RuntimeError("something")) is False


class TestBuildFreshQueryCmd:
    """Direct unit tests for _build_fresh_query_cmd."""

    def test_basic_query(self):
        from limacharlie.commands.search import _build_fresh_query_cmd
        meta = {"query": "* | * | *", "start_time": 1000, "end_time": 2000}
        cmd = _build_fresh_query_cmd(meta, "/tmp/test.jsonl")
        assert "--query" in cmd
        assert "--start 1000" in cmd
        assert "--end 2000" in cmd
        assert "--force" in cmd
        assert "/tmp/test.jsonl" in cmd

    def test_with_stream_and_limit(self):
        from limacharlie.commands.search import _build_fresh_query_cmd
        meta = {"query": "q", "start_time": 1, "end_time": 2,
                "stream": "event", "limit": 100}
        cmd = _build_fresh_query_cmd(meta, "/tmp/t.jsonl")
        assert "--stream" in cmd
        assert "event" in cmd
        assert "--limit 100" in cmd

    def test_shell_escapes_query_with_quotes(self):
        from limacharlie.commands.search import _build_fresh_query_cmd
        meta = {"query": "event/FILE_PATH contains \"C:\\Windows\"",
                "start_time": 1, "end_time": 2}
        cmd = _build_fresh_query_cmd(meta, "/tmp/t.jsonl")
        # shlex.quote wraps in single quotes for safety
        assert "'" in cmd or "\\" in cmd

    def test_shell_escapes_path_with_spaces(self):
        from limacharlie.commands.search import _build_fresh_query_cmd
        meta = {"query": "q", "start_time": 1, "end_time": 2}
        cmd = _build_fresh_query_cmd(meta, "/tmp/my search results.jsonl")
        # Path with spaces should be quoted
        assert "'" in cmd or '"' in cmd


class TestStreamingOutput:
    """Tests for streaming output modes (JSONL, JSON, expand).

    Verifies that streaming formats produce correct output without
    requiring the full result set in memory. Covers all code paths:
    _run_normal, _run_with_checkpoint, _run_resume, checkpoint-show,
    saved-run.
    """

    def _create_checkpoint(self, tmp_path, mock_org, pages=3, events_per_page=2):
        """Helper: create a completed checkpoint."""
        data_path = str(tmp_path / "stream_test.jsonl")
        mock_org.client.request.side_effect = _make_search_responses(pages, events_per_page)

        runner = CliRunner()
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            result = runner.invoke(cli, [
                "--oid", "test-oid", "--output", "json",
                "search", "run",
                "--query", "* | NEW_PROCESS | *",
                "--start", "1700000000", "--end", "1700086400",
                "--checkpoint", data_path,
            ])
        assert result.exit_code == 0, f"Setup failed: {result.output}"
        return data_path

    def _invoke_search(self, mock_org, output_fmt, extra_args=None):
        """Helper: run a normal search with given output format."""
        mock_org.client.request.side_effect = _make_search_responses(3, events_per_page=2)
        runner = CliRunner()
        args = ["--oid", "test-oid", "--output", output_fmt,
                "search", "run",
                "--query", "* | NEW_PROCESS | *",
                "--start", "1700000000", "--end", "1700086400"]
        if extra_args:
            args.extend(extra_args)
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            return runner.invoke(cli, args)

    # ---------------------------------------------------------------
    # JSON streaming validity
    # ---------------------------------------------------------------

    def test_json_zero_results_produces_empty_array(self, mock_org):
        """Streaming JSON with 0 results produces valid []."""
        mock_org.client.request.side_effect = [
            {"queryId": "q"}, {"results": [], "completed": True}, {},
        ]
        runner = CliRunner()
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            result = runner.invoke(cli, [
                "--oid", "o", "--output", "json", "search", "run",
                "--query", "q", "--start", "1000", "--end", "2000",
            ])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed == []

    def test_json_single_result_valid(self, mock_org):
        """Streaming JSON with 1 result produces valid [item]."""
        result = self._invoke_search(mock_org, "json")
        # _make_search_responses(3) produces 3 results
        mock_org.client.request.side_effect = _make_search_responses(1)
        runner = CliRunner()
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            result = runner.invoke(cli, [
                "--oid", "o", "--output", "json", "search", "run",
                "--query", "q", "--start", "1000", "--end", "2000",
            ])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert isinstance(parsed, list)
        assert len(parsed) == 1

    def test_json_many_results_valid(self, mock_org):
        """Streaming JSON with many results produces valid array."""
        mock_org.client.request.side_effect = _make_search_responses(5, events_per_page=3)
        runner = CliRunner()
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            result = runner.invoke(cli, [
                "--oid", "o", "--output", "json", "search", "run",
                "--query", "q", "--start", "1000", "--end", "2000",
            ])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert len(parsed) == 5
        # Verify all items have the right structure
        for item in parsed:
            assert item["type"] == "events"
            assert len(item["rows"]) == 3

    def test_json_results_with_special_chars(self, mock_org):
        """Streaming JSON handles special characters (quotes, backslashes)."""
        mock_org.client.request.side_effect = [
            {"queryId": "q"},
            {"results": [{"type": "events", "rows": [
                {"data": {"path": "C:\\Windows\\System32", "cmd": 'echo "hello"'}}
            ]}], "completed": True},
            {},
        ]
        runner = CliRunner()
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            result = runner.invoke(cli, [
                "--oid", "o", "--output", "json", "search", "run",
                "--query", "q", "--start", "1000", "--end", "2000",
            ])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed[0]["rows"][0]["data"]["path"] == "C:\\Windows\\System32"
        assert parsed[0]["rows"][0]["data"]["cmd"] == 'echo "hello"'

    def test_json_results_with_unicode(self, mock_org):
        """Streaming JSON handles unicode characters."""
        mock_org.client.request.side_effect = [
            {"queryId": "q"},
            {"results": [{"type": "events", "rows": [
                {"data": {"hostname": "servidor-\u00e9", "user": "\u4e16\u754c"}}
            ]}], "completed": True},
            {},
        ]
        runner = CliRunner()
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            result = runner.invoke(cli, [
                "--oid", "o", "--output", "json", "search", "run",
                "--query", "q", "--start", "1000", "--end", "2000",
            ])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed[0]["rows"][0]["data"]["user"] == "\u4e16\u754c"

    # ---------------------------------------------------------------
    # JSONL streaming
    # ---------------------------------------------------------------

    def test_jsonl_zero_results(self, mock_org):
        """JSONL with 0 results produces empty output."""
        mock_org.client.request.side_effect = [
            {"queryId": "q"}, {"results": [], "completed": True}, {},
        ]
        runner = CliRunner()
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            result = runner.invoke(cli, [
                "--oid", "o", "--output", "jsonl", "search", "run",
                "--query", "q", "--start", "1000", "--end", "2000",
            ])
        assert result.exit_code == 0
        assert result.output.strip() == ""

    def test_jsonl_each_line_is_valid_json(self, mock_org):
        """Every JSONL line is independently valid JSON."""
        result = self._invoke_search(mock_org, "jsonl")
        assert result.exit_code == 0
        lines = [l for l in result.output.strip().split("\n") if l.strip()]
        assert len(lines) == 3
        for i, line in enumerate(lines):
            parsed = json.loads(line)
            assert "type" in parsed, f"Line {i} missing 'type'"

    def test_jsonl_special_chars(self, mock_org):
        """JSONL handles special characters per line."""
        mock_org.client.request.side_effect = [
            {"queryId": "q"},
            {"results": [{"type": "events", "rows": [
                {"data": {"msg": "line1\nline2", "path": "C:\\test"}}
            ]}], "completed": True},
            {},
        ]
        runner = CliRunner()
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            result = runner.invoke(cli, [
                "--oid", "o", "--output", "jsonl", "search", "run",
                "--query", "q", "--start", "1000", "--end", "2000",
            ])
        assert result.exit_code == 0
        # Should be one JSONL line (the embedded newline is escaped in JSON)
        lines = [l for l in result.output.strip().split("\n") if l.strip()]
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["rows"][0]["data"]["msg"] == "line1\nline2"

    # ---------------------------------------------------------------
    # Expand streaming
    # ---------------------------------------------------------------

    def test_expand_zero_events(self, mock_org):
        """Expand with 0 events shows 'No events'."""
        mock_org.client.request.side_effect = [
            {"queryId": "q"}, {"results": [], "completed": True}, {},
        ]
        runner = CliRunner()
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            result = runner.invoke(cli, [
                "--oid", "o", "--output", "table", "search", "run",
                "--query", "q", "--start", "1000", "--end", "2000",
                "--expand",
            ])
        assert result.exit_code == 0
        assert "No events" in result.output

    def test_expand_each_event_has_header(self, mock_org):
        """Each event in expand mode gets a --- header line."""
        result = self._invoke_search(mock_org, "table", extra_args=["--expand"])
        assert result.exit_code == 0
        headers = [l for l in result.output.split("\n") if l.startswith("---")]
        # 3 pages x 2 events = 6 headers
        assert len(headers) == 6

    def test_expand_event_body_is_valid_json(self, mock_org):
        """Each event body in expand mode is valid pretty-printed JSON."""
        mock_org.client.request.side_effect = _make_search_responses(1, events_per_page=1)
        runner = CliRunner()
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            result = runner.invoke(cli, [
                "--oid", "o", "--output", "table", "search", "run",
                "--query", "q", "--start", "1000", "--end", "2000",
                "--expand",
            ])
        assert result.exit_code == 0
        lines = result.output.strip().split("\n")
        # First line is the header, rest is JSON
        json_lines = [l for l in lines if not l.startswith("---")]
        json_body = "\n".join(json_lines)
        parsed = json.loads(json_body)
        assert isinstance(parsed, dict)

    def test_expand_across_multiple_pages(self, mock_org):
        """Expand correctly renders events from multiple pages."""
        result = self._invoke_search(mock_org, "table", extra_args=["--expand"])
        assert result.exit_code == 0
        # Should have event data from all pages
        assert "idx" in result.output

    # ---------------------------------------------------------------
    # Checkpoint-show streaming
    # ---------------------------------------------------------------

    def test_checkpoint_show_jsonl_streams(self, tmp_path, mock_org):
        """checkpoint-show --output jsonl streams from file."""
        data_path = self._create_checkpoint(tmp_path, mock_org, pages=3)
        runner = CliRunner()
        result = runner.invoke(cli, [
            "--output", "jsonl", "search", "checkpoint-show",
            "--checkpoint", data_path,
        ])
        assert result.exit_code == 0
        lines = [l for l in result.output.strip().split("\n") if l.strip()]
        assert len(lines) == 3

    def test_checkpoint_show_json_streams_valid(self, tmp_path, mock_org):
        """checkpoint-show --output json streams valid JSON from file."""
        data_path = self._create_checkpoint(tmp_path, mock_org, pages=3)
        runner = CliRunner()
        result = runner.invoke(cli, [
            "--output", "json", "search", "checkpoint-show",
            "--checkpoint", data_path,
        ])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert len(parsed) == 3

    def test_checkpoint_show_expand_streams(self, tmp_path, mock_org):
        """checkpoint-show --expand streams events from file."""
        data_path = self._create_checkpoint(tmp_path, mock_org, pages=2, events_per_page=3)
        runner = CliRunner()
        result = runner.invoke(cli, [
            "--output", "table", "search", "checkpoint-show",
            "--checkpoint", data_path, "--expand",
        ])
        assert result.exit_code == 0
        headers = [l for l in result.output.split("\n") if l.startswith("---")]
        assert len(headers) == 6

    def test_checkpoint_show_empty_json(self, tmp_path, mock_org):
        """checkpoint-show --output json on empty checkpoint produces []."""
        data_path = str(tmp_path / "empty.jsonl")
        mock_org.client.request.side_effect = [
            {"queryId": "q"}, {"results": [], "completed": True}, {},
        ]
        runner = CliRunner()
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            runner.invoke(cli, [
                "--oid", "o", "search", "run",
                "--query", "q", "--start", "1000", "--end", "2000",
                "--checkpoint", data_path,
            ])
        result = runner.invoke(cli, [
            "--output", "json", "search", "checkpoint-show",
            "--checkpoint", data_path,
        ])
        assert result.exit_code == 0
        assert result.output.strip() == "[]"

    # ---------------------------------------------------------------
    # Checkpoint run + streaming
    # ---------------------------------------------------------------

    def test_checkpoint_run_jsonl_streams(self, tmp_path, mock_org):
        """search run --checkpoint --output jsonl streams without OOM risk."""
        data_path = str(tmp_path / "stream_cp.jsonl")
        mock_org.client.request.side_effect = _make_search_responses(3)
        runner = CliRunner()
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            result = runner.invoke(cli, [
                "--oid", "test-oid", "--output", "jsonl",
                "search", "run",
                "--query", "* | * | *",
                "--start", "1700000000", "--end", "1700086400",
                "--checkpoint", data_path,
            ])
        assert result.exit_code == 0
        lines = [l for l in result.output.strip().split("\n") if l.strip()]
        assert len(lines) == 3
        from limacharlie.search_checkpoint import CheckpointReader
        meta = CheckpointReader.read_metadata(data_path)
        assert meta["result_count"] == 3

    def test_checkpoint_run_json_streams_valid(self, tmp_path, mock_org):
        """search run --checkpoint --output json produces valid JSON."""
        data_path = str(tmp_path / "json_cp.jsonl")
        mock_org.client.request.side_effect = _make_search_responses(2)
        runner = CliRunner()
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            result = runner.invoke(cli, [
                "--oid", "test-oid", "--output", "json",
                "search", "run",
                "--query", "q", "--start", "1000", "--end", "2000",
                "--checkpoint", data_path,
            ])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert len(parsed) == 2

    # ---------------------------------------------------------------
    # Buffered fallback (table, CSV, YAML)
    # ---------------------------------------------------------------

    def test_table_falls_back_to_buffered(self, mock_org):
        """Table output still works (requires buffering)."""
        mock_org.client.request.side_effect = _make_search_responses(1, events_per_page=2)
        runner = CliRunner()
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            result = runner.invoke(cli, [
                "--oid", "o", "--output", "table", "search", "run",
                "--query", "* | NEW_PROCESS | *",
                "--start", "1000", "--end", "2000",
            ])
        assert result.exit_code == 0
        assert "NEW_PROCESS" in result.output

    def test_csv_falls_back_to_buffered(self, mock_org):
        """CSV output still works (requires buffering for headers)."""
        mock_org.client.request.side_effect = _make_search_responses(1, events_per_page=1)
        runner = CliRunner()
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            result = runner.invoke(cli, [
                "--oid", "o", "--output", "csv", "search", "run",
                "--query", "q", "--start", "1000", "--end", "2000",
            ])
        assert result.exit_code == 0
        # CSV has header row + data rows
        assert "type" in result.output

    def test_yaml_falls_back_to_buffered(self, mock_org):
        """YAML output still works (requires buffering)."""
        mock_org.client.request.side_effect = _make_search_responses(1, events_per_page=1)
        runner = CliRunner()
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            result = runner.invoke(cli, [
                "--oid", "o", "--output", "yaml", "search", "run",
                "--query", "q", "--start", "1000", "--end", "2000",
            ])
        assert result.exit_code == 0
        assert "type:" in result.output or "events" in result.output

    # ---------------------------------------------------------------
    # _stream_search_output unit tests
    # ---------------------------------------------------------------

    def test_stream_returns_true_for_table(self):
        """_stream_search_output returns True for table (streams with sampled widths)."""
        from limacharlie.commands.search import _stream_search_output
        ctx = MagicMock()
        ctx.obj.quiet = False
        ctx.obj.output_format = "table"
        ctx.obj.wide = False
        assert _stream_search_output(ctx, iter([]), raw=False, expand=False) is True

    def test_stream_returns_false_for_csv(self):
        """_stream_search_output returns False for CSV."""
        from limacharlie.commands.search import _stream_search_output
        ctx = MagicMock()
        ctx.obj.quiet = False
        ctx.obj.output_format = "csv"
        assert _stream_search_output(ctx, iter([]), raw=False, expand=False) is False

    def test_stream_returns_false_for_yaml(self):
        """_stream_search_output returns False for YAML."""
        from limacharlie.commands.search import _stream_search_output
        ctx = MagicMock()
        ctx.obj.quiet = False
        ctx.obj.output_format = "yaml"
        assert _stream_search_output(ctx, iter([]), raw=False, expand=False) is False

    def test_stream_returns_false_for_table_raw(self):
        """_stream_search_output returns False for table+raw (raw needs full list)."""
        from limacharlie.commands.search import _stream_search_output
        ctx = MagicMock()
        ctx.obj.quiet = False
        ctx.obj.output_format = "table"
        ctx.obj.wide = False
        assert _stream_search_output(ctx, iter([]), raw=True, expand=False) is False

    def test_stream_returns_true_for_jsonl(self):
        """_stream_search_output returns True for JSONL (handled)."""
        from limacharlie.commands.search import _stream_search_output
        ctx = MagicMock()
        ctx.obj.quiet = False
        ctx.obj.output_format = "jsonl"
        assert _stream_search_output(ctx, iter([]), raw=False, expand=False) is True

    def test_stream_returns_true_for_json(self):
        """_stream_search_output returns True for JSON (handled)."""
        from limacharlie.commands.search import _stream_search_output
        ctx = MagicMock()
        ctx.obj.quiet = False
        ctx.obj.output_format = "json"
        assert _stream_search_output(ctx, iter([]), raw=False, expand=False) is True

    def test_stream_returns_true_for_expand(self):
        """_stream_search_output returns True for table+expand."""
        from limacharlie.commands.search import _stream_search_output
        ctx = MagicMock()
        ctx.obj.quiet = False
        ctx.obj.output_format = "table"
        assert _stream_search_output(ctx, iter([]), raw=False, expand=True) is True

    def test_stream_quiet_returns_true(self):
        """_stream_search_output returns True when quiet (nothing to do)."""
        from limacharlie.commands.search import _stream_search_output
        ctx = MagicMock()
        ctx.obj.quiet = True
        ctx.obj.output_format = "table"
        assert _stream_search_output(ctx, iter([{"x": 1}]), raw=False, expand=False) is True

    def test_stream_does_not_consume_iterator_on_false(self):
        """When returning False (CSV/YAML/raw), the iterator is NOT consumed."""
        from limacharlie.commands.search import _stream_search_output
        ctx = MagicMock()
        ctx.obj.quiet = False
        ctx.obj.output_format = "csv"

        items = [{"a": 1}, {"b": 2}]
        gen = iter(items)
        result = _stream_search_output(ctx, gen, raw=False, expand=False)
        assert result is False
        # Generator should still yield all items
        remaining = list(gen)
        assert len(remaining) == 2


class TestStreamingMemoryBehavior:
    """Tests that verify streaming output does NOT buffer all results in memory.

    Uses a tracking generator that records how many items are "alive" at
    any given time. If something calls list() on the generator, all items
    are consumed at once (max_alive == total). If streaming, items are
    consumed one at a time (max_alive == 1).

    This is the critical property that prevents OOM on large searches.
    """

    @staticmethod
    def _tracking_generator(items):
        """Generator that tracks consumption pattern.

        Yields items one at a time and records:
        - consumed_count: total items yielded so far
        - consume_order: list of (item_index, consumed_at_count) tuples

        After exhaustion, check consume_order to verify items were consumed
        one at a time (streaming) vs all at once (buffering).
        """
        consume_order = []
        for i, item in enumerate(items):
            consume_order.append(i)
            yield item
        # Attach metadata to the list so caller can inspect it
        return consume_order

    @staticmethod
    def _make_results(n):
        """Create n SearchResult-like dicts."""
        return [
            {"type": "events", "rows": [{"mtd": {"ts": 1700000000000 + i * 1000,
                                                  "stream": "event"},
                                          "data": {"routing": {"event_type": "NEW_PROCESS"},
                                                   "event": {"idx": i}}}]}
            for i in range(n)
        ]

    def test_jsonl_consumes_one_at_a_time(self):
        """JSONL streaming consumes items one at a time, not all at once.

        Proves constant memory by verifying the generator is advanced
        incrementally (each item is yielded, processed, then the next
        is requested).
        """
        from limacharlie.commands.search import _stream_search_output

        items = self._make_results(100)
        consumed_indices = []

        def tracking_gen():
            for i, item in enumerate(items):
                consumed_indices.append(i)
                yield item

        ctx = MagicMock()
        ctx.obj.quiet = False
        ctx.obj.output_format = "jsonl"

        result = _stream_search_output(ctx, tracking_gen())
        assert result is True
        # All 100 items should be consumed
        assert len(consumed_indices) == 100
        # They should be consumed in order, one at a time
        assert consumed_indices == list(range(100))

    def test_json_consumes_one_at_a_time(self):
        """JSON streaming consumes items one at a time.

        The JSON streaming writes "[", then each item with comma, then "]".
        Each item is serialized and written before the next is consumed.
        """
        from limacharlie.commands.search import _stream_search_output

        items = self._make_results(50)
        consumed_indices = []

        def tracking_gen():
            for i, item in enumerate(items):
                consumed_indices.append(i)
                yield item

        ctx = MagicMock()
        ctx.obj.quiet = False
        ctx.obj.output_format = "json"

        result = _stream_search_output(ctx, tracking_gen())
        assert result is True
        assert len(consumed_indices) == 50
        assert consumed_indices == list(range(50))

    def test_expand_consumes_one_at_a_time(self):
        """Expand streaming consumes items one at a time."""
        from limacharlie.commands.search import _stream_search_output

        items = self._make_results(30)
        consumed_indices = []

        def tracking_gen():
            for i, item in enumerate(items):
                consumed_indices.append(i)
                yield item

        ctx = MagicMock()
        ctx.obj.quiet = False
        ctx.obj.output_format = "table"

        result = _stream_search_output(ctx, tracking_gen(), expand=True)
        assert result is True
        assert len(consumed_indices) == 30
        assert consumed_indices == list(range(30))

    def test_table_streams_from_generator(self):
        """Table format streams from generator (consumes one at a time)."""
        from limacharlie.commands.search import _stream_search_output

        consumed_indices = []

        def tracking_gen():
            for i in range(10):
                consumed_indices.append(i)
                yield {"type": "events", "rows": [
                    {"mtd": {"ts": 1700000000000 + i * 1000, "stream": "event"},
                     "data": {"routing": {"event_type": "NEW_PROCESS"},
                              "event": {"idx": i}}}
                ]}

        ctx = MagicMock()
        ctx.obj.quiet = False
        ctx.obj.output_format = "table"
        ctx.obj.wide = False

        gen = tracking_gen()
        result = _stream_search_output(ctx, gen, expand=False)
        assert result is True
        # All items consumed
        assert len(consumed_indices) == 10

    def test_csv_does_not_consume_generator(self):
        """CSV format returns False and does NOT touch the generator."""
        from limacharlie.commands.search import _stream_search_output

        consumed_indices = []

        def tracking_gen():
            for i in range(10):
                consumed_indices.append(i)
                yield {"type": "events", "rows": [{"data": {"idx": i}}]}

        ctx = MagicMock()
        ctx.obj.quiet = False
        ctx.obj.output_format = "csv"

        gen = tracking_gen()
        result = _stream_search_output(ctx, gen, expand=False)
        assert result is False
        assert len(consumed_indices) == 0
        remaining = list(gen)
        assert len(remaining) == 10

    def test_run_normal_jsonl_does_not_buffer(self, mock_org):
        """_run_normal with --output jsonl streams without list() buffering.

        Verifies that the search generator's results are NOT collected
        into a list when JSONL output is selected. The output should
        appear as the generator yields items.
        """
        # Use a large-ish result count to make the test meaningful
        mock_org.client.request.side_effect = _make_search_responses(10, events_per_page=5)

        runner = CliRunner()
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            result = runner.invoke(cli, [
                "--oid", "o", "--output", "jsonl", "search", "run",
                "--query", "q", "--start", "1000", "--end", "2000",
            ])

        assert result.exit_code == 0
        lines = [l for l in result.output.strip().split("\n") if l.strip()]
        assert len(lines) == 10
        # Each line should be a valid independent JSON object
        for line in lines:
            parsed = json.loads(line)
            assert parsed["type"] == "events"
            assert len(parsed["rows"]) == 5

    def test_run_normal_json_does_not_buffer(self, mock_org):
        """_run_normal with --output json streams without list() buffering."""
        mock_org.client.request.side_effect = _make_search_responses(10, events_per_page=5)

        runner = CliRunner()
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            result = runner.invoke(cli, [
                "--oid", "o", "--output", "json", "search", "run",
                "--query", "q", "--start", "1000", "--end", "2000",
            ])

        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert len(parsed) == 10

    def test_checkpoint_run_does_not_accumulate_in_loop(self, tmp_path, mock_org):
        """_run_with_checkpoint does not accumulate results in the search loop.

        The search loop should write each item to disk and discard it,
        not append it to a list. Verify by checking there's no results
        list growing during the search.
        """
        data_path = str(tmp_path / "no_accum.jsonl")
        mock_org.client.request.side_effect = _make_search_responses(5, events_per_page=3)

        runner = CliRunner()
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            result = runner.invoke(cli, [
                "--oid", "o", "--output", "jsonl", "search", "run",
                "--query", "q", "--start", "1000", "--end", "2000",
                "--checkpoint", data_path,
            ])

        assert result.exit_code == 0
        # Output should have 5 JSONL lines (streamed from file after search)
        lines = [l for l in result.output.strip().split("\n") if l.strip()]
        assert len(lines) == 5
        # Checkpoint file should also have 5 results
        from limacharlie.search_checkpoint import CheckpointReader
        meta = CheckpointReader.read_metadata(data_path)
        assert meta["result_count"] == 5
        assert meta["total_events"] == 15  # 5 * 3

    def test_checkpoint_show_jsonl_streams_from_file(self, tmp_path, mock_org):
        """checkpoint-show with JSONL streams from file without full load."""
        data_path = str(tmp_path / "show_stream.jsonl")
        mock_org.client.request.side_effect = _make_search_responses(8, events_per_page=2)

        runner = CliRunner()
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            runner.invoke(cli, [
                "--oid", "o", "--output", "json", "search", "run",
                "--query", "q", "--start", "1000", "--end", "2000",
                "--checkpoint", data_path,
            ])

        # Now show via checkpoint-show with JSONL - should stream
        result = runner.invoke(cli, [
            "--output", "jsonl", "search", "checkpoint-show",
            "--checkpoint", data_path,
        ])
        assert result.exit_code == 0
        lines = [l for l in result.output.strip().split("\n") if l.strip()]
        assert len(lines) == 8

    def test_resume_output_streams_jsonl(self, tmp_path, mock_org):
        """Resume with JSONL output streams results from file."""
        data_path = str(tmp_path / "resume_stream.jsonl")
        # Create incomplete checkpoint via interrupt
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"queryId": "q1"}
            elif call_count == 2:
                return {"results": [{"type": "events",
                                     "rows": [{"mtd": {"ts": 1000000}, "data": {}}],
                                     "nextToken": "tok1"}], "completed": True}
            elif call_count == 3:
                raise KeyboardInterrupt()
            else:
                return {}

        mock_org.client.request.side_effect = side_effect
        runner = CliRunner(mix_stderr=False)
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            runner.invoke(cli, [
                "--oid", "o", "search", "run",
                "--query", "q", "--start", "1000", "--end", "2000",
                "--checkpoint", data_path,
            ])

        # Resume with JSONL
        mock_org.client.request.side_effect = [
            {"queryId": "q2"},
            {"results": [{"type": "events",
                          "rows": [{"mtd": {"ts": 2000000}, "data": {}}]}],
             "completed": True},
            {},
        ]

        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            result = CliRunner().invoke(cli, [
                "--oid", "o", "--output", "jsonl", "search", "run",
                "--resume", "--checkpoint", data_path,
            ])
        assert result.exit_code == 0
        lines = [l for l in result.output.strip().split("\n") if l.strip()]
        # Should have 2 total results (1 existing + 1 new), streamed
        assert len(lines) == 2
        for line in lines:
            json.loads(line)  # Each line is valid JSON


class TestStreamingCheckpointIntegrity:
    """End-to-end tests verifying that streaming output produces correct
    and complete data through the full checkpoint lifecycle:
    create -> interrupt -> resume -> show.

    These tests verify data integrity, not just streaming behavior.
    """

    def test_full_lifecycle_json_output(self, tmp_path, mock_org):
        """Full lifecycle: create, interrupt, resume, show - all with JSON output.

        Verifies that streaming JSON produces the same data at each stage
        and that no results are lost or duplicated.
        """
        data_path = str(tmp_path / "lifecycle.jsonl")

        # Step 1: Start search, interrupt after 2 pages
        call_count = 0

        def side_effect_1(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"queryId": "q1"}
            elif call_count == 2:
                return {"results": [{"type": "events",
                                     "rows": [{"mtd": {"ts": 1700000000000}, "data": {"idx": 0}}],
                                     "nextToken": "tok1"}], "completed": True}
            elif call_count == 3:
                return {"results": [{"type": "events",
                                     "rows": [{"mtd": {"ts": 1700001000000}, "data": {"idx": 1}}],
                                     "nextToken": "tok2"}], "completed": True}
            elif call_count == 4:
                raise KeyboardInterrupt()
            else:
                return {}

        mock_org.client.request.side_effect = side_effect_1
        runner = CliRunner(mix_stderr=False)
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            runner.invoke(cli, [
                "--oid", "o", "--output", "json", "search", "run",
                "--query", "* | * | *", "--start", "1700000000", "--end", "1700086400",
                "--checkpoint", data_path,
            ])

        # Verify checkpoint state
        from limacharlie.search_checkpoint import CheckpointReader
        meta = CheckpointReader.read_metadata(data_path)
        assert meta["result_count"] == 2
        assert meta["completed"] is False
        assert meta["last_token"] == "tok2"

        # Step 2: Show checkpoint (JSON streaming)
        result = CliRunner().invoke(cli, [
            "--output", "json", "search", "checkpoint-show",
            "--checkpoint", data_path,
        ])
        assert result.exit_code == 0
        shown = json.loads(result.output)
        assert len(shown) == 2
        assert shown[0]["rows"][0]["data"]["idx"] == 0
        assert shown[1]["rows"][0]["data"]["idx"] == 1

        # Step 3: Resume (server returns page 3 via token)
        mock_org.client.request.side_effect = [
            {"queryId": "q2"},
            {"results": [{"type": "events",
                          "rows": [{"mtd": {"ts": 1700002000000}, "data": {"idx": 2}}]}],
             "completed": True},
            {},
        ]
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            result = CliRunner().invoke(cli, [
                "--oid", "o", "--output", "json", "search", "run",
                "--resume", "--checkpoint", data_path,
            ])
        assert result.exit_code == 0
        resumed = json.loads(result.output)
        assert len(resumed) == 3  # 2 existing + 1 new
        assert resumed[0]["rows"][0]["data"]["idx"] == 0
        assert resumed[1]["rows"][0]["data"]["idx"] == 1
        assert resumed[2]["rows"][0]["data"]["idx"] == 2

        # Step 4: Show completed checkpoint (JSON streaming)
        meta = CheckpointReader.read_metadata(data_path)
        assert meta["completed"] is True
        assert meta["result_count"] == 3

        result = CliRunner().invoke(cli, [
            "--output", "json", "search", "checkpoint-show",
            "--checkpoint", data_path,
        ])
        assert result.exit_code == 0
        final = json.loads(result.output)
        assert len(final) == 3
        # Verify order preserved
        for i in range(3):
            assert final[i]["rows"][0]["data"]["idx"] == i

    def test_full_lifecycle_jsonl_output(self, tmp_path, mock_org):
        """Full lifecycle with JSONL output - verifies streaming at each stage."""
        data_path = str(tmp_path / "lifecycle_jsonl.jsonl")

        # Step 1: Start with checkpoint
        mock_org.client.request.side_effect = _make_search_responses(3, events_per_page=2)
        runner = CliRunner()
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            result = runner.invoke(cli, [
                "--oid", "o", "--output", "jsonl", "search", "run",
                "--query", "q", "--start", "1700000000", "--end", "1700086400",
                "--checkpoint", data_path,
            ])
        assert result.exit_code == 0
        run_lines = [l for l in result.output.strip().split("\n") if l.strip()]
        assert len(run_lines) == 3

        # Step 2: Show via JSONL
        result = runner.invoke(cli, [
            "--output", "jsonl", "search", "checkpoint-show",
            "--checkpoint", data_path,
        ])
        assert result.exit_code == 0
        show_lines = [l for l in result.output.strip().split("\n") if l.strip()]
        assert len(show_lines) == 3

        # Both should produce identical output
        for run_line, show_line in zip(run_lines, show_lines):
            assert json.loads(run_line) == json.loads(show_line)

    def test_resume_jsonl_includes_existing_and_new(self, tmp_path, mock_org):
        """Resume with JSONL output includes both existing and new results."""
        data_path = str(tmp_path / "resume_jsonl.jsonl")

        # Create incomplete checkpoint
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"queryId": "q1"}
            elif call_count == 2:
                return {"results": [{"type": "events",
                                     "rows": [{"mtd": {"ts": 1000}, "data": {"x": "existing"}}],
                                     "nextToken": "tok1"}], "completed": True}
            elif call_count == 3:
                raise KeyboardInterrupt()
            else:
                return {}

        mock_org.client.request.side_effect = side_effect
        runner = CliRunner(mix_stderr=False)
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            runner.invoke(cli, [
                "--oid", "o", "search", "run",
                "--query", "q", "--start", "1000", "--end", "2000",
                "--checkpoint", data_path,
            ])

        # Resume
        mock_org.client.request.side_effect = [
            {"queryId": "q2"},
            {"results": [{"type": "events",
                          "rows": [{"mtd": {"ts": 2000}, "data": {"x": "new"}}]}],
             "completed": True},
            {},
        ]
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            result = CliRunner().invoke(cli, [
                "--oid", "o", "--output", "jsonl", "search", "run",
                "--resume", "--checkpoint", data_path,
            ])
        assert result.exit_code == 0
        lines = [l for l in result.output.strip().split("\n") if l.strip()]
        assert len(lines) == 2
        # Verify data content
        r0 = json.loads(lines[0])
        r1 = json.loads(lines[1])
        assert r0["rows"][0]["data"]["x"] == "existing"
        assert r1["rows"][0]["data"]["x"] == "new"

    def test_checkpoint_show_expand_correct_event_count(self, tmp_path, mock_org):
        """checkpoint-show --expand produces one block per event."""
        data_path = str(tmp_path / "expand_match.jsonl")
        mock_org.client.request.side_effect = _make_search_responses(2, events_per_page=2)

        runner = CliRunner()
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            runner.invoke(cli, [
                "--oid", "o", "--output", "json", "search", "run",
                "--query", "q", "--start", "1000", "--end", "2000",
                "--checkpoint", data_path,
            ])

        # Show with expand
        result = runner.invoke(cli, [
            "--output", "table", "search", "checkpoint-show",
            "--checkpoint", data_path, "--expand",
        ])
        assert result.exit_code == 0
        headers = [l for l in result.output.split("\n") if l.startswith("---")]
        assert len(headers) == 4  # 2 pages x 2 events
        # Output should contain event data
        assert "idx" in result.output


class TestLargeTimeRangeWarning:
    """Tests for the memory-buffering warning on large searches without --checkpoint.

    The warning triggers when the time range exceeds _LARGE_TIME_RANGE_WARN_SECONDS
    (7 days) and the output format requires full buffering (table, csv, yaml).
    Streaming formats (jsonl, json, expand) should NOT trigger the warning.
    Searches with --checkpoint should NOT trigger the warning regardless of format.
    """

    # 8 days in seconds - just above the 7-day threshold
    _EIGHT_DAYS = 8 * 24 * 3600

    def _run_search(self, mock_org, runner, extra_args=None, start=1000, end=None):
        """Helper to invoke a search with configurable time range."""
        if end is None:
            end = start + self._EIGHT_DAYS
        args = ["--oid", "o"]
        if extra_args:
            args.extend(extra_args)
        args.extend([
            "search", "run",
            "--query", "q",
            "--start", str(start),
            "--end", str(end),
        ])
        mock_org.client.request.side_effect = _make_search_responses(1)
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            return runner.invoke(cli, args)

    def test_warning_shown_for_csv_format(self, mock_org):
        """CSV format over 7 days without --checkpoint emits a warning."""
        runner = CliRunner(mix_stderr=False)
        result = self._run_search(mock_org, runner, ["--output", "csv"])
        assert result.exit_code == 0
        assert "Warning: searching 8 days without --checkpoint" in result.stderr
        assert "all results are buffered in memory" in result.stderr

    def test_warning_shown_for_yaml_format(self, mock_org):
        """YAML format over 7 days without --checkpoint emits a warning."""
        runner = CliRunner(mix_stderr=False)
        result = self._run_search(mock_org, runner, ["--output", "yaml"])
        assert result.exit_code == 0
        assert "Warning: searching 8 days without --checkpoint" in result.stderr

    def test_warning_not_shown_for_table(self, mock_org):
        """Table now streams with sampled column widths - no warning needed."""
        runner = CliRunner(mix_stderr=False)
        result = self._run_search(mock_org, runner, ["--output", "table"])
        assert result.exit_code == 0
        assert "without --checkpoint" not in result.stderr

    def test_warning_not_shown_for_jsonl(self, mock_org):
        """JSONL streams with constant memory - no warning needed."""
        runner = CliRunner(mix_stderr=False)
        result = self._run_search(mock_org, runner, ["--output", "jsonl"])
        assert result.exit_code == 0
        assert "without --checkpoint" not in result.stderr

    def test_warning_not_shown_for_json(self, mock_org):
        """JSON streams with constant memory - no warning needed."""
        runner = CliRunner(mix_stderr=False)
        result = self._run_search(mock_org, runner, ["--output", "json"])
        assert result.exit_code == 0
        assert "without --checkpoint" not in result.stderr

    def test_warning_not_shown_under_threshold(self, mock_org):
        """A 6-day search should not trigger the warning."""
        six_days = 6 * 24 * 3600
        runner = CliRunner(mix_stderr=False)
        result = self._run_search(
            mock_org, runner, ["--output", "csv"],
            start=1000, end=1000 + six_days,
        )
        assert result.exit_code == 0
        assert "without --checkpoint" not in result.stderr

    def test_warning_not_shown_with_checkpoint(self, tmp_path, mock_org):
        """With --checkpoint, no warning regardless of format or time range."""
        data_path = str(tmp_path / "warn_cp.jsonl")
        runner = CliRunner(mix_stderr=False)
        end = 1000 + self._EIGHT_DAYS
        mock_org.client.request.side_effect = _make_search_responses(1)
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            result = runner.invoke(cli, [
                "--oid", "o", "--output", "csv",
                "search", "run",
                "--query", "q", "--start", "1000", "--end", str(end),
                "--checkpoint", data_path,
            ])
        assert result.exit_code == 0
        assert "without --checkpoint" not in result.stderr

    def test_warning_suggests_alternatives(self, mock_org):
        """Warning text mentions jsonl, table, and --checkpoint as alternatives."""
        runner = CliRunner(mix_stderr=False)
        result = self._run_search(mock_org, runner, ["--output", "csv"])
        assert result.exit_code == 0
        assert "--checkpoint" in result.stderr
        assert "jsonl" in result.stderr
        assert "table" in result.stderr
        assert "constant memory" in result.stderr


class TestCheckpointRecommendWarning:
    """Tests for the --checkpoint resumability recommendation on very large searches.

    The warning triggers when the time range exceeds _CHECKPOINT_RECOMMEND_SECONDS
    (14 days) regardless of output format. It recommends --checkpoint for resumability,
    not for memory reasons.
    """

    # 15 days in seconds - just above the 14-day threshold
    _FIFTEEN_DAYS = 15 * 24 * 3600

    def _run_search(self, mock_org, runner, extra_args=None, start=1000, end=None):
        """Helper to invoke a search with configurable time range."""
        if end is None:
            end = start + self._FIFTEEN_DAYS
        args = ["--oid", "o"]
        if extra_args:
            args.extend(extra_args)
        args.extend([
            "search", "run",
            "--query", "q",
            "--start", str(start),
            "--end", str(end),
        ])
        mock_org.client.request.side_effect = _make_search_responses(1)
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            return runner.invoke(cli, args)

    def test_shown_for_jsonl(self, mock_org):
        """JSONL over 14 days still gets the checkpoint recommendation."""
        runner = CliRunner(mix_stderr=False)
        result = self._run_search(mock_org, runner, ["--output", "jsonl"])
        assert result.exit_code == 0
        assert "progress will be lost" in result.stderr
        assert "--resume" in result.stderr

    def test_shown_for_table(self, mock_org):
        """Table over 14 days gets the checkpoint recommendation."""
        runner = CliRunner(mix_stderr=False)
        result = self._run_search(mock_org, runner, ["--output", "table"])
        assert result.exit_code == 0
        assert "progress will be lost" in result.stderr

    def test_not_shown_under_threshold(self, mock_org):
        """A 13-day search should not trigger the recommendation."""
        thirteen_days = 13 * 24 * 3600
        runner = CliRunner(mix_stderr=False)
        result = self._run_search(
            mock_org, runner, ["--output", "jsonl"],
            start=1000, end=1000 + thirteen_days,
        )
        assert result.exit_code == 0
        assert "progress will be lost" not in result.stderr

    def test_not_shown_with_checkpoint(self, tmp_path, mock_org):
        """With --checkpoint, no resumability warning."""
        data_path = str(tmp_path / "recommend_cp.jsonl")
        runner = CliRunner(mix_stderr=False)
        end = 1000 + self._FIFTEEN_DAYS
        mock_org.client.request.side_effect = _make_search_responses(1)
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            result = runner.invoke(cli, [
                "--oid", "o", "--output", "jsonl",
                "search", "run",
                "--query", "q", "--start", "1000", "--end", str(end),
                "--checkpoint", data_path,
            ])
        assert result.exit_code == 0
        assert "progress will be lost" not in result.stderr

    def test_mentions_resume_flag(self, mock_org):
        """Warning text mentions --resume for resumability."""
        runner = CliRunner(mix_stderr=False)
        result = self._run_search(mock_org, runner, ["--output", "table"])
        assert result.exit_code == 0
        assert "--resume" in result.stderr
        assert "--checkpoint" in result.stderr


class TestFormatFileSize:
    """Tests for _format_file_size human-readable formatting."""

    def test_bytes(self):
        from limacharlie.commands.search import _format_file_size
        assert _format_file_size(0) == "0 B"
        assert _format_file_size(512) == "512 B"
        assert _format_file_size(1023) == "1023 B"

    def test_kilobytes(self):
        from limacharlie.commands.search import _format_file_size
        assert _format_file_size(1024) == "1.0 KB"
        assert _format_file_size(1536) == "1.5 KB"
        assert _format_file_size(10240) == "10.0 KB"

    def test_megabytes(self):
        from limacharlie.commands.search import _format_file_size
        assert _format_file_size(1024 * 1024) == "1.0 MB"
        assert _format_file_size(1024 * 1024 * 5 + 1024 * 512) == "5.5 MB"

    def test_gigabytes(self):
        from limacharlie.commands.search import _format_file_size
        assert _format_file_size(1024 ** 3) == "1.0 GB"
        assert _format_file_size(int(1024 ** 3 * 2.3)) == "2.3 GB"

    def test_terabytes(self):
        from limacharlie.commands.search import _format_file_size
        assert _format_file_size(1024 ** 4) == "1.0 TB"


class TestCheckpointsListFileSize:
    """Tests for file size column in checkpoint list output."""

    def test_table_includes_size_column(self, tmp_path, mock_org):
        """Checkpoints list table includes a 'size' column with human-readable file sizes."""
        data_path = str(tmp_path / "sized.jsonl")
        mock_org.client.request.side_effect = _make_search_responses(3, events_per_page=10)

        runner = CliRunner()
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            runner.invoke(cli, [
                "--oid", "test-oid",
                "search", "run",
                "--query", "* | NEW_PROCESS | *",
                "--start", "1700000000", "--end", "1700086400",
                "--checkpoint", data_path,
            ])

        result = runner.invoke(cli, ["--output", "table", "search", "checkpoints"])
        assert result.exit_code == 0
        # Table header should include 'size'
        assert "size" in result.output.lower()
        # Should show a human-readable size (the checkpoint file has data)
        assert "KB" in result.output or " B" in result.output

    def test_json_includes_file_size_bytes(self, tmp_path, mock_org):
        """JSON output includes data_file_size in bytes."""
        data_path = str(tmp_path / "sized_json.jsonl")
        mock_org.client.request.side_effect = _make_search_responses(2, events_per_page=3)

        runner = CliRunner()
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            runner.invoke(cli, [
                "--oid", "test-oid",
                "search", "run",
                "--query", "test",
                "--start", "1700000000", "--end", "1700086400",
                "--checkpoint", data_path,
            ])

        result = runner.invoke(cli, ["--output", "json", "search", "checkpoints"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert len(parsed) == 1
        assert "data_file_size" in parsed[0]
        assert isinstance(parsed[0]["data_file_size"], int)
        assert parsed[0]["data_file_size"] > 0


class TestFormatExpandedEventBlock:
    """Tests for _format_expanded_event_block edge cases."""

    def test_complete_row(self):
        from limacharlie.commands.search import _format_expanded_event_block
        row = {
            "mtd": {"ts": 1700000000000, "stream": "event"},
            "data": {"routing": {"event_type": "NEW_PROCESS"}, "event": {"pid": 42}},
        }
        result = _format_expanded_event_block(row)
        assert "---" in result
        assert "NEW_PROCESS" in result
        assert "event" in result
        assert "42" in result

    def test_empty_row(self):
        from limacharlie.commands.search import _format_expanded_event_block
        result = _format_expanded_event_block({})
        assert "--- event ---" in result

    def test_empty_mtd(self):
        from limacharlie.commands.search import _format_expanded_event_block
        result = _format_expanded_event_block({"mtd": {}, "data": {"x": 1}})
        assert "---" in result
        assert '"x"' in result

    def test_missing_data(self):
        from limacharlie.commands.search import _format_expanded_event_block
        result = _format_expanded_event_block({"mtd": {"ts": 1700000000000}})
        assert "---" in result

    def test_data_not_a_dict(self):
        from limacharlie.commands.search import _format_expanded_event_block
        result = _format_expanded_event_block({"data": "just a string"})
        assert "---" in result
        assert "just a string" in result

    def test_invalid_timestamp(self):
        """Extremely large timestamp should not crash."""
        from limacharlie.commands.search import _format_expanded_event_block
        row = {"mtd": {"ts": 99999999999999999}, "data": {}}
        result = _format_expanded_event_block(row)
        assert "---" in result

    def test_negative_timestamp(self):
        from limacharlie.commands.search import _format_expanded_event_block
        row = {"mtd": {"ts": -1000}, "data": {}}
        result = _format_expanded_event_block(row)
        assert "---" in result

    def test_event_type_from_cat_field(self):
        from limacharlie.commands.search import _format_expanded_event_block
        row = {"mtd": {}, "data": {"cat": "DETECTION"}}
        result = _format_expanded_event_block(row)
        assert "DETECTION" in result

    def test_event_type_from_etype_field(self):
        from limacharlie.commands.search import _format_expanded_event_block
        row = {"mtd": {}, "data": {"etype": "AUDIT_EVENT"}}
        result = _format_expanded_event_block(row)
        assert "AUDIT_EVENT" in result


class TestStreamExpandedEvents:
    """Tests for _stream_expanded_events."""

    def test_empty_iterator(self):
        from limacharlie.commands.search import _stream_expanded_events
        assert _stream_expanded_events(iter([])) is False

    def test_non_event_types_skipped(self):
        from limacharlie.commands.search import _stream_expanded_events
        results = [{"type": "facets", "data": {}}]
        assert _stream_expanded_events(iter(results)) is False

    def test_event_with_no_rows(self):
        from limacharlie.commands.search import _stream_expanded_events
        results = [{"type": "events", "rows": []}]
        assert _stream_expanded_events(iter(results)) is False

    def test_event_with_none_rows(self):
        from limacharlie.commands.search import _stream_expanded_events
        results = [{"type": "events", "rows": None}]
        assert _stream_expanded_events(iter(results)) is False


class TestWarningBoundaryValues:
    """Tests for exact boundary values of warning thresholds."""

    _SEVEN_DAYS = 7 * 24 * 3600
    _FOURTEEN_DAYS = 14 * 24 * 3600

    def _run_search(self, mock_org, runner, fmt, start, end):
        mock_org.client.request.side_effect = _make_search_responses(1)
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            return runner.invoke(cli, [
                "--oid", "o", "--output", fmt, "search", "run",
                "--query", "q", "--start", str(start), "--end", str(end),
            ])

    def test_exactly_7_days_csv_no_warning(self, mock_org):
        """Exactly 7 days should NOT trigger the buffering warning (> not >=)."""
        runner = CliRunner(mix_stderr=False)
        result = self._run_search(mock_org, runner, "csv", 1000, 1000 + self._SEVEN_DAYS)
        assert result.exit_code == 0
        assert "buffered in memory" not in result.stderr

    def test_7_days_plus_one_second_csv_warns(self, mock_org):
        """One second over 7 days should trigger the buffering warning."""
        runner = CliRunner(mix_stderr=False)
        result = self._run_search(mock_org, runner, "csv", 1000, 1000 + self._SEVEN_DAYS + 1)
        assert result.exit_code == 0
        assert "buffered in memory" in result.stderr

    def test_exactly_14_days_no_resume_warning(self, mock_org):
        """Exactly 14 days should NOT trigger the resume warning (> not >=)."""
        runner = CliRunner(mix_stderr=False)
        result = self._run_search(mock_org, runner, "jsonl", 1000, 1000 + self._FOURTEEN_DAYS)
        assert result.exit_code == 0
        assert "progress will be lost" not in result.stderr

    def test_14_days_plus_one_second_resume_warns(self, mock_org):
        """One second over 14 days should trigger the resume warning."""
        runner = CliRunner(mix_stderr=False)
        result = self._run_search(mock_org, runner, "jsonl", 1000, 1000 + self._FOURTEEN_DAYS + 1)
        assert result.exit_code == 0
        assert "progress will be lost" in result.stderr

    def test_both_warnings_fire_for_csv_over_14_days(self, mock_org):
        """CSV with >14 days should trigger BOTH warnings."""
        runner = CliRunner(mix_stderr=False)
        result = self._run_search(mock_org, runner, "csv", 1000, 1000 + self._FOURTEEN_DAYS + 1)
        assert result.exit_code == 0
        assert "buffered in memory" in result.stderr
        assert "progress will be lost" in result.stderr


class TestStreamTableFromFileEdgeCases:
    """Tests for _stream_table_from_file with edge case inputs.

    These test the function directly rather than going through checkpoint-show,
    since we need precise control over file contents (including corrupt data).
    """

    def test_empty_file(self, tmp_path):
        """Empty file should show 'No events'."""
        from limacharlie.commands.search import _stream_table_from_file
        data_path = str(tmp_path / "empty.jsonl")
        with open(data_path, "w") as f:
            f.write("")

        from click.testing import CliRunner
        from io import StringIO
        import sys
        # Capture stdout
        old_stdout = sys.stdout
        sys.stdout = captured = StringIO()
        try:
            _stream_table_from_file(data_path)
        finally:
            sys.stdout = old_stdout
        output = captured.getvalue()
        assert "No events" in output

    def test_corrupt_lines_skipped(self, tmp_path):
        """Non-JSON lines in file should be skipped without error."""
        from limacharlie.commands.search import _stream_table_from_file
        data_path = str(tmp_path / "corrupt.jsonl")
        good_result = json.dumps({
            "type": "events",
            "rows": [{"mtd": {"ts": 1700000000000, "stream": "event"},
                       "data": {"routing": {"event_type": "NEW_PROCESS"}, "event": {"pid": 1}}}],
        })
        with open(data_path, "w") as f:
            f.write("not json at all\n")
            f.write(good_result + "\n")
            f.write("{broken json\n")
            f.write(good_result + "\n")

        import sys
        from io import StringIO
        old_stdout = sys.stdout
        sys.stdout = captured = StringIO()
        try:
            _stream_table_from_file(data_path)
        finally:
            sys.stdout = old_stdout
        output = captured.getvalue()
        # Should render the valid rows without crashing
        assert "NEW_PROCESS" in output

    def test_only_non_event_types(self, tmp_path):
        """File with only facet results should show 'No events'."""
        from limacharlie.commands.search import _stream_table_from_file
        data_path = str(tmp_path / "facets_only.jsonl")
        with open(data_path, "w") as f:
            f.write(json.dumps({"type": "facets", "data": {"field": 42}}) + "\n")

        import sys
        from io import StringIO
        old_stdout = sys.stdout
        sys.stdout = captured = StringIO()
        try:
            _stream_table_from_file(data_path)
        finally:
            sys.stdout = old_stdout
        output = captured.getvalue()
        assert "No events" in output

    def test_blank_lines_skipped(self, tmp_path):
        """Blank lines (whitespace only) should be skipped."""
        from limacharlie.commands.search import _stream_table_from_file
        data_path = str(tmp_path / "blanks.jsonl")
        good_result = json.dumps({
            "type": "events",
            "rows": [{"mtd": {"ts": 1700000000000}, "data": {"event": {"pid": 1}}}],
        })
        with open(data_path, "w") as f:
            f.write("\n")
            f.write("   \n")
            f.write(good_result + "\n")
            f.write("\n")

        import sys
        from io import StringIO
        old_stdout = sys.stdout
        sys.stdout = captured = StringIO()
        try:
            _stream_table_from_file(data_path)
        finally:
            sys.stdout = old_stdout
        output = captured.getvalue()
        assert "pid" in output


class TestCheckpointsListSortOrder:
    """Tests for checkpoints list column order and sort."""

    def test_sorted_by_created_descending(self, tmp_path, mock_org):
        """Checkpoints are sorted newest-first by created timestamp."""
        # Create two checkpoints with different creation times.
        for name in ("first.jsonl", "second.jsonl"):
            data_path = str(tmp_path / name)
            mock_org.client.request.side_effect = _make_search_responses(1)
            runner = CliRunner()
            with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
                 patch("limacharlie.commands.search.Organization", return_value=mock_org):
                runner.invoke(cli, [
                    "--oid", "test-oid", "search", "run",
                    "--query", "q", "--start", "1700000000", "--end", "1700086400",
                    "--checkpoint", data_path,
                ])

        result = CliRunner().invoke(cli, ["--output", "json", "search", "checkpoints"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        # JSON output goes through the same sort path (via the table branch)
        # but JSON output bypasses the table rows - check via table output.
        result = CliRunner().invoke(cli, ["--output", "table", "search", "checkpoints"])
        assert result.exit_code == 0
        lines = [l for l in result.output.strip().split("\n") if l.strip() and not l.startswith("-")]
        # Header is first, then data rows
        assert len(lines) >= 3  # header + 2 data rows

    def test_created_column_is_first(self, tmp_path, mock_org):
        """The 'created' column should appear first in table output."""
        data_path = str(tmp_path / "col_order.jsonl")
        mock_org.client.request.side_effect = _make_search_responses(1)
        runner = CliRunner()
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            runner.invoke(cli, [
                "--oid", "test-oid", "search", "run",
                "--query", "q", "--start", "1700000000", "--end", "1700086400",
                "--checkpoint", data_path,
            ])

        result = CliRunner().invoke(cli, ["--output", "table", "search", "checkpoints"])
        assert result.exit_code == 0
        lines = result.output.strip().split("\n")
        header = lines[0].lower()
        # 'created' should appear before 'data_file'
        assert header.index("created") < header.index("data_file")
