"""Checkpoint/resume support for long-running search queries.

Provides incremental persistence of search results so that interrupted
searches can be resumed without losing already-fetched data.

Architecture:
- Data file (user-specified path): Append-only JSONL, one SearchResult
  dict per line. This is the user's data - lives wherever they want.
- Metadata file (~/.limacharlie/checkpoints/<id>.meta.json): Query
  parameters, progress state (page, result count, completed). Stored
  in the standard LimaCharlie config area.

The metadata file is rewritten atomically (tempfile + rename) each time
a page completes. The data file is append-only and flushed after each
write. On resume, the query is re-run and already-fetched results are
skipped.

Resume mechanism: the pagination token contains a cursor encoding the
position in the result set. On resume, a fresh search is initiated and
the server re-runs the query starting from the cursor position. This
means resume works even after long delays between sessions - there is
no server-side TTL that limits when a checkpoint can be resumed.

Concurrency model: single-writer. No file locking. If two processes
write to the same checkpoint simultaneously, results will be corrupted.
This is acceptable since search queries are interactive CLI operations.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import time
from collections.abc import Generator
from datetime import datetime, timezone
from typing import Any

from .config import ENV_CREDS_FILE, CONFIG_FILE_PATH
from .file_utils import (
    _reject_symlink,
    atomic_write,
    secure_file_permissions,
    secure_makedirs,
)


def get_data_dir() -> str:
    """Return the directory for checkpoint metadata files.

    Path resolution:
    - Default: ~/.limacharlie/search_checkpoints/
      Uses a directory named after the config file with a .d suffix
      to avoid conflicting with the flat config file. For the default
      ~/.limacharlie config, this gives ~/.limacharlie.d/search_checkpoints/.
      When the config eventually migrates to a directory layout
      (~/.limacharlie/ as a dir), this naturally becomes
      ~/.limacharlie/search_checkpoints/.
    - Respects LC_CREDS_FILE: if config is at /foo/bar, checkpoints go
      to /foo/bar.d/search_checkpoints/.

    Returns:
        Absolute path to the checkpoints directory.
    """
    config_path = os.environ.get(ENV_CREDS_FILE, CONFIG_FILE_PATH)
    config_dir = os.path.dirname(config_path)
    config_base = os.path.basename(config_path)

    # If the config path is already a directory (future layout or custom),
    # use <config_path>/search_checkpoints/ directly.
    if os.path.isdir(config_path):
        return os.path.join(config_path, "search_checkpoints")

    # Config path is a flat file (current layout) or doesn't exist yet.
    # Use <config_path>.d/search_checkpoints/ to avoid conflict with the
    # flat file. For ~/.limacharlie -> ~/.limacharlie.d/search_checkpoints/.
    return os.path.join(config_dir, config_base + ".d", "search_checkpoints")


def _checkpoint_id(data_path: str) -> str:
    """Compute a checkpoint ID from the absolute path of the data file.

    Uses SHA-256 hash of the absolute path so metadata and data are
    always paired regardless of the data file location.

    Args:
        data_path: Absolute path to the JSONL data file.

    Returns:
        Hex-encoded SHA-256 hash string.
    """
    return hashlib.sha256(os.path.abspath(data_path).encode()).hexdigest()


def _meta_path(data_path: str) -> str:
    """Return the metadata file path for a given data file.

    Args:
        data_path: Absolute path to the JSONL data file.

    Returns:
        Absolute path to the metadata JSON file.
    """
    return os.path.join(get_data_dir(), _checkpoint_id(data_path) + ".meta.json")


class CheckpointWriter:
    """Incrementally writes search results to a JSONL data file
    and maintains a metadata file for resume support.

    Data file: append-only JSONL at user-specified path.
    Metadata file: atomic JSON in the checkpoints directory.

    Usage:
        writer = CheckpointWriter(data_path, query, start_time, end_time,
                                  stream, limit, oid)
        for result in search.execute(...):
            writer.write_result(result)
            writer.update_progress(page, result_count, completed=False)
        writer.update_progress(page, result_count, completed=True)
        writer.close()
    """

    def __init__(
        self,
        data_path: str,
        query: str,
        start_time: int,
        end_time: int,
        stream: str | None,
        limit: int | None,
        oid: str,
        force: bool = False,
    ) -> None:
        """Initialize checkpoint writer.

        Creates the data file and metadata file. Raises if the data file
        already exists unless force=True (which overwrites it).

        Args:
            data_path: Path to the JSONL data file.
            query: LCQL query string.
            start_time: Start time (unix seconds).
            end_time: End time (unix seconds).
            stream: Stream type or None.
            limit: Result limit or None.
            oid: Organization ID.
            force: If True, overwrite existing data file and metadata.

        Raises:
            FileExistsError: If data_path already exists and force is False.
        """
        self._data_path = os.path.abspath(data_path)
        self._meta_path = _meta_path(self._data_path)

        # Reject symlinks at the data file path to prevent symlink attacks.
        _reject_symlink(self._data_path)

        if os.path.exists(self._data_path) and not force:
            raise FileExistsError(
                f"Checkpoint data file already exists: {self._data_path}. "
                "Use --resume to continue, --force to overwrite, "
                "or delete the file and retry."
            )

        # If force, remove existing data and metadata files.
        if force and os.path.exists(self._data_path):
            os.unlink(self._data_path)
            if os.path.exists(self._meta_path):
                os.unlink(self._meta_path)

        # Ensure parent directories exist.
        # The data file dir uses regular makedirs (user controls the path).
        data_dir = os.path.dirname(self._data_path)
        if data_dir:
            os.makedirs(data_dir, exist_ok=True)

        # The metadata dir is in ~/.limacharlie.d/ and must be owner-only.
        meta_dir = os.path.dirname(self._meta_path)
        if meta_dir:
            secure_makedirs(meta_dir)

        now = datetime.now(timezone.utc).isoformat()
        self._metadata: dict[str, Any] = {
            "version": 1,
            "data_file": self._data_path,
            "query": query,
            "start_time": start_time,
            "end_time": end_time,
            "stream": stream,
            "limit": limit,
            "oid": oid,
            "created_at": now,
            "updated_at": now,
            "result_count": 0,
            "total_events": 0,
            "page": 1,
            "last_token": None,
            "completed": False,
        }

        # Create the data file with secure permissions. Use O_CREAT|O_EXCL
        # when not forcing to atomically prevent TOCTOU races (another process
        # creating the file between our exists-check and open). On Unix,
        # O_NOFOLLOW also rejects symlinks at open time.
        # Search results may contain sensitive telemetry, so restrict
        # access to owner-only (0o600).
        open_flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
        if not force:
            open_flags |= os.O_EXCL
        if os.name != "nt" and hasattr(os, "O_NOFOLLOW"):
            open_flags |= os.O_NOFOLLOW
        try:
            fd = os.open(self._data_path, open_flags, stat.S_IRUSR | stat.S_IWUSR)
        except FileExistsError:
            raise FileExistsError(
                f"Checkpoint data file already exists: {self._data_path}. "
                "Use --resume to continue, --force to overwrite, "
                "or delete the file and retry."
            )
        self._file = os.fdopen(fd, "a", encoding="utf-8")
        secure_file_permissions(self._data_path)

        # Write initial metadata (atomic_write handles its own permissions).
        self._write_metadata()

    def write_result(self, result: dict[str, Any]) -> None:
        """Append a single search result to the data file.

        Each result is written as a single JSON line, flushed immediately.

        Args:
            result: A SearchResult dict from the API.
        """
        self._file.write(json.dumps(result, default=str) + "\n")
        self._file.flush()

    def update_progress(self, page: int, result_count: int, completed: bool,
                        last_token: str | None = None,
                        total_events: int | None = None,
                        last_event_ts: int | None = None) -> None:
        """Update checkpoint metadata with current progress.

        Rewrites the metadata file atomically.

        Args:
            page: Current page number.
            result_count: Total results (SearchResult wrappers) written so far.
            completed: Whether the search has completed.
            last_token: The most recent nextToken from results, used for
                server-side resume.
            total_events: Cumulative count of individual event rows across
                all results fetched so far.
            last_event_ts: Timestamp (milliseconds epoch) of the most recent
                event in the last fetched page, used to show progress through
                the time range.
        """
        self._metadata["page"] = page
        self._metadata["result_count"] = result_count
        self._metadata["completed"] = completed
        if last_token is not None:
            self._metadata["last_token"] = last_token
        if total_events is not None:
            self._metadata["total_events"] = total_events
        if last_event_ts is not None:
            self._metadata["last_event_ts"] = last_event_ts
        self._metadata["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._write_metadata()

    def close(self) -> None:
        """Close the data file handle."""
        if self._file and not self._file.closed:
            self._file.close()

    def _write_metadata(self) -> None:
        """Atomically write metadata to disk."""
        content = json.dumps(self._metadata, indent=2).encode("utf-8")
        atomic_write(self._meta_path, content)

    def __enter__(self) -> "CheckpointWriter":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


class CheckpointReader:
    """Reads checkpoint metadata and data for resume.

    Provides both eager (``read``) and lazy (``iter_results``) access
    to checkpoint data. Use ``iter_results`` for large checkpoints to
    avoid loading all results into memory at once.

    Handles corrupt last line in data file gracefully - if the last
    line is not valid JSON (e.g. from a crash mid-write), it is
    silently dropped.
    """

    @staticmethod
    def iter_results(data_path: str) -> Generator[dict[str, Any], None, None]:
        """Lazily iterate over results in the checkpoint data file.

        Streams one JSONL line at a time without buffering the entire
        file in memory. Suitable for large checkpoints.

        Only the very last line is allowed to be corrupt (crash mid-write).
        Corrupt lines in the middle raise ValueError.

        Args:
            data_path: Absolute path to the JSONL data file.

        Yields:
            Parsed result dicts, one per JSONL line.

        Raises:
            FileNotFoundError: If data file does not exist.
            ValueError: If a non-last line is corrupt.
        """
        abs_path = os.path.abspath(data_path)
        if not os.path.exists(abs_path):
            raise FileNotFoundError(
                f"Checkpoint data file not found: {abs_path}"
            )

        # We need to know whether a corrupt line is the last one.
        # Use a one-line lookahead: parse the previous line only after
        # confirming the current line exists (meaning previous wasn't last).
        pending: tuple[int, str] | None = None  # (line_number, raw_line)
        line_num = 0
        with open(abs_path, "r", encoding="utf-8") as f:
            for raw_line in f:
                stripped = raw_line.strip()
                if not stripped:
                    continue
                line_num += 1

                if pending is not None:
                    # Previous line is NOT the last - must be valid.
                    prev_num, prev_line = pending
                    try:
                        yield json.loads(prev_line)
                    except json.JSONDecodeError:
                        raise ValueError(
                            f"Corrupt line {prev_num} in checkpoint data file "
                            f"{abs_path} (only the last line may be corrupt)"
                        )

                pending = (line_num, stripped)

        # Process the final line - tolerate corruption.
        if pending is not None:
            _, last_line = pending
            try:
                yield json.loads(last_line)
            except json.JSONDecodeError:
                # Last line corrupt (crash mid-write) - skip silently.
                pass

    @staticmethod
    def read(data_path: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Read checkpoint metadata and data file contents.

        Loads all results into memory. For large checkpoints, prefer
        ``iter_results`` combined with ``read_metadata``.

        Args:
            data_path: Absolute path to the JSONL data file.

        Returns:
            Tuple of (metadata dict, list of result dicts from data file).

        Raises:
            FileNotFoundError: If data file or metadata file is missing.
        """
        metadata = CheckpointReader.read_metadata(data_path)

        abs_path = os.path.abspath(data_path)
        results = list(CheckpointReader.iter_results(abs_path))
        return metadata, results

    @staticmethod
    def read_metadata(data_path: str) -> dict[str, Any]:
        """Read only the checkpoint metadata (not the data file).

        Uses safe_open_read to reject symlinks at the metadata path.

        Args:
            data_path: Absolute path to the JSONL data file.

        Returns:
            Metadata dict.

        Raises:
            FileNotFoundError: If metadata file is missing.
        """
        from .file_utils import safe_open_read as _safe_read
        abs_path = os.path.abspath(data_path)
        meta_file = _meta_path(abs_path)
        if not os.path.exists(meta_file):
            raise FileNotFoundError(
                f"Checkpoint metadata not found for: {abs_path}"
            )
        return json.loads(_safe_read(meta_file))

    @staticmethod
    def count_results(data_path: str) -> int:
        """Count results in the data file without loading them into memory.

        Counts non-empty lines. Used by CheckpointResumer to determine
        the skip count without loading all results.

        Args:
            data_path: Absolute path to the JSONL data file.

        Returns:
            Number of result lines in the data file.
        """
        count = 0
        with open(data_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    count += 1
        return count


class CheckpointResumer:
    """Resumes a search from a checkpoint.

    Re-opens the data file for appending and updates the existing
    metadata file as new results arrive.
    """

    def __init__(self, data_path: str) -> None:
        """Initialize from an existing checkpoint.

        Args:
            data_path: Path to the existing JSONL data file.

        Raises:
            FileNotFoundError: If data file or metadata is missing.
        """
        self._data_path = os.path.abspath(data_path)
        self._meta_path = _meta_path(self._data_path)

        # Read metadata only; count results without loading all data
        # into memory (checkpoints can be very large).
        self._metadata = CheckpointReader.read_metadata(self._data_path)
        if not os.path.exists(self._data_path):
            raise FileNotFoundError(
                f"Checkpoint data file not found: {self._data_path}"
            )
        self._existing_count = CheckpointReader.count_results(self._data_path)
        self._file: Any = None

    @property
    def metadata(self) -> dict[str, Any]:
        """The checkpoint metadata dict."""
        return self._metadata

    @property
    def existing_count(self) -> int:
        """Number of results already in the data file."""
        return self._existing_count

    def open(self) -> None:
        """Open the data file for appending. Rejects symlinks."""
        _reject_symlink(self._data_path)
        self._file = open(self._data_path, "a", encoding="utf-8")

    def write_result(self, result: dict[str, Any]) -> None:
        """Append a single search result to the data file.

        Args:
            result: A SearchResult dict from the API.
        """
        self._file.write(json.dumps(result, default=str) + "\n")
        self._file.flush()

    def update_progress(self, page: int, result_count: int, completed: bool,
                        last_token: str | None = None,
                        total_events: int | None = None,
                        last_event_ts: int | None = None) -> None:
        """Update checkpoint metadata with current progress.

        Args:
            page: Current page number.
            result_count: Total results written so far.
            completed: Whether the search has completed.
            last_token: The most recent nextToken for server-side resume.
            total_events: Cumulative count of individual event rows.
            last_event_ts: Timestamp (ms epoch) of most recent event.
        """
        self._metadata["page"] = page
        self._metadata["result_count"] = result_count
        self._metadata["completed"] = completed
        if last_token is not None:
            self._metadata["last_token"] = last_token
        if total_events is not None:
            self._metadata["total_events"] = total_events
        if last_event_ts is not None:
            self._metadata["last_event_ts"] = last_event_ts
        self._metadata["updated_at"] = datetime.now(timezone.utc).isoformat()
        content = json.dumps(self._metadata, indent=2).encode("utf-8")
        atomic_write(self._meta_path, content)

    def close(self) -> None:
        """Close the data file handle."""
        if self._file and not self._file.closed:
            self._file.close()

    def __enter__(self) -> "CheckpointResumer":
        self.open()
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


def list_checkpoints(
    cleanup: bool = True,
    debug_fn: Any = None,
) -> list[dict[str, Any]]:
    """List all checkpoint metadata files.

    Scans the checkpoints directory and reads each .meta.json file.
    When cleanup=True (default), automatically deletes stale metadata
    files whose data files no longer exist on disk.

    Args:
        cleanup: If True, delete metadata for checkpoints whose data
            file has been removed. Default True.
        debug_fn: Optional callback for debug messages.

    Returns:
        List of metadata dicts for live checkpoints. Corrupt and stale
        metadata files are cleaned up silently.
    """
    data_dir = get_data_dir()
    if debug_fn:
        debug_fn(f"Checkpoint metadata dir: {data_dir}")
    if not os.path.isdir(data_dir):
        if debug_fn:
            debug_fn("Checkpoint metadata dir does not exist")
        return []

    checkpoints: list[dict[str, Any]] = []
    for name in sorted(os.listdir(data_dir)):
        if not name.endswith(".meta.json"):
            continue
        path = os.path.join(data_dir, name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                meta = json.load(f)
        except (json.JSONDecodeError, OSError, KeyError):
            # Corrupt metadata - clean up.
            if cleanup:
                if debug_fn:
                    debug_fn(f"Removing corrupt checkpoint metadata: {path}")
                try:
                    os.unlink(path)
                except OSError:
                    pass
            continue

        data_file = meta.get("data_file", "")
        # Validate data_file is an absolute path to prevent path traversal
        # from malicious or corrupt metadata files.
        if not data_file or not os.path.isabs(data_file):
            if cleanup:
                if debug_fn:
                    debug_fn(f"Removing metadata with invalid data_file path: {data_file!r}")
                try:
                    os.unlink(path)
                except OSError:
                    pass
            continue
        data_exists = os.path.exists(data_file)

        if not data_exists and cleanup:
            # Data file has been deleted - clean up stale metadata.
            if debug_fn:
                debug_fn(f"Cleaning up stale checkpoint metadata (data file missing): {data_file}")
            try:
                os.unlink(path)
            except OSError:
                pass
            continue

        meta["data_file_exists"] = data_exists
        if data_exists:
            try:
                meta["data_file_size"] = os.path.getsize(data_file)
            except OSError:
                meta["data_file_size"] = None
        else:
            meta["data_file_size"] = None
        checkpoints.append(meta)

    return checkpoints
