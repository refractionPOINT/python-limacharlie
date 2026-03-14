"""Cross-platform file security and atomic write utilities.

Provides secure file permission management and atomic write operations
that work across Unix (Linux/macOS) and Windows. Used by config.py and
jwt_cache.py to safely persist sensitive credential data.

Key invariants:
- Files written via atomic_write() are never partially written (readers
  see either the old content or the new content, never a partial state).
- File permissions are restricted to owner-only access (0o600 on Unix).
- Symlinks are rejected on read and write paths to prevent symlink attacks
  where an attacker places a symlink at the expected path to redirect
  writes to an arbitrary file (e.g. overwriting ~/.ssh/authorized_keys).

Security model:
- atomic_write() refuses to write through symlinks at the target path.
- safe_open_read() refuses to read through symlinks.
- secure_file_permissions() restricts access to owner-only.
- These mitigations protect against local attackers who can create symlinks
  in directories writable by the current user (e.g. shared /tmp mounts,
  misconfigured home directories). They do NOT protect against root-level
  attackers who can modify the filesystem arbitrarily.
"""

from __future__ import annotations

import os
import stat
import tempfile


def _reject_symlink(path: str) -> None:
    """Raise if path is a symlink or contains symlinks in parent components.

    Prevents symlink-based attacks where an attacker places a symlink at the
    expected path to redirect reads/writes to an arbitrary file.

    Only checks the final component and one level of parent. We don't
    walk the entire path since we trust the OS home directory root.

    Args:
        path: file path to check.

    Raises:
        OSError: if path or its immediate parent is a symlink.
    """
    if os.path.islink(path):
        raise OSError(f"Refusing to operate on symlink: {path}")
    parent = os.path.dirname(path)
    if parent and os.path.islink(parent):
        raise OSError(f"Refusing to operate through symlinked directory: {parent}")


def secure_file_permissions(path: str) -> None:
    """Restrict file permissions to owner-only read/write access.

    On Unix: sets mode to 0o600 and chowns to current user/group.
    On Windows: sets user read/write via os.chmod (limited but functional -
    Windows home directories are already ACL-restricted by default).

    Args:
        path: absolute path to the file to secure.
    """
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    if os.name != "nt":
        os.chown(path, os.getuid(), os.getgid())


def safe_open_read(path: str) -> bytes:
    """Read a file's contents, rejecting symlinks atomically.

    On Unix, uses O_NOFOLLOW to atomically reject symlinks at open time,
    preventing TOCTOU races where an attacker swaps a regular file for a
    symlink between the check and the open. On Windows, falls back to a
    pre-check (symlinks require admin privileges on Windows, so the
    TOCTOU window is not exploitable in practice).

    Args:
        path: absolute path to the file to read.

    Returns:
        File contents as bytes.

    Raises:
        OSError: if path is a symlink or doesn't exist.
    """
    _reject_symlink(path)
    if os.name != "nt" and hasattr(os, "O_NOFOLLOW"):
        # O_NOFOLLOW makes the kernel reject symlinks atomically,
        # closing the TOCTOU window between _reject_symlink and open.
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            # os.fdopen takes ownership of fd on success and will close
            # it when the file object is closed.
            with os.fdopen(fd, "rb") as f:
                return f.read()
        except Exception:
            # If os.fdopen fails before taking ownership, close fd manually
            # to prevent a leak. Use try/except since fd may already be
            # closed if fdopen partially succeeded.
            try:
                os.close(fd)
            except OSError:
                pass
            raise
    else:
        with open(path, "rb") as f:
            return f.read()


def atomic_write(path: str, content: bytes) -> None:
    """Atomically write content to a file with secure permissions.

    Writes to a temporary file in the same directory, sets secure
    permissions, then atomically moves into place via os.replace().
    This prevents readers from seeing partial content on all platforms
    (os.replace is atomic on both POSIX and Windows).

    Refuses to write if the target path is a symlink, to prevent
    symlink attacks that redirect writes to arbitrary files.

    Args:
        path: absolute path to the destination file.
        content: bytes to write.

    Raises:
        OSError: if path is a symlink.
    """
    _reject_symlink(path)
    parent = os.path.dirname(path) or "."
    fd, tmp_path = tempfile.mkstemp(dir=parent)
    try:
        try:
            secure_file_permissions(tmp_path)
            os.write(fd, content)
        finally:
            os.close(fd)
        os.replace(tmp_path, path)
    finally:
        # Clean up temp file if it still exists (replace succeeded = gone,
        # but if an error happened before replace, it may still be here).
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
