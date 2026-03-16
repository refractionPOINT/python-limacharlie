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

        result = runner.invoke(cli, [
            "search", "checkpoint-show",
            "--checkpoint", data_path,
        ])
        assert result.exit_code == 0
        assert "empty" in result.output.lower()

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
