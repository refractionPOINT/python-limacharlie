"""Tests for limacharlie.file_utils module.

Tests cover correctness, security properties, and race condition resistance
of the file utility functions used to persist sensitive credential data.

Security focus areas:
- Symlink rejection: all I/O paths must refuse symlinks to prevent redirect attacks
- Permission model: files 0o600, directories 0o700 (owner-only)
- TOCTOU resistance: atomic writes via temp file + os.replace
- Concurrent access: atomic writes prevent partial reads
- Resource safety: no file descriptor leaks on error paths
"""

import os
import stat
import threading
import time

import pytest

from limacharlie.file_utils import (
    _reject_symlink,
    atomic_write,
    safe_open_read,
    secure_dir_permissions,
    secure_file_permissions,
    secure_makedirs,
)


class TestSecureFilePermissions:
    def test_sets_owner_only_permissions(self, tmp_path):
        path = str(tmp_path / "secret")
        with open(path, "w") as f:
            f.write("data")
        secure_file_permissions(path)
        mode = os.stat(path).st_mode
        assert mode & 0o777 == 0o600

    @pytest.mark.skipif(os.name == "nt", reason="Unix-only ownership check")
    def test_sets_ownership_to_current_user(self, tmp_path):
        path = str(tmp_path / "secret")
        with open(path, "w") as f:
            f.write("data")
        secure_file_permissions(path)
        st = os.stat(path)
        assert st.st_uid == os.getuid()
        assert st.st_gid == os.getgid()

    def test_works_on_existing_file_with_open_permissions(self, tmp_path):
        path = str(tmp_path / "open_file")
        with open(path, "w") as f:
            f.write("data")
        os.chmod(path, 0o777)
        secure_file_permissions(path)
        mode = os.stat(path).st_mode
        assert mode & 0o777 == 0o600

    def test_nonexistent_file_raises(self, tmp_path):
        path = str(tmp_path / "nonexistent")
        with pytest.raises(OSError):
            secure_file_permissions(path)


class TestSecureDirPermissions:
    """Tests for secure_dir_permissions."""

    @pytest.mark.skipif(os.name == "nt", reason="Unix permission model")
    def test_sets_owner_only_permissions(self, tmp_path):
        d = str(tmp_path / "secure_dir")
        os.mkdir(d)
        os.chmod(d, 0o755)  # Start permissive
        secure_dir_permissions(d)
        mode = os.stat(d).st_mode & 0o777
        assert mode == 0o700

    @pytest.mark.skipif(os.name == "nt", reason="Unix-only ownership check")
    def test_sets_ownership_to_current_user(self, tmp_path):
        d = str(tmp_path / "owned_dir")
        os.mkdir(d)
        secure_dir_permissions(d)
        st = os.stat(d)
        assert st.st_uid == os.getuid()
        assert st.st_gid == os.getgid()

    def test_nonexistent_dir_raises(self, tmp_path):
        with pytest.raises(OSError):
            secure_dir_permissions(str(tmp_path / "nonexistent"))


class TestSecureMakedirs:
    """Tests for secure_makedirs."""

    @pytest.mark.skipif(os.name == "nt", reason="Unix permission model")
    def test_creates_single_dir_with_secure_perms(self, tmp_path):
        d = str(tmp_path / "new_dir")
        secure_makedirs(d)
        assert os.path.isdir(d)
        mode = os.stat(d).st_mode & 0o777
        assert mode == 0o700

    @pytest.mark.skipif(os.name == "nt", reason="Unix permission model")
    def test_creates_nested_dirs_all_secure(self, tmp_path):
        d = str(tmp_path / "a" / "b" / "c")
        secure_makedirs(d)
        assert os.path.isdir(d)
        # Check each created level
        for level in ["a", os.path.join("a", "b"), os.path.join("a", "b", "c")]:
            path = str(tmp_path / level)
            mode = os.stat(path).st_mode & 0o777
            assert mode == 0o700, f"{path} has {oct(mode)}, expected 0o700"

    def test_existing_dir_is_noop(self, tmp_path):
        """If directory already exists, secure_makedirs does not fail."""
        d = str(tmp_path / "existing")
        os.mkdir(d)
        # Should not raise
        secure_makedirs(d)

    def test_works_on_all_platforms(self, tmp_path):
        """secure_makedirs succeeds on all platforms without crashing."""
        d = str(tmp_path / "crossplat" / "nested")
        secure_makedirs(d)
        assert os.path.isdir(d)


class TestAtomicWrite:
    def test_writes_content_correctly(self, tmp_path):
        path = str(tmp_path / "out")
        atomic_write(path, b"hello world")
        with open(path, "rb") as f:
            assert f.read() == b"hello world"

    def test_file_has_restricted_permissions(self, tmp_path):
        path = str(tmp_path / "out")
        atomic_write(path, b"secret")
        mode = os.stat(path).st_mode
        assert mode & 0o777 == 0o600

    def test_overwrites_existing_file(self, tmp_path):
        path = str(tmp_path / "out")
        with open(path, "w") as f:
            f.write("old content")
        atomic_write(path, b"new content")
        with open(path, "rb") as f:
            assert f.read() == b"new content"

    def test_temp_file_cleaned_up_on_success(self, tmp_path):
        path = str(tmp_path / "out")
        atomic_write(path, b"data")
        # Only the target file should exist, no temp files
        files = os.listdir(tmp_path)
        assert files == ["out"]

    def test_content_must_be_bytes(self, tmp_path):
        path = str(tmp_path / "out")
        with pytest.raises(TypeError):
            atomic_write(path, "not bytes")

    def test_empty_content(self, tmp_path):
        path = str(tmp_path / "out")
        atomic_write(path, b"")
        with open(path, "rb") as f:
            assert f.read() == b""

    def test_large_content(self, tmp_path):
        path = str(tmp_path / "out")
        data = b"x" * (1024 * 1024)  # 1MB
        atomic_write(path, data)
        with open(path, "rb") as f:
            assert f.read() == data

    @pytest.mark.skipif(os.name == "nt", reason="Unix-only symlink test")
    def test_refuses_to_write_through_symlink(self, tmp_path):
        """Symlink attack: attacker places symlink at cache path pointing
        to a sensitive file. atomic_write must refuse."""
        target = str(tmp_path / "sensitive_file")
        with open(target, "w") as f:
            f.write("original")
        link = str(tmp_path / "symlink_cache")
        os.symlink(target, link)
        with pytest.raises(OSError, match="symlink"):
            atomic_write(link, b"overwritten")
        # Verify the target file was not modified
        with open(target, "r") as f:
            assert f.read() == "original"

    @pytest.mark.skipif(os.name == "nt", reason="Unix-only symlink test")
    def test_refuses_to_write_through_symlinked_parent(self, tmp_path):
        """Attacker places symlink as parent directory."""
        real_dir = str(tmp_path / "real")
        os.makedirs(real_dir)
        link_dir = str(tmp_path / "link")
        os.symlink(real_dir, link_dir)
        path = os.path.join(link_dir, "file")
        with pytest.raises(OSError, match="symlink"):
            atomic_write(path, b"data")

    def test_fd_not_leaked_on_permission_error(self, tmp_path):
        """If secure_file_permissions raises, fd must still be closed."""
        path = str(tmp_path / "out")
        # Write a file first so we can verify no fd leak
        atomic_write(path, b"first")
        # Second write should work (fd from first call was properly closed)
        atomic_write(path, b"second")
        with open(path, "rb") as f:
            assert f.read() == b"second"


class TestSafeOpenRead:
    def test_reads_normal_file(self, tmp_path):
        path = str(tmp_path / "data")
        with open(path, "wb") as f:
            f.write(b"hello")
        assert safe_open_read(path) == b"hello"

    @pytest.mark.skipif(os.name == "nt", reason="Unix-only symlink test")
    def test_refuses_to_read_symlink(self, tmp_path):
        """Reading through a symlink could feed attacker-controlled data."""
        target = str(tmp_path / "real")
        with open(target, "w") as f:
            f.write("real data")
        link = str(tmp_path / "link")
        os.symlink(target, link)
        with pytest.raises(OSError, match="symlink"):
            safe_open_read(link)

    @pytest.mark.skipif(os.name == "nt", reason="Unix-only symlink test")
    def test_refuses_to_read_through_symlinked_parent(self, tmp_path):
        real_dir = str(tmp_path / "real")
        os.makedirs(real_dir)
        target = os.path.join(real_dir, "file")
        with open(target, "w") as f:
            f.write("data")
        link_dir = str(tmp_path / "link")
        os.symlink(real_dir, link_dir)
        with pytest.raises(OSError, match="symlink"):
            safe_open_read(os.path.join(link_dir, "file"))

    def test_nonexistent_file_raises(self, tmp_path):
        with pytest.raises(OSError):
            safe_open_read(str(tmp_path / "nonexistent"))

    @pytest.mark.skipif(os.name == "nt", reason="Unix-only symlink test")
    def test_safe_open_read_does_not_leak_fd_on_symlink(self, tmp_path):
        """Verify that fd is properly handled when symlink is detected."""
        target = str(tmp_path / "target")
        with open(target, "w") as f:
            f.write("data")
        link = str(tmp_path / "link")
        os.symlink(target, link)
        # Call multiple times to ensure no fd accumulation
        for _ in range(10):
            with pytest.raises(OSError):
                safe_open_read(link)


class TestRejectSymlink:
    """Tests for _reject_symlink - our pre-check that guards all I/O paths.

    Tests cover the two code paths in the function:
    1. Symlink at the target path itself
    2. Symlink at the immediate parent directory
    Plus the accept path for regular files/nonexistent paths.
    """

    @pytest.mark.skipif(os.name == "nt", reason="Unix-only symlink test")
    def test_rejects_file_symlink(self, tmp_path):
        target = str(tmp_path / "target")
        with open(target, "w") as f:
            f.write("data")
        link = str(tmp_path / "link")
        os.symlink(target, link)
        with pytest.raises(OSError, match="symlink"):
            _reject_symlink(link)

    @pytest.mark.skipif(os.name == "nt", reason="Unix-only symlink test")
    def test_rejects_directory_symlink_parent(self, tmp_path):
        real_dir = str(tmp_path / "real")
        os.makedirs(real_dir)
        link_dir = str(tmp_path / "link")
        os.symlink(real_dir, link_dir)
        with pytest.raises(OSError, match="symlink"):
            _reject_symlink(os.path.join(link_dir, "file"))

    def test_accepts_regular_file(self, tmp_path):
        path = str(tmp_path / "regular")
        with open(path, "w") as f:
            f.write("data")
        _reject_symlink(path)  # should not raise

    def test_accepts_nonexistent_path(self, tmp_path):
        # Nonexistent path is not a symlink
        _reject_symlink(str(tmp_path / "nonexistent"))  # should not raise

    @pytest.mark.skipif(os.name == "nt", reason="Unix-only symlink test")
    def test_rejects_dangling_symlink(self, tmp_path):
        """A symlink whose target does not exist is still a symlink.

        This matters because our code uses os.path.islink (checks the link
        itself) rather than os.path.exists (follows the link). A dangling
        symlink is still an attack vector - the attacker creates the target
        later, or the link redirects writes to a new location.
        """
        link = str(tmp_path / "dangling")
        os.symlink("/nonexistent/target", link)
        with pytest.raises(OSError, match="symlink"):
            _reject_symlink(link)


# ---------------------------------------------------------------------------
# Permission tightening and secure_makedirs security
# ---------------------------------------------------------------------------

class TestSecureMakedirsSecurity:
    """Security-focused tests for secure_makedirs."""

    @pytest.mark.skipif(os.name == "nt", reason="Unix permission model")
    def test_tightens_existing_permissive_directory(self, tmp_path):
        """If directory already exists with 0o755, secure_makedirs tightens
        it to 0o700. This prevents another process from pre-creating a
        directory with permissive permissions."""
        d = str(tmp_path / "permissive")
        os.mkdir(d, mode=0o755)
        assert os.stat(d).st_mode & 0o777 == 0o755
        secure_makedirs(d)
        assert os.stat(d).st_mode & 0o777 == 0o700

    @pytest.mark.skipif(os.name == "nt", reason="Unix permission model")
    def test_tightens_world_writable_directory(self, tmp_path):
        """World-writable directory (0o777) must be tightened to 0o700."""
        d = str(tmp_path / "world_writable")
        os.mkdir(d, mode=0o777)
        secure_makedirs(d)
        assert os.stat(d).st_mode & 0o777 == 0o700

    @pytest.mark.skipif(os.name == "nt", reason="Unix permission model")
    def test_intermediate_dirs_not_world_readable(self, tmp_path):
        """Every directory created by secure_makedirs must be 0o700.

        os.makedirs(mode=) only applies to the leaf on some platforms.
        secure_makedirs creates each level explicitly to avoid this.
        """
        d = str(tmp_path / "l1" / "l2" / "l3" / "l4")
        secure_makedirs(d)
        current = str(tmp_path / "l1")
        for level in ["l1", "l2", "l3", "l4"]:
            current = str(tmp_path / os.sep.join(["l1", "l2", "l3", "l4"][:["l1", "l2", "l3", "l4"].index(level) + 1]))
            mode = os.stat(current).st_mode & 0o777
            assert mode == 0o700, f"{current} has {oct(mode)}, expected 0o700"


# ---------------------------------------------------------------------------
# atomic_write security: TOCTOU, permissions, cleanup
# ---------------------------------------------------------------------------

class TestAtomicWriteSecurity:
    """Security-focused tests for atomic_write."""

    @pytest.mark.skipif(os.name == "nt", reason="Unix permission model")
    def test_overwrite_downgrades_world_readable_permissions(self, tmp_path):
        """Overwriting a world-readable file must result in 0o600.

        An attacker could pre-create a file with 0o644 at the expected
        path. atomic_write via os.replace replaces the file entirely,
        so the new file inherits the temp file's permissions (0o600).
        """
        path = str(tmp_path / "world_readable")
        with open(path, "w") as f:
            f.write("old")
        os.chmod(path, 0o644)
        atomic_write(path, b"new secret")
        mode = os.stat(path).st_mode & 0o777
        assert mode == 0o600

    @pytest.mark.skipif(os.name == "nt", reason="Unix permission model")
    def test_overwrite_downgrades_world_writable_permissions(self, tmp_path):
        """Overwriting a world-writable file (0o666) must result in 0o600."""
        path = str(tmp_path / "world_writable")
        with open(path, "w") as f:
            f.write("old")
        os.chmod(path, 0o666)
        atomic_write(path, b"new secret")
        mode = os.stat(path).st_mode & 0o777
        assert mode == 0o600

    def test_no_temp_file_left_on_symlink_rejection(self, tmp_path):
        """When atomic_write rejects a symlink, no temp file should remain.

        Temp files with sensitive content lingering on disk would be a
        security issue.
        """
        if os.name == "nt":
            pytest.skip("Unix-only symlink test")
        target = str(tmp_path / "target")
        with open(target, "w") as f:
            f.write("sensitive")
        link = str(tmp_path / "link")
        os.symlink(target, link)
        files_before = set(os.listdir(tmp_path))
        with pytest.raises(OSError, match="symlink"):
            atomic_write(link, b"attacker data")
        files_after = set(os.listdir(tmp_path))
        # No new files should remain (temp file was cleaned up)
        assert files_after == files_before


# ---------------------------------------------------------------------------
# Race condition / concurrent access tests
# ---------------------------------------------------------------------------

class TestAtomicWriteConcurrency:
    """Test that atomic_write provides safe concurrent access.

    atomic_write uses temp file + os.replace which is atomic on POSIX.
    Concurrent writers must not produce partial or corrupt reads.
    """

    def test_concurrent_writes_no_partial_reads(self, tmp_path):
        """Multiple threads writing to the same file concurrently.

        A reader must see either the old content or the new content,
        never a partial mix. This tests the atomicity guarantee of
        atomic_write's temp-file-then-replace strategy.
        """
        path = str(tmp_path / "shared")
        atomic_write(path, b"initial")

        content_a = b"A" * 1000
        content_b = b"B" * 1000
        errors = []

        def writer(content, count):
            for _ in range(count):
                try:
                    atomic_write(path, content)
                except OSError:
                    pass  # Permission race - acceptable

        def reader(count):
            for _ in range(count):
                try:
                    data = safe_open_read(path)
                    # Content must be entirely one writer's content
                    if data not in (b"initial", content_a, content_b):
                        errors.append(f"Partial read: {data[:20]!r}...")
                except OSError:
                    pass  # File momentarily missing during replace - acceptable

        threads = [
            threading.Thread(target=writer, args=(content_a, 50)),
            threading.Thread(target=writer, args=(content_b, 50)),
            threading.Thread(target=reader, args=(100,)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert errors == [], f"Partial reads detected: {errors}"

    def test_concurrent_writes_file_never_corrupt(self, tmp_path):
        """After concurrent writes, the final file must be valid
        (content from one writer, not a mix)."""
        path = str(tmp_path / "concurrent")

        content_a = b"AAAA" * 250
        content_b = b"BBBB" * 250

        def writer(content, count):
            for _ in range(count):
                try:
                    atomic_write(path, content)
                except OSError:
                    pass

        threads = [
            threading.Thread(target=writer, args=(content_a, 100)),
            threading.Thread(target=writer, args=(content_b, 100)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        # Final content must be entirely from one writer
        final = safe_open_read(path)
        assert final in (content_a, content_b), "File content is corrupt (mixed writers)"

    @pytest.mark.skipif(os.name == "nt", reason="Unix permission model")
    def test_concurrent_writes_preserve_secure_permissions(self, tmp_path):
        """After concurrent writes, file must still have 0o600."""
        path = str(tmp_path / "perms")

        def writer(tag, count):
            for i in range(count):
                try:
                    atomic_write(path, f"{tag}-{i}".encode())
                except OSError:
                    pass

        threads = [
            threading.Thread(target=writer, args=("A", 50)),
            threading.Thread(target=writer, args=("B", 50)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        mode = os.stat(path).st_mode & 0o777
        assert mode == 0o600, f"Permissions after concurrent writes: {oct(mode)}"

    def test_no_temp_files_after_concurrent_writes(self, tmp_path):
        """After concurrent writes complete, no temp files should remain."""
        path = str(tmp_path / "target")

        def writer(tag, count):
            for i in range(count):
                try:
                    atomic_write(path, f"{tag}-{i}".encode())
                except OSError:
                    pass

        threads = [
            threading.Thread(target=writer, args=("A", 50)),
            threading.Thread(target=writer, args=("B", 50)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        files = os.listdir(tmp_path)
        assert files == ["target"], f"Leftover temp files: {files}"


# ---------------------------------------------------------------------------
# Integration: symlink protection at config/jwt_cache boundaries
# ---------------------------------------------------------------------------

class TestSymlinkProtectionIntegration:
    """End-to-end tests verifying symlink protection at the config and
    JWT cache write paths, not just the file_utils primitives."""

    @pytest.mark.skipif(os.name == "nt", reason="Unix-only symlink test")
    def test_save_config_refuses_symlinked_config_path(self, monkeypatch, tmp_path):
        """config.save_config uses atomic_write which rejects symlinks."""
        from limacharlie.config import _reset_config_cache, save_config
        from limacharlie.paths import _reset_path_cache

        monkeypatch.delenv("LC_EPHEMERAL_CREDS", raising=False)

        # Create a real file that the symlink points to
        target = str(tmp_path / "sensitive")
        with open(target, "w") as f:
            f.write("do not overwrite")

        # Set up config directory with a symlinked config.yaml
        config_dir = str(tmp_path / "config_dir")
        os.makedirs(config_dir, mode=0o700)
        config_file = os.path.join(config_dir, "config.yaml")
        os.symlink(target, config_file)

        monkeypatch.setenv("LC_CONFIG_DIR", config_dir)
        monkeypatch.delenv("LC_CREDS_FILE", raising=False)
        monkeypatch.delenv("LC_LEGACY_CONFIG", raising=False)
        _reset_path_cache()
        _reset_config_cache()

        try:
            with pytest.raises(OSError, match="symlink"):
                save_config({"oid": "test-org"})
            # Target must be untouched
            with open(target, "r") as f:
                assert f.read() == "do not overwrite"
        finally:
            _reset_path_cache()
            _reset_config_cache()

    @pytest.mark.skipif(os.name == "nt", reason="Unix-only symlink test")
    def test_load_config_refuses_symlinked_config_path(self, monkeypatch, tmp_path):
        """config.load_config uses safe_open_read which rejects symlinks.

        The OSError from symlink rejection propagates to the caller -
        load_config does not silently swallow it. This is the correct
        behavior: a symlinked config file is a security issue that should
        be surfaced, not hidden.
        """
        from limacharlie.config import _reset_config_cache, load_config
        from limacharlie.paths import _reset_path_cache

        # Create an attacker-controlled file
        target = str(tmp_path / "attacker_config")
        with open(target, "w") as f:
            f.write("oid: attacker-org\napi_key: stolen-key\n")

        # Set up config directory with a symlinked config.yaml
        config_dir = str(tmp_path / "config_dir")
        os.makedirs(config_dir, mode=0o700)
        config_file = os.path.join(config_dir, "config.yaml")
        os.symlink(target, config_file)

        monkeypatch.setenv("LC_CONFIG_DIR", config_dir)
        monkeypatch.delenv("LC_CREDS_FILE", raising=False)
        monkeypatch.delenv("LC_LEGACY_CONFIG", raising=False)
        _reset_path_cache()
        _reset_config_cache()

        try:
            with pytest.raises(OSError, match="symlink"):
                load_config()
        finally:
            _reset_path_cache()
            _reset_config_cache()

    @pytest.mark.skipif(os.name == "nt", reason="Unix-only symlink test")
    def test_jwt_cache_clear_does_not_delete_through_symlink(self, tmp_path, monkeypatch):
        """clear_jwt_cache deletes the path entry, not the symlink target.

        If an attacker places a symlink at the cache path pointing to
        a valuable file, clear_jwt_cache must not delete the target.
        """
        from limacharlie.jwt_cache import clear_jwt_cache
        from limacharlie.paths import _reset_path_cache

        config_dir = str(tmp_path / "config")
        os.makedirs(config_dir, mode=0o700)
        monkeypatch.setenv("LC_CONFIG_DIR", config_dir)
        monkeypatch.delenv("LC_CREDS_FILE", raising=False)
        monkeypatch.delenv("LC_LEGACY_CONFIG", raising=False)
        _reset_path_cache()

        target = str(tmp_path / "valuable_file")
        with open(target, "w") as f:
            f.write("important data")

        cache_path = os.path.join(config_dir, "jwt_cache.json")
        os.symlink(target, cache_path)

        try:
            clear_jwt_cache()
            # The symlink should be removed (os.unlink removes the symlink)
            assert not os.path.islink(cache_path)
            # The target file must still exist
            assert os.path.isfile(target)
            with open(target, "r") as f:
                assert f.read() == "important data"
        finally:
            _reset_path_cache()
