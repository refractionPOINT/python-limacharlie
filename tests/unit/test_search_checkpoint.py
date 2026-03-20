"""Tests for limacharlie.search_checkpoint module.

Tests cover CheckpointWriter, CheckpointReader, CheckpointResumer,
path derivation, and the list_checkpoints function.
"""

import json
import os
import tempfile
from unittest.mock import patch

import pytest

from limacharlie.search_checkpoint import (
    CheckpointReader,
    CheckpointResumer,
    CheckpointWriter,
    get_data_dir,
    list_checkpoints,
    _checkpoint_id,
    _meta_path,
)


@pytest.fixture
def tmp_dir(tmp_path):
    """Provide a temporary directory for test data files."""
    return tmp_path


@pytest.fixture
def checkpoints_dir(tmp_path):
    """Provide a temporary checkpoints metadata directory."""
    cp_dir = tmp_path / "checkpoints_meta"
    cp_dir.mkdir()
    return cp_dir


@pytest.fixture(autouse=True)
def patch_data_dir(checkpoints_dir):
    """Patch get_data_dir to use the test-local checkpoints directory."""
    with patch("limacharlie.search_checkpoint.get_data_dir", return_value=str(checkpoints_dir)):
        yield


class TestGetDataDir:
    """Tests for checkpoint metadata directory path derivation.

    These tests exercise the paths module's get_checkpoint_dir()
    function which is now the single source of truth for checkpoint
    directory resolution.
    """

    @pytest.fixture(autouse=True)
    def _undo_autouse(self, patch_data_dir):
        """The class-level autouse still runs; we just ignore its effect
        by calling the paths module directly."""

    def test_default_config_dir(self, monkeypatch, tmp_path):
        """LC_CONFIG_DIR -> <dir>/search_checkpoints."""
        from limacharlie.paths import _reset_path_cache, get_checkpoint_dir
        config_dir = str(tmp_path / "lc_config")
        os.makedirs(config_dir, exist_ok=True)
        monkeypatch.setenv("LC_CONFIG_DIR", config_dir)
        monkeypatch.delenv("LC_CREDS_FILE", raising=False)
        monkeypatch.delenv("LC_LEGACY_CONFIG", raising=False)
        _reset_path_cache()
        result = get_checkpoint_dir()
        assert result == os.path.join(config_dir, "search_checkpoints")
        _reset_path_cache()

    def test_respects_lc_creds_file(self, monkeypatch):
        """Respects LC_CREDS_FILE: /foo/bar -> /foo/bar.d/search_checkpoints."""
        from limacharlie.paths import _reset_path_cache, get_checkpoint_dir
        monkeypatch.setenv("LC_CREDS_FILE", "/foo/bar")
        monkeypatch.delenv("LC_CONFIG_DIR", raising=False)
        monkeypatch.delenv("LC_LEGACY_CONFIG", raising=False)
        _reset_path_cache()
        result = get_checkpoint_dir()
        assert result == "/foo/bar.d/search_checkpoints"
        _reset_path_cache()

    def test_creds_file_is_directory(self, monkeypatch, tmp_path):
        """If LC_CREDS_FILE points to a directory, use <dir>/search_checkpoints/."""
        from limacharlie.paths import _reset_path_cache, get_checkpoint_dir
        config_dir = tmp_path / "config_as_dir"
        config_dir.mkdir()
        monkeypatch.setenv("LC_CREDS_FILE", str(config_dir))
        monkeypatch.delenv("LC_CONFIG_DIR", raising=False)
        monkeypatch.delenv("LC_LEGACY_CONFIG", raising=False)
        _reset_path_cache()
        result = get_checkpoint_dir()
        assert result == os.path.join(str(config_dir), "search_checkpoints")
        _reset_path_cache()


class TestCheckpointId:
    """Tests for _checkpoint_id helper."""

    def test_deterministic(self, tmp_dir):
        """Same path always produces the same ID."""
        path = str(tmp_dir / "data.jsonl")
        assert _checkpoint_id(path) == _checkpoint_id(path)

    def test_different_paths_different_ids(self, tmp_dir):
        """Different paths produce different IDs."""
        id1 = _checkpoint_id(str(tmp_dir / "a.jsonl"))
        id2 = _checkpoint_id(str(tmp_dir / "b.jsonl"))
        assert id1 != id2

    def test_relative_vs_absolute(self, tmp_dir, monkeypatch):
        """Relative path is resolved to absolute before hashing."""
        monkeypatch.chdir(tmp_dir)
        abs_id = _checkpoint_id(str(tmp_dir / "data.jsonl"))
        rel_id = _checkpoint_id("data.jsonl")
        assert abs_id == rel_id


class TestCheckpointWriter:
    """Tests for CheckpointWriter."""

    def test_creates_data_and_meta_files(self, tmp_dir):
        """Writer creates both data file and metadata file."""
        data_path = str(tmp_dir / "results.jsonl")
        with CheckpointWriter(data_path, "test query", 1000, 2000,
                              "event", None, "test-oid") as w:
            pass

        assert os.path.exists(data_path)
        meta_file = _meta_path(data_path)
        assert os.path.exists(meta_file)

    def test_refuses_existing_data_file(self, tmp_dir):
        """Raises FileExistsError if data file already exists."""
        data_path = str(tmp_dir / "existing.jsonl")
        with open(data_path, "w") as f:
            f.write("existing data\n")

        with pytest.raises(FileExistsError, match="already exists"):
            CheckpointWriter(data_path, "query", 1000, 2000, None, None, "oid")

    def test_refuses_existing_data_file_error_message(self, tmp_dir):
        """Error message mentions --resume, --force, and delete as options."""
        data_path = str(tmp_dir / "existing2.jsonl")
        with open(data_path, "w") as f:
            f.write("existing data\n")

        with pytest.raises(FileExistsError, match="--resume") as exc_info:
            CheckpointWriter(data_path, "query", 1000, 2000, None, None, "oid")
        msg = str(exc_info.value)
        assert "--force" in msg
        assert "delete" in msg

    def test_force_overwrites_existing_data_file(self, tmp_dir):
        """force=True overwrites existing data and metadata files."""
        data_path = str(tmp_dir / "overwrite.jsonl")
        # Create initial checkpoint
        with CheckpointWriter(data_path, "old query", 1000, 2000,
                              None, None, "oid") as w:
            w.write_result({"old": True})
            w.update_progress(1, 1, completed=True)

        # Force overwrite
        with CheckpointWriter(data_path, "new query", 3000, 4000,
                              "event", None, "oid", force=True) as w:
            w.write_result({"new": True})
            w.update_progress(1, 1, completed=True)

        meta, results = CheckpointReader.read(data_path)
        assert len(results) == 1
        assert results[0]["new"] is True
        assert meta["query"] == "new query"
        assert meta["start_time"] == 3000

    def test_force_works_when_no_existing_file(self, tmp_dir):
        """force=True works fine even when no file exists."""
        data_path = str(tmp_dir / "new_force.jsonl")
        with CheckpointWriter(data_path, "query", 1000, 2000,
                              None, None, "oid", force=True) as w:
            w.write_result({"a": 1})
        assert os.path.exists(data_path)

    def test_write_result_appends_jsonl(self, tmp_dir):
        """write_result appends JSON lines to data file."""
        data_path = str(tmp_dir / "results.jsonl")
        with CheckpointWriter(data_path, "query", 1000, 2000,
                              None, None, "oid") as w:
            w.write_result({"type": "events", "rows": [{"a": 1}]})
            w.write_result({"type": "events", "rows": [{"b": 2}]})

        with open(data_path) as f:
            lines = [line.strip() for line in f if line.strip()]
        assert len(lines) == 2
        assert json.loads(lines[0])["rows"] == [{"a": 1}]
        assert json.loads(lines[1])["rows"] == [{"b": 2}]

    def test_update_progress_updates_metadata(self, tmp_dir):
        """update_progress rewrites metadata atomically."""
        data_path = str(tmp_dir / "results.jsonl")
        with CheckpointWriter(data_path, "query", 1000, 2000,
                              "event", 50, "test-oid") as w:
            w.update_progress(page=2, result_count=10, completed=False)

            meta_file = _meta_path(data_path)
            with open(meta_file) as f:
                meta = json.load(f)
            assert meta["page"] == 2
            assert meta["result_count"] == 10
            assert meta["completed"] is False

            w.update_progress(page=3, result_count=20, completed=True)
            with open(meta_file) as f:
                meta = json.load(f)
            assert meta["page"] == 3
            assert meta["result_count"] == 20
            assert meta["completed"] is True

    def test_metadata_contains_all_fields(self, tmp_dir):
        """Metadata file has all required fields."""
        data_path = str(tmp_dir / "results.jsonl")
        with CheckpointWriter(data_path, "my query", 1000, 2000,
                              "detect", 100, "org-123") as w:
            pass

        meta_file = _meta_path(data_path)
        with open(meta_file) as f:
            meta = json.load(f)

        assert meta["version"] == 1
        assert meta["data_file"] == os.path.abspath(data_path)
        assert meta["query"] == "my query"
        assert meta["start_time"] == 1000
        assert meta["end_time"] == 2000
        assert meta["stream"] == "detect"
        assert meta["limit"] == 100
        assert meta["oid"] == "org-123"
        assert "created_at" in meta
        assert "updated_at" in meta
        assert meta["result_count"] == 0
        assert meta["page"] == 1
        assert meta["completed"] is False

    def test_creates_parent_directories(self, tmp_dir):
        """Writer creates parent directories for data file if needed."""
        data_path = str(tmp_dir / "subdir" / "deep" / "results.jsonl")
        with CheckpointWriter(data_path, "query", 1000, 2000,
                              None, None, "oid") as w:
            w.write_result({"test": True})
        assert os.path.exists(data_path)

    def test_flush_after_write(self, tmp_dir):
        """Data is flushed to disk after each write_result call."""
        data_path = str(tmp_dir / "results.jsonl")
        writer = CheckpointWriter(data_path, "query", 1000, 2000,
                                  None, None, "oid")
        writer.write_result({"a": 1})

        # Read before close - data should be flushed.
        with open(data_path) as f:
            content = f.read()
        assert '"a": 1' in content
        writer.close()


class TestCheckpointReader:
    """Tests for CheckpointReader."""

    def _create_checkpoint(self, tmp_dir, results, completed=False):
        """Helper to create a checkpoint with given results."""
        data_path = str(tmp_dir / "data.jsonl")
        with CheckpointWriter(data_path, "test query", 1000, 2000,
                              "event", None, "test-oid") as w:
            for r in results:
                w.write_result(r)
            w.update_progress(1, len(results), completed)
        return data_path

    def test_read_valid_checkpoint(self, tmp_dir):
        """Reads back metadata and results correctly."""
        results = [{"type": "events", "rows": [{"a": i}]} for i in range(3)]
        data_path = self._create_checkpoint(tmp_dir, results)

        meta, data = CheckpointReader.read(data_path)
        assert meta["query"] == "test query"
        assert meta["result_count"] == 3
        assert len(data) == 3
        assert data[0]["rows"] == [{"a": 0}]

    def test_read_empty_data_file(self, tmp_dir):
        """Empty data file returns empty results list."""
        data_path = self._create_checkpoint(tmp_dir, [])

        meta, data = CheckpointReader.read(data_path)
        assert len(data) == 0
        assert meta["result_count"] == 0

    def test_read_corrupted_last_line(self, tmp_dir):
        """Corrupt last line is gracefully skipped."""
        data_path = self._create_checkpoint(
            tmp_dir, [{"type": "events", "rows": [{"a": 1}]}]
        )
        # Append corrupt data
        with open(data_path, "a") as f:
            f.write('{"incomplete json\n')

        meta, data = CheckpointReader.read(data_path)
        # Should get the valid line, corrupt line is skipped
        assert len(data) == 1

    def test_read_corrupted_middle_line_raises(self, tmp_dir):
        """Corrupt line in the middle of the file raises ValueError."""
        data_path = self._create_checkpoint(
            tmp_dir, [{"type": "events", "rows": [{"a": 1}]}]
        )
        # Insert corrupt line followed by a valid line
        with open(data_path, "a") as f:
            f.write('corrupt middle line\n')
            f.write('{"type": "events", "rows": [{"b": 2}]}\n')

        with pytest.raises(ValueError, match="Corrupt line"):
            CheckpointReader.read(data_path)

    def test_count_results(self, tmp_dir):
        """count_results returns the line count without loading data."""
        results = [{"type": "events", "rows": [{"a": i}]} for i in range(5)]
        data_path = self._create_checkpoint(tmp_dir, results)
        assert CheckpointReader.count_results(data_path) == 5

    def test_count_results_empty_file(self, tmp_dir):
        """count_results returns 0 for an empty checkpoint."""
        data_path = self._create_checkpoint(tmp_dir, [])
        assert CheckpointReader.count_results(data_path) == 0

    def test_read_missing_data_file(self, tmp_dir):
        """Raises FileNotFoundError for missing data file."""
        with pytest.raises(FileNotFoundError):
            CheckpointReader.read(str(tmp_dir / "nonexistent.jsonl"))

    def test_iter_results_missing_data_file(self, tmp_dir):
        """iter_results raises FileNotFoundError for missing data file."""
        with pytest.raises(FileNotFoundError, match="data file not found"):
            list(CheckpointReader.iter_results(str(tmp_dir / "nonexistent.jsonl")))

    def test_read_missing_metadata(self, tmp_dir):
        """Raises FileNotFoundError for missing metadata."""
        data_path = str(tmp_dir / "orphan.jsonl")
        with open(data_path, "w") as f:
            f.write('{"a": 1}\n')

        with pytest.raises(FileNotFoundError, match="metadata not found"):
            CheckpointReader.read(data_path)

    def test_read_metadata_only(self, tmp_dir):
        """read_metadata returns just the metadata dict."""
        data_path = self._create_checkpoint(tmp_dir, [{"x": 1}])
        meta = CheckpointReader.read_metadata(data_path)
        assert meta["query"] == "test query"
        assert meta["start_time"] == 1000


class TestCheckpointResumer:
    """Tests for CheckpointResumer."""

    def _create_checkpoint(self, tmp_dir, results, completed=False):
        """Helper to create a checkpoint."""
        data_path = str(tmp_dir / "data.jsonl")
        with CheckpointWriter(data_path, "test query", 1000, 2000,
                              "event", None, "test-oid") as w:
            for r in results:
                w.write_result(r)
            w.update_progress(1, len(results), completed)
        return data_path

    def test_loads_existing_checkpoint(self, tmp_dir):
        """Resumer loads metadata and counts existing results."""
        results = [{"type": "events", "rows": [{"a": i}]} for i in range(5)]
        data_path = self._create_checkpoint(tmp_dir, results)

        resumer = CheckpointResumer(data_path)
        assert resumer.existing_count == 5
        assert resumer.metadata["query"] == "test query"

    def test_appends_new_results(self, tmp_dir):
        """Resumer appends new results to existing data file."""
        results = [{"type": "events", "rows": [{"a": 1}]}]
        data_path = self._create_checkpoint(tmp_dir, results)

        with CheckpointResumer(data_path) as resumer:
            resumer.write_result({"type": "events", "rows": [{"b": 2}]})
            resumer.update_progress(2, 2, completed=True)

        meta, data = CheckpointReader.read(data_path)
        assert len(data) == 2
        assert meta["result_count"] == 2
        assert meta["completed"] is True

    def test_missing_data_file_raises(self, tmp_dir):
        """Raises FileNotFoundError for missing data file."""
        with pytest.raises(FileNotFoundError):
            CheckpointResumer(str(tmp_dir / "missing.jsonl"))

    def test_missing_metadata_raises(self, tmp_dir):
        """Raises FileNotFoundError for orphan data file."""
        data_path = str(tmp_dir / "orphan.jsonl")
        with open(data_path, "w") as f:
            f.write('{"a": 1}\n')

        with pytest.raises(FileNotFoundError, match="metadata not found"):
            CheckpointResumer(data_path)


class TestListCheckpoints:
    """Tests for list_checkpoints function."""

    def test_empty_directory(self, checkpoints_dir):
        """Returns empty list when no checkpoints exist."""
        assert list_checkpoints() == []

    def test_lists_checkpoints(self, tmp_dir, checkpoints_dir):
        """Returns metadata for all checkpoints."""
        # Create two checkpoints
        path1 = str(tmp_dir / "search1.jsonl")
        with CheckpointWriter(path1, "query 1", 1000, 2000,
                              "event", None, "oid-1") as w:
            w.write_result({"a": 1})
            w.update_progress(1, 1, completed=True)

        path2 = str(tmp_dir / "search2.jsonl")
        with CheckpointWriter(path2, "query 2", 3000, 4000,
                              "detect", 50, "oid-2") as w:
            w.write_result({"b": 2})
            w.write_result({"c": 3})
            w.update_progress(1, 2, completed=False)

        cps = list_checkpoints()
        assert len(cps) == 2

        # Check that data_file_exists is set
        for cp in cps:
            assert "data_file_exists" in cp

    def test_cleanup_removes_stale_metadata(self, tmp_dir, checkpoints_dir):
        """Stale metadata (missing data file) is deleted on list with cleanup=True."""
        path = str(tmp_dir / "temp.jsonl")
        with CheckpointWriter(path, "query", 1000, 2000,
                              None, None, "oid") as w:
            pass

        meta_file = _meta_path(path)
        assert os.path.exists(meta_file)

        # Delete the data file but leave metadata
        os.unlink(path)

        # Default cleanup=True should remove stale metadata
        cps = list_checkpoints()
        assert len(cps) == 0
        assert not os.path.exists(meta_file)

    def test_cleanup_false_preserves_stale_metadata(self, tmp_dir, checkpoints_dir):
        """With cleanup=False, stale metadata is preserved and reported."""
        path = str(tmp_dir / "temp2.jsonl")
        with CheckpointWriter(path, "query", 1000, 2000,
                              None, None, "oid") as w:
            pass

        meta_file = _meta_path(path)
        os.unlink(path)

        cps = list_checkpoints(cleanup=False)
        assert len(cps) == 1
        assert cps[0]["data_file_exists"] is False
        assert os.path.exists(meta_file)

    def test_cleanup_removes_corrupt_metadata(self, checkpoints_dir):
        """Corrupt metadata files are deleted on list with cleanup=True."""
        corrupt_path = os.path.join(str(checkpoints_dir), "corrupt.meta.json")
        with open(corrupt_path, "w") as f:
            f.write("not valid json{{{")

        cps = list_checkpoints(cleanup=True)
        assert len(cps) == 0
        assert not os.path.exists(corrupt_path)

    def test_cleanup_preserves_live_checkpoints(self, tmp_dir, checkpoints_dir):
        """Cleanup only removes stale/corrupt entries, not live ones."""
        # Create a live checkpoint
        live_path = str(tmp_dir / "live.jsonl")
        with CheckpointWriter(live_path, "query", 1000, 2000,
                              None, None, "oid") as w:
            w.write_result({"a": 1})

        # Create a stale checkpoint
        stale_path = str(tmp_dir / "stale.jsonl")
        with CheckpointWriter(stale_path, "query2", 3000, 4000,
                              None, None, "oid") as w:
            pass
        os.unlink(stale_path)

        cps = list_checkpoints(cleanup=True)
        assert len(cps) == 1
        assert cps[0]["data_file"] == os.path.abspath(live_path)

    def test_nonexistent_directory(self, tmp_path):
        """Returns empty list when checkpoints directory does not exist."""
        with patch("limacharlie.search_checkpoint.get_data_dir",
                   return_value=str(tmp_path / "does_not_exist")):
            assert list_checkpoints() == []


class TestCheckpointPermissions:
    """Tests for secure file and directory permissions.

    Verifies that checkpoint directories and files are created with
    owner-only permissions to protect sensitive search telemetry.
    On Windows, permissions are best-effort (relies on home dir ACLs).
    """

    @pytest.mark.skipif(os.name == "nt", reason="Unix permission model")
    def test_metadata_dir_is_owner_only(self, tmp_dir, checkpoints_dir):
        """Metadata directory has 0o700 permissions (owner rwx only)."""
        # The autouse patch uses a pre-created dir, but we need to test
        # the real secure_makedirs path. Create a fresh checkpoint that
        # triggers directory creation.
        import limacharlie.search_checkpoint as cp_module
        fresh_dir = str(tmp_dir / "fresh_meta")
        with patch("limacharlie.search_checkpoint.get_data_dir", return_value=fresh_dir):
            data_path = str(tmp_dir / "perms_test.jsonl")
            with CheckpointWriter(data_path, "query", 1000, 2000,
                                  None, None, "oid") as w:
                pass

        assert os.path.isdir(fresh_dir)
        mode = os.stat(fresh_dir).st_mode & 0o777
        assert mode == 0o700, f"Expected 0o700, got {oct(mode)}"

    @pytest.mark.skipif(os.name == "nt", reason="Unix permission model")
    def test_metadata_file_is_owner_only(self, tmp_dir):
        """Metadata .meta.json file has 0o600 permissions."""
        data_path = str(tmp_dir / "meta_perms.jsonl")
        with CheckpointWriter(data_path, "query", 1000, 2000,
                              None, None, "oid") as w:
            pass

        meta_file = _meta_path(data_path)
        mode = os.stat(meta_file).st_mode & 0o777
        assert mode == 0o600, f"Expected 0o600, got {oct(mode)}"

    @pytest.mark.skipif(os.name == "nt", reason="Unix permission model")
    def test_data_file_is_owner_only(self, tmp_dir):
        """Data JSONL file has 0o600 permissions (contains sensitive telemetry)."""
        data_path = str(tmp_dir / "data_perms.jsonl")
        with CheckpointWriter(data_path, "query", 1000, 2000,
                              None, None, "oid") as w:
            w.write_result({"sensitive": "data"})

        mode = os.stat(data_path).st_mode & 0o777
        assert mode == 0o600, f"Expected 0o600, got {oct(mode)}"

    @pytest.mark.skipif(os.name == "nt", reason="Unix permission model")
    def test_nested_metadata_dirs_are_all_secure(self, tmp_dir):
        """All directories in the metadata path have 0o700 permissions.

        The path ~/.limacharlie.d/search_checkpoints/ has two levels of
        directories that both need to be secured.
        """
        import limacharlie.search_checkpoint as cp_module
        # Create a deep fresh path to test multi-level creation.
        base = str(tmp_dir / "deep_meta" / "level1" / "level2")
        with patch("limacharlie.search_checkpoint.get_data_dir", return_value=base):
            data_path = str(tmp_dir / "deep_perms.jsonl")
            with CheckpointWriter(data_path, "query", 1000, 2000,
                                  None, None, "oid") as w:
                pass

        # Check each created directory.
        current = base
        while current != str(tmp_dir / "deep_meta"):
            if os.path.isdir(current):
                mode = os.stat(current).st_mode & 0o777
                assert mode == 0o700, f"Dir {current} has {oct(mode)}, expected 0o700"
            parent = os.path.dirname(current)
            if parent == current:
                break
            current = parent

    @pytest.mark.skipif(os.name == "nt", reason="Unix permission model")
    def test_force_overwrite_preserves_secure_permissions(self, tmp_dir):
        """Force-overwriting a checkpoint preserves secure file permissions."""
        data_path = str(tmp_dir / "force_perms.jsonl")
        with CheckpointWriter(data_path, "query", 1000, 2000,
                              None, None, "oid") as w:
            w.write_result({"old": True})

        with CheckpointWriter(data_path, "query2", 3000, 4000,
                              None, None, "oid", force=True) as w:
            w.write_result({"new": True})

        data_mode = os.stat(data_path).st_mode & 0o777
        assert data_mode == 0o600, f"Data file: expected 0o600, got {oct(data_mode)}"

        meta_file = _meta_path(data_path)
        meta_mode = os.stat(meta_file).st_mode & 0o777
        assert meta_mode == 0o600, f"Meta file: expected 0o600, got {oct(meta_mode)}"

    def test_works_on_all_platforms(self, tmp_dir):
        """Checkpoint creation succeeds on all platforms regardless of permission model.

        This test runs on all platforms (including Windows) to verify that
        the secure permission calls don't crash, even if they have limited
        effect on non-Unix systems.
        """
        data_path = str(tmp_dir / "crossplat.jsonl")
        with CheckpointWriter(data_path, "query", 1000, 2000,
                              None, None, "oid") as w:
            w.write_result({"a": 1})
            w.update_progress(1, 1, completed=True)

        assert os.path.exists(data_path)
        meta, results = CheckpointReader.read(data_path)
        assert len(results) == 1
        assert meta["completed"] is True
