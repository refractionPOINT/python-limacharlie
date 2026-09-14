"""Integration tests for search checkpoint/resume flow.

Tests the end-to-end interaction between CheckpointWriter,
CheckpointResumer, and the search execute generator, using
mocked SDK responses to simulate real search behavior without
requiring API credentials.

Covers: normal checkpoint, interruption (KeyboardInterrupt), resume
after interrupt, error recovery, retry + checkpoint interaction, and
server-side query cancellation behavior.
"""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from limacharlie.search_checkpoint import (
    CheckpointReader,
    CheckpointResumer,
    CheckpointWriter,
    get_data_dir,
    list_checkpoints,
    _meta_path,
)
from limacharlie.errors import ApiError, SearchError
from limacharlie.sdk.search import Search


@pytest.fixture
def checkpoints_dir(tmp_path):
    """Temporary checkpoints metadata directory."""
    cp_dir = tmp_path / "checkpoints_meta"
    cp_dir.mkdir()
    return cp_dir


@pytest.fixture(autouse=True)
def patch_data_dir(checkpoints_dir):
    """Patch get_data_dir for all tests."""
    with patch("limacharlie.search_checkpoint.get_data_dir", return_value=str(checkpoints_dir)):
        yield


@pytest.fixture
def mock_org():
    """Mock Organization with search URL."""
    org = MagicMock()
    org.oid = "test-oid"
    org.client = MagicMock()
    org.get_urls.return_value = {"search": "abc123.replay-search.limacharlie.io"}
    return org


def _make_search_responses(num_pages, results_per_page):
    """Build mock API responses for a multi-page search.

    Returns a list of side_effect values for mock_org.client.request.
    """
    responses = [{"queryId": "q-test"}]
    for page in range(num_pages):
        is_last = page == num_pages - 1
        result = {
            "type": "events",
            "rows": [{"data": {"idx": page * results_per_page + i}}
                     for i in range(results_per_page)],
        }
        if not is_last:
            result["nextToken"] = f"tok-{page + 1}"
        poll_resp = {
            "results": [result],
            "completed": True,
        }
        responses.append(poll_resp)
    responses.append({})  # DELETE cleanup
    return responses


class TestCheckpointEndToEnd:
    """End-to-end checkpoint creation and verification."""

    def test_checkpoint_captures_all_results(self, tmp_path, mock_org):
        """Full search with checkpoint saves all results to JSONL."""
        mock_org.client.request.side_effect = _make_search_responses(3, 2)
        search = Search(mock_org)
        data_path = str(tmp_path / "search.jsonl")

        with CheckpointWriter(data_path, "test query", 1000, 2000,
                              "event", None, "test-oid") as writer:
            count = 0
            for item in search.execute("test query", 1000, 2000, stream="event"):
                writer.write_result(item)
                count += 1
                writer.update_progress(1, count, completed=False)
            writer.update_progress(1, count, completed=True)

        # Verify data file
        meta, results = CheckpointReader.read(data_path)
        assert len(results) == 3  # 3 pages, 1 result wrapper each
        assert meta["completed"] is True
        assert meta["result_count"] == 3

    def test_checkpoint_survives_interruption(self, tmp_path, mock_org):
        """Checkpoint preserves results even when search is interrupted."""
        # Search that returns 3 pages, but we stop after 2
        responses = _make_search_responses(3, 2)
        mock_org.client.request.side_effect = responses
        search = Search(mock_org)
        data_path = str(tmp_path / "interrupted.jsonl")

        with CheckpointWriter(data_path, "test query", 1000, 2000,
                              "event", None, "test-oid") as writer:
            count = 0
            for item in search.execute("test query", 1000, 2000,
                                       stream="event", limit=2):
                writer.write_result(item)
                count += 1
                writer.update_progress(1, count, completed=False)

        # Data file should have 2 results
        meta, results = CheckpointReader.read(data_path)
        assert len(results) == 2
        assert meta["completed"] is False


class TestResumeEndToEnd:
    """End-to-end resume from checkpoint.

    Tests the token-based server-side resume path. When a checkpoint has
    a last_token, resume passes it to execute(start_token=...) so the
    server skips directly to the next page. No re-fetching of previous pages.
    """

    def test_resume_with_token_skips_to_correct_page(self, tmp_path, mock_org):
        """Resume uses stored token to skip directly to the right page."""
        # Initial run: 2 pages, interrupted after page 2 (has nextToken)
        mock_org.client.request.side_effect = [
            {"queryId": "q-init"},
            {"results": [{"type": "events", "rows": [{"a": 1}], "nextToken": "tok1"}], "completed": True},
            {"results": [{"type": "events", "rows": [{"b": 2}], "nextToken": "tok2"}], "completed": True},
            {},  # DELETE (limit=2)
        ]
        search = Search(mock_org)
        data_path = str(tmp_path / "token_resume.jsonl")

        last_token = None
        page = 1
        with CheckpointWriter(data_path, "test query", 1000, 2000,
                              "event", None, "test-oid") as writer:
            count = 0
            for item in search.execute("test query", 1000, 2000,
                                       stream="event", limit=2):
                writer.write_result(item)
                count += 1
                if item.get("nextToken"):
                    last_token = item["nextToken"]
                    page += 1
                writer.update_progress(page, count, completed=False,
                                       last_token=last_token)

        # Verify checkpoint has token
        meta = CheckpointReader.read_metadata(data_path)
        assert meta["last_token"] == "tok2"
        assert meta["page"] == 3  # was on page 3 when interrupted

        # Resume: server gets new queryId but we pass tok2 to skip ahead
        mock_org.client.request.reset_mock()
        mock_org.client.request.side_effect = [
            {"queryId": "q-resume"},
            # Server returns page 3 directly (because we passed tok2)
            {"results": [{"type": "events", "rows": [{"c": 3}]}], "completed": True},
            {},  # DELETE
        ]
        search2 = Search(mock_org)
        resumer = CheckpointResumer(data_path)
        resume_token = resumer.metadata.get("last_token")
        resume_page = resumer.metadata.get("page", 1)

        with resumer:
            for item in search2.execute("test query", 1000, 2000, stream="event",
                                        start_token=resume_token,
                                        start_page=resume_page):
                resumer.write_result(item)

        # Verify: the first GET used the saved token
        get_calls = [c for c in mock_org.client.request.call_args_list
                     if c[0][0] == "GET"]
        assert len(get_calls) == 1
        assert get_calls[0][1]["query_params"] == {"token": "tok2"}

        # Data file has 3 results total (2 original + 1 new)
        _, results = CheckpointReader.read(data_path)
        assert len(results) == 3

    def test_resume_without_token_falls_back_to_skip(self, tmp_path, mock_org):
        """Resume without a stored token re-fetches and skips."""
        # Initial run: interrupted on page 1 before any nextToken
        mock_org.client.request.side_effect = [
            {"queryId": "q-no-tok"},
            {"results": [{"type": "events", "rows": [{"a": 1}]}], "completed": True},
            {},  # DELETE (limit=1)
        ]
        search = Search(mock_org)
        data_path = str(tmp_path / "no_token.jsonl")

        with CheckpointWriter(data_path, "query", 1000, 2000,
                              None, None, "test-oid") as writer:
            for item in search.execute("query", 1000, 2000, limit=1):
                writer.write_result(item)
            writer.update_progress(1, 1, completed=False)
            # No last_token stored

        meta = CheckpointReader.read_metadata(data_path)
        assert meta.get("last_token") is None

        # Resume: no token, so re-fetches from start
        mock_org.client.request.side_effect = _make_search_responses(2, 1)
        search2 = Search(mock_org)
        resumer = CheckpointResumer(data_path)

        skipped = 0
        with resumer:
            for item in search2.execute("query", 1000, 2000):
                if skipped < resumer.existing_count:
                    skipped += 1
                    continue
                resumer.write_result(item)

        _, results = CheckpointReader.read(data_path)
        assert len(results) == 2  # 1 original + 1 new

    def test_resume_completed_checkpoint_is_noop(self, tmp_path, mock_org):
        """Resuming an already-completed checkpoint returns existing results."""
        responses = _make_search_responses(2, 1)
        mock_org.client.request.side_effect = responses
        search = Search(mock_org)
        data_path = str(tmp_path / "completed.jsonl")

        with CheckpointWriter(data_path, "query", 1000, 2000,
                              None, None, "test-oid") as writer:
            count = 0
            for item in search.execute("query", 1000, 2000):
                writer.write_result(item)
                count += 1
            writer.update_progress(1, count, completed=True)

        meta = CheckpointReader.read_metadata(data_path)
        assert meta["completed"] is True

        resumer = CheckpointResumer(data_path)
        assert resumer.metadata["completed"] is True


class TestResumeCorrectness:
    """Tests verifying that resume re-runs the query correctly.

    Validates that:
    - Resume uses the same query parameters from the checkpoint metadata
    - The search API is called with proper POST body (same query, start, end, stream)
    - Pagination tokens are followed correctly on the re-run
    - The skip count matches exactly the number of results in the data file
    - Results written to the data file after resume are only the new ones
    """

    def test_resume_uses_correct_query_parameters(self, tmp_path, mock_org):
        """Resume re-executes with the exact same query params from metadata."""
        # Initial run
        mock_org.client.request.side_effect = [
            {"queryId": "q-init"},
            {"results": [{"type": "events", "rows": [{"a": 1}]}], "completed": True},
            {},  # DELETE
        ]
        search = Search(mock_org)
        data_path = str(tmp_path / "params_test.jsonl")

        with CheckpointWriter(data_path, "plat == linux | DNS_REQUEST | *",
                              5000, 9000, "event", 100, "org-abc") as writer:
            for item in search.execute("plat == linux | DNS_REQUEST | *",
                                       5000, 9000, stream="event", limit=1):
                writer.write_result(item)
            # Intentionally NOT marking completed

        # Resume - verify the query parameters
        mock_org.client.request.reset_mock()
        mock_org.client.request.side_effect = [
            {"queryId": "q-resume"},
            {"results": [{"type": "events", "rows": [{"a": 1}]}], "completed": True},
            {"results": [{"type": "events", "rows": [{"b": 2}]}], "completed": True},
            {},  # DELETE
        ]
        search2 = Search(mock_org)
        resumer = CheckpointResumer(data_path)

        # Verify metadata loaded correctly
        assert resumer.metadata["query"] == "plat == linux | DNS_REQUEST | *"
        assert resumer.metadata["start_time"] == 5000
        assert resumer.metadata["end_time"] == 9000
        assert resumer.metadata["stream"] == "event"
        assert resumer.metadata["oid"] == "org-abc"

        skipped = 0
        with resumer:
            for item in search2.execute("plat == linux | DNS_REQUEST | *",
                                        5000, 9000, stream="event"):
                if skipped < resumer.existing_count:
                    skipped += 1
                    continue
                resumer.write_result(item)

        # Verify the POST body sent to initiate search
        import json
        post_calls = [c for c in mock_org.client.request.call_args_list
                      if c[0][0] == "POST"]
        assert len(post_calls) == 1
        body = json.loads(post_calls[0][1]["raw_body"])
        assert body["query"] == "plat == linux | DNS_REQUEST | *"
        assert body["startTime"] == "5000"
        assert body["endTime"] == "9000"
        assert body["stream"] == "event"

    def test_resume_with_token_starts_from_saved_position(self, tmp_path, mock_org):
        """Resume with stored token skips to the correct page via start_token."""
        # Initial run: 1 page fetched with nextToken
        mock_org.client.request.side_effect = [
            {"queryId": "q-tok-init"},
            {"results": [{"type": "events", "rows": [{"p": 1}], "nextToken": "tok1"}],
             "completed": True},
            {},  # DELETE (limit=1)
        ]
        search = Search(mock_org)
        data_path = str(tmp_path / "token_test.jsonl")

        last_token = None
        page = 1
        with CheckpointWriter(data_path, "query", 1000, 2000,
                              None, None, "test-oid") as writer:
            for item in search.execute("query", 1000, 2000, limit=1):
                writer.write_result(item)
                if item.get("nextToken"):
                    last_token = item["nextToken"]
                    page += 1
            writer.update_progress(page, 1, completed=False, last_token=last_token)

        meta = CheckpointReader.read_metadata(data_path)
        assert meta["last_token"] == "tok1"

        # Resume: pass tok1 as start_token, server returns pages 2 and 3
        mock_org.client.request.reset_mock()
        mock_org.client.request.side_effect = [
            {"queryId": "q-tok-resume"},
            # First GET uses tok1 -> returns page 2
            {"results": [{"type": "events", "rows": [{"p": 2}], "nextToken": "tok2"}],
             "completed": True},
            # Second GET uses tok2 -> returns page 3
            {"results": [{"type": "events", "rows": [{"p": 3}]}],
             "completed": True},
            {},  # DELETE
        ]
        search2 = Search(mock_org)

        resumer = CheckpointResumer(data_path)
        resume_token = resumer.metadata.get("last_token")
        resume_page = resumer.metadata.get("page", 1)

        with resumer:
            for item in search2.execute("query", 1000, 2000,
                                        start_token=resume_token,
                                        start_page=resume_page):
                resumer.write_result(item)

        # Verify: first GET used tok1 (skipped page 1 entirely)
        get_calls = [c for c in mock_org.client.request.call_args_list
                     if c[0][0] == "GET"]
        assert len(get_calls) == 2
        # First GET: uses saved token tok1
        assert get_calls[0][1]["query_params"] == {"token": "tok1"}
        # Second GET: uses tok2 from page 2
        assert get_calls[1][1]["query_params"] == {"token": "tok2"}

        # Data file: 3 total (1 original + 2 new from resume)
        _, results = CheckpointReader.read(data_path)
        assert len(results) == 3

    def test_resume_skip_count_matches_data_file_lines(self, tmp_path, mock_org):
        """Skip count is determined by actual data file lines, not metadata.

        If metadata says result_count=5 but data file has 3 lines (crash
        between metadata update and data write), we trust the data file.
        """
        # Create checkpoint with 3 results
        data_path = str(tmp_path / "count_test.jsonl")
        with CheckpointWriter(data_path, "query", 1000, 2000,
                              None, None, "test-oid") as writer:
            writer.write_result({"r": 1})
            writer.write_result({"r": 2})
            writer.write_result({"r": 3})
            # Metadata says 5 but file only has 3 (simulating inconsistency)
            writer.update_progress(2, 5, completed=False)

        resumer = CheckpointResumer(data_path)
        # existing_count should be 3 (from data file), not 5 (from metadata)
        assert resumer.existing_count == 3

    def test_resume_only_appends_new_results_to_file(self, tmp_path, mock_org):
        """Resume writes only new results to the data file, not duplicates."""
        # Create checkpoint with 2 results
        mock_org.client.request.side_effect = _make_search_responses(3, 1)
        search = Search(mock_org)
        data_path = str(tmp_path / "append_test.jsonl")

        with CheckpointWriter(data_path, "query", 1000, 2000,
                              None, None, "test-oid") as writer:
            count = 0
            for item in search.execute("query", 1000, 2000, limit=2):
                writer.write_result(item)
                count += 1
            writer.update_progress(1, count, completed=False)

        _, before = CheckpointReader.read(data_path)
        assert len(before) == 2

        # Resume
        mock_org.client.request.side_effect = _make_search_responses(3, 1)
        search2 = Search(mock_org)
        resumer = CheckpointResumer(data_path)
        skip_count = resumer.existing_count

        skipped = 0
        count = skip_count
        with resumer:
            for item in search2.execute("query", 1000, 2000):
                if skipped < skip_count:
                    skipped += 1
                    continue
                resumer.write_result(item)
                count += 1
            resumer.update_progress(1, count, completed=True)

        # File should have exactly 3 lines (2 original + 1 new)
        with open(data_path) as f:
            lines = [l for l in f if l.strip()]
        assert len(lines) == 3

        # And all 3 should be valid JSON
        import json
        for line in lines:
            json.loads(line)



    """End-to-end listing of checkpoints."""

    def test_list_shows_checkpoints_after_run(self, tmp_path, mock_org):
        """list_checkpoints returns metadata for created checkpoints."""
        responses = _make_search_responses(1, 1)
        mock_org.client.request.side_effect = responses
        search = Search(mock_org)
        data_path = str(tmp_path / "listed.jsonl")

        with CheckpointWriter(data_path, "list test query", 5000, 6000,
                              "detect", 10, "test-oid") as writer:
            for item in search.execute("list test query", 5000, 6000, stream="detect"):
                writer.write_result(item)
            writer.update_progress(1, 1, completed=True)

        cps = list_checkpoints()
        assert len(cps) == 1
        cp = cps[0]
        assert cp["query"] == "list test query"
        assert cp["start_time"] == 5000
        assert cp["end_time"] == 6000
        assert cp["completed"] is True
        assert cp["data_file_exists"] is True


class TestCheckpointCancellation:
    """Tests for KeyboardInterrupt handling with checkpoint enabled.

    Verifies that Ctrl+C:
    1. Preserves all results written to the checkpoint data file
    2. Updates metadata to reflect partial progress (completed=False)
    3. Allows successful resume after interruption
    4. Server-side query is canceled (via Search.execute() finally block)
    """

    def test_keyboard_interrupt_preserves_checkpoint_data(self, tmp_path, mock_org):
        """KeyboardInterrupt during checkpointed search preserves all
        results written before the interrupt."""
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"queryId": "q-ki-cp"}
            elif call_count == 2:
                return {
                    "results": [{"type": "events", "rows": [{"a": 1}], "nextToken": "tok1"}],
                    "completed": True,
                }
            elif call_count == 3:
                # Page 2 poll: user hits Ctrl+C
                raise KeyboardInterrupt()
            else:
                return {}  # DELETE

        mock_org.client.request.side_effect = side_effect
        search = Search(mock_org)
        data_path = str(tmp_path / "ki_checkpoint.jsonl")

        writer = CheckpointWriter(data_path, "test query", 1000, 2000,
                                  "event", None, "test-oid")
        count = 0
        with pytest.raises(KeyboardInterrupt):
            with writer:
                for item in search.execute("test query", 1000, 2000, stream="event"):
                    writer.write_result(item)
                    count += 1
                    writer.update_progress(1, count, completed=False)

        # Page 1 result should be preserved in data file.
        meta, results = CheckpointReader.read(data_path)
        assert len(results) == 1
        assert results[0]["rows"] == [{"a": 1}]
        assert meta["completed"] is False
        assert meta["result_count"] == 1

    def test_keyboard_interrupt_during_first_poll_preserves_empty_checkpoint(
        self, tmp_path, mock_org,
    ):
        """Ctrl+C before any results are received creates an empty checkpoint."""
        mock_org.client.request.side_effect = [
            {"queryId": "q-ki-empty"},
            KeyboardInterrupt(),
            {},  # DELETE
        ]
        search = Search(mock_org)
        data_path = str(tmp_path / "empty_ki.jsonl")

        writer = CheckpointWriter(data_path, "test query", 1000, 2000,
                                  "event", None, "test-oid")
        with pytest.raises(KeyboardInterrupt):
            with writer:
                for item in search.execute("test query", 1000, 2000, stream="event"):
                    writer.write_result(item)

        # Checkpoint exists but is empty.
        meta, results = CheckpointReader.read(data_path)
        assert len(results) == 0
        assert meta["completed"] is False

    def test_resume_after_keyboard_interrupt(self, tmp_path, mock_org):
        """Full flow: start -> Ctrl+C -> resume -> complete.

        Simulates a real user workflow:
        1. Start a search with checkpointing
        2. Ctrl+C after getting some results
        3. Resume and get remaining results
        4. Verify all results are present and checkpoint is completed
        """
        # Step 1 & 2: Start search, interrupt after 2 results
        call_count = 0

        def side_effect_initial(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"queryId": "q-resume-ki"}
            elif call_count == 2:
                return {
                    "results": [{"type": "events", "rows": [{"a": 1}], "nextToken": "tok1"}],
                    "completed": True,
                }
            elif call_count == 3:
                return {
                    "results": [{"type": "events", "rows": [{"b": 2}], "nextToken": "tok2"}],
                    "completed": True,
                }
            elif call_count == 4:
                raise KeyboardInterrupt()
            else:
                return {}  # DELETE

        mock_org.client.request.side_effect = side_effect_initial
        search = Search(mock_org)
        data_path = str(tmp_path / "resume_ki.jsonl")

        writer = CheckpointWriter(data_path, "test query", 1000, 2000,
                                  "event", None, "test-oid")
        count = 0
        with pytest.raises(KeyboardInterrupt):
            with writer:
                for item in search.execute("test query", 1000, 2000, stream="event"):
                    writer.write_result(item)
                    count += 1
                    writer.update_progress(1, count, completed=False)

        # Verify 2 results saved after interrupt.
        meta, existing = CheckpointReader.read(data_path)
        assert len(existing) == 2
        assert meta["completed"] is False

        # Step 3: Resume - server returns same data, we skip first 2
        mock_org.client.request.side_effect = [
            {"queryId": "q-resume-ki-2"},
            {"results": [{"type": "events", "rows": [{"a": 1}], "nextToken": "tok1"}], "completed": True},
            {"results": [{"type": "events", "rows": [{"b": 2}], "nextToken": "tok2"}], "completed": True},
            {"results": [{"type": "events", "rows": [{"c": 3}]}], "completed": True},
            {},  # DELETE
        ]
        search2 = Search(mock_org)

        resumer = CheckpointResumer(data_path)
        skip_count = resumer.existing_count
        assert skip_count == 2

        all_results = list(existing)
        count = skip_count
        skipped = 0
        with resumer:
            for item in search2.execute("test query", 1000, 2000, stream="event"):
                if skipped < skip_count:
                    skipped += 1
                    continue
                resumer.write_result(item)
                all_results.append(item)
                count += 1
                resumer.update_progress(1, count, completed=False)
            resumer.update_progress(1, count, completed=True)

        # Step 4: Verify all 3 results present and completed.
        meta, final_results = CheckpointReader.read(data_path)
        assert len(final_results) == 3
        assert final_results[0]["rows"] == [{"a": 1}]
        assert final_results[1]["rows"] == [{"b": 2}]
        assert final_results[2]["rows"] == [{"c": 3}]
        assert meta["completed"] is True
        assert meta["result_count"] == 3

    def test_keyboard_interrupt_server_cancel_still_fires(self, tmp_path, mock_org):
        """Server-side DELETE cancel is called even with checkpoint enabled.

        The Search.execute() finally block calls _cancel_query regardless
        of whether a checkpoint is in use - the checkpoint is a CLI concern,
        the cancel is an SDK concern.
        """
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"queryId": "q-srv-cancel"}
            elif call_count == 2:
                return {
                    "results": [{"type": "events", "rows": [{"a": 1}]}],
                    "completed": False,
                    "nextPollInMs": 500,
                }
            elif call_count == 3:
                raise KeyboardInterrupt()
            else:
                return {}  # DELETE

        mock_org.client.request.side_effect = side_effect
        search = Search(mock_org)
        data_path = str(tmp_path / "srv_cancel.jsonl")

        writer = CheckpointWriter(data_path, "test query", 1000, 2000,
                                  "event", None, "test-oid")
        with pytest.raises(KeyboardInterrupt):
            with writer:
                for item in search.execute("test query", 1000, 2000, stream="event"):
                    writer.write_result(item)

        # Verify DELETE was called on the server
        delete_calls = [c for c in mock_org.client.request.call_args_list
                        if c[0][0] == "DELETE"]
        assert len(delete_calls) == 1
        assert "search/q-srv-cancel" in delete_calls[0][0][1]


class TestCheckpointErrorRecovery:
    """Tests for error handling during checkpointed searches.

    Verifies that non-interrupt errors (SearchError, transport errors)
    preserve checkpoint state for later resume.
    """

    def test_search_error_preserves_checkpoint(self, tmp_path, mock_org):
        """SearchError after partial results preserves checkpoint data."""
        mock_org.client.request.side_effect = [
            {"queryId": "q-err-cp"},
            {"results": [{"type": "events", "rows": [{"a": 1}], "nextToken": "tok1"}], "completed": True},
            {"error": "context canceled"},  # Page 2 error
            {},  # DELETE
        ]
        search = Search(mock_org)
        data_path = str(tmp_path / "error_cp.jsonl")

        writer = CheckpointWriter(data_path, "test query", 1000, 2000,
                                  "event", None, "test-oid")
        count = 0
        with pytest.raises(SearchError, match="context canceled"):
            with writer:
                for item in search.execute("test query", 1000, 2000, stream="event"):
                    writer.write_result(item)
                    count += 1
                    writer.update_progress(1, count, completed=False)

        # Page 1 result should be preserved.
        meta, results = CheckpointReader.read(data_path)
        assert len(results) == 1
        assert meta["completed"] is False

    @patch("limacharlie.sdk.search.time.sleep")
    def test_transient_error_with_checkpoint_recovers(self, mock_sleep, tmp_path, mock_org):
        """Transient error during checkpointed search retries and completes.

        Verifies that poll retry + checkpoint work together correctly -
        the retry happens at the SDK level, the checkpoint captures all
        results including those from retried pages.
        """
        mock_org.client.request.side_effect = [
            {"queryId": "q-retry-cp"},
            # Page 1: success
            {"results": [{"type": "events", "rows": [{"a": 1}], "nextToken": "tok1"}], "completed": True},
            # Page 2: transient 503, then success
            ApiError("503", status_code=503),
            {"results": [{"type": "events", "rows": [{"b": 2}]}], "completed": True},
            {},  # DELETE
        ]
        search = Search(mock_org)
        data_path = str(tmp_path / "retry_cp.jsonl")

        with CheckpointWriter(data_path, "test query", 1000, 2000,
                              "event", None, "test-oid") as writer:
            count = 0
            for item in search.execute("test query", 1000, 2000, stream="event"):
                writer.write_result(item)
                count += 1
                writer.update_progress(1, count, completed=False)
            writer.update_progress(1, count, completed=True)

        # Both pages should be captured despite the transient error.
        meta, results = CheckpointReader.read(data_path)
        assert len(results) == 2
        assert results[0]["rows"] == [{"a": 1}]
        assert results[1]["rows"] == [{"b": 2}]
        assert meta["completed"] is True

    @patch("limacharlie.sdk.search.time.sleep")
    def test_exhausted_retries_preserves_checkpoint(self, mock_sleep, tmp_path, mock_org):
        """When retries exhaust during checkpointed search, partial checkpoint
        is preserved for later resume."""
        mock_org.client.request.side_effect = [
            {"queryId": "q-exhaust-cp"},
            # Page 1: success
            {"results": [{"type": "events", "rows": [{"a": 1}], "nextToken": "tok1"}], "completed": True},
            # Page 2: all retries fail
            ApiError("503", status_code=503),
            ApiError("503", status_code=503),
            ApiError("503", status_code=503),
            ApiError("503", status_code=503),  # Exhausted (3 retries + 1 initial)
        ]
        search = Search(mock_org)
        data_path = str(tmp_path / "exhaust_cp.jsonl")

        writer = CheckpointWriter(data_path, "test query", 1000, 2000,
                                  "event", None, "test-oid")
        count = 0
        with pytest.raises(SearchError):
            with writer:
                for item in search.execute("test query", 1000, 2000, stream="event"):
                    writer.write_result(item)
                    count += 1
                    writer.update_progress(1, count, completed=False)

        # Page 1 result should be preserved.
        meta, results = CheckpointReader.read(data_path)
        assert len(results) == 1
        assert meta["completed"] is False
        assert meta["result_count"] == 1

    def test_resume_after_search_error(self, tmp_path, mock_org):
        """Resume works after a SearchError interrupted the previous run."""
        # Step 1: Run that fails with SearchError after 1 result
        mock_org.client.request.side_effect = [
            {"queryId": "q-err-resume"},
            {"results": [{"type": "events", "rows": [{"a": 1}], "nextToken": "tok1"}], "completed": True},
            {"error": "server error"},
            {},  # DELETE
        ]
        search = Search(mock_org)
        data_path = str(tmp_path / "err_resume.jsonl")

        writer = CheckpointWriter(data_path, "test query", 1000, 2000,
                                  "event", None, "test-oid")
        count = 0
        with pytest.raises(SearchError):
            with writer:
                for item in search.execute("test query", 1000, 2000, stream="event"):
                    writer.write_result(item)
                    count += 1
                    writer.update_progress(1, count, completed=False)

        # Step 2: Resume succeeds
        mock_org.client.request.side_effect = [
            {"queryId": "q-err-resume-2"},
            {"results": [{"type": "events", "rows": [{"a": 1}], "nextToken": "tok1"}], "completed": True},
            {"results": [{"type": "events", "rows": [{"b": 2}]}], "completed": True},
            {},  # DELETE
        ]
        search2 = Search(mock_org)

        resumer = CheckpointResumer(data_path)
        skip_count = resumer.existing_count
        assert skip_count == 1

        count = skip_count
        skipped = 0
        with resumer:
            for item in search2.execute("test query", 1000, 2000, stream="event"):
                if skipped < skip_count:
                    skipped += 1
                    continue
                resumer.write_result(item)
                count += 1
                resumer.update_progress(1, count, completed=False)
            resumer.update_progress(1, count, completed=True)

        meta, final_results = CheckpointReader.read(data_path)
        assert len(final_results) == 2
        assert meta["completed"] is True


class TestCheckpointWriterContextManager:
    """Tests verifying CheckpointWriter context manager cleans up properly."""

    def test_writer_closes_file_on_normal_exit(self, tmp_path):
        """Context manager closes file handle on normal exit."""
        data_path = str(tmp_path / "normal_exit.jsonl")
        writer = CheckpointWriter(data_path, "query", 1000, 2000,
                                  None, None, "oid")
        with writer:
            writer.write_result({"a": 1})
            assert not writer._file.closed

        assert writer._file.closed

    def test_writer_closes_file_on_exception(self, tmp_path):
        """Context manager closes file handle even on exception."""
        data_path = str(tmp_path / "exception_exit.jsonl")
        writer = CheckpointWriter(data_path, "query", 1000, 2000,
                                  None, None, "oid")
        with pytest.raises(ValueError):
            with writer:
                writer.write_result({"a": 1})
                raise ValueError("boom")

        assert writer._file.closed
        # Data should still be flushed and readable.
        meta, results = CheckpointReader.read(data_path)
        assert len(results) == 1

    def test_writer_closes_file_on_keyboard_interrupt(self, tmp_path):
        """Context manager closes file handle on KeyboardInterrupt."""
        data_path = str(tmp_path / "ki_exit.jsonl")
        writer = CheckpointWriter(data_path, "query", 1000, 2000,
                                  None, None, "oid")
        with pytest.raises(KeyboardInterrupt):
            with writer:
                writer.write_result({"a": 1})
                raise KeyboardInterrupt()

        assert writer._file.closed
        meta, results = CheckpointReader.read(data_path)
        assert len(results) == 1

    def test_double_close_is_safe(self, tmp_path):
        """Calling close() multiple times does not raise."""
        data_path = str(tmp_path / "double_close.jsonl")
        writer = CheckpointWriter(data_path, "query", 1000, 2000,
                                  None, None, "oid")
        writer.close()
        writer.close()  # Should not raise


class TestCheckpointResumerContextManager:
    """Tests verifying CheckpointResumer context manager cleans up properly."""

    def _create_checkpoint(self, tmp_path, results):
        """Helper to create a checkpoint with given results."""
        data_path = str(tmp_path / "data.jsonl")
        with CheckpointWriter(data_path, "test query", 1000, 2000,
                              "event", None, "test-oid") as w:
            for r in results:
                w.write_result(r)
            w.update_progress(1, len(results), completed=False)
        return data_path

    def test_resumer_closes_file_on_normal_exit(self, tmp_path):
        """Context manager closes file handle on normal exit."""
        data_path = self._create_checkpoint(tmp_path, [{"a": 1}])
        resumer = CheckpointResumer(data_path)
        with resumer:
            resumer.write_result({"b": 2})
            assert not resumer._file.closed

        assert resumer._file.closed

    def test_resumer_closes_file_on_keyboard_interrupt(self, tmp_path):
        """Context manager closes file handle on KeyboardInterrupt."""
        data_path = self._create_checkpoint(tmp_path, [{"a": 1}])
        resumer = CheckpointResumer(data_path)
        with pytest.raises(KeyboardInterrupt):
            with resumer:
                resumer.write_result({"b": 2})
                raise KeyboardInterrupt()

        assert resumer._file.closed
        # Both original and new result should be in the file.
        _, results = CheckpointReader.read(data_path)
        assert len(results) == 2

    def test_resumer_closes_file_on_exception(self, tmp_path):
        """Context manager closes file handle on general exception."""
        data_path = self._create_checkpoint(tmp_path, [{"a": 1}])
        resumer = CheckpointResumer(data_path)
        with pytest.raises(RuntimeError):
            with resumer:
                resumer.write_result({"b": 2})
                raise RuntimeError("boom")

        assert resumer._file.closed
        _, results = CheckpointReader.read(data_path)
        assert len(results) == 2
