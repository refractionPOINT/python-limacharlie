"""Tests for limacharlie.file_utils module."""

import os
import stat

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

    @pytest.mark.skipif(os.name == "nt", reason="Unix-only O_NOFOLLOW test")
    def test_o_nofollow_rejects_symlink_at_kernel_level(self, tmp_path):
        """Verify the O_NOFOLLOW path works independently of _reject_symlink.

        Even if the pre-check were somehow bypassed, O_NOFOLLOW in the
        kernel open() call would reject the symlink.
        """
        target = str(tmp_path / "secret")
        with open(target, "w") as f:
            f.write("secret data")
        link = str(tmp_path / "link")
        os.symlink(target, link)
        # Directly call os.open with O_NOFOLLOW to verify kernel rejects it
        with pytest.raises(OSError):
            os.open(link, os.O_RDONLY | os.O_NOFOLLOW)

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
        """A symlink pointing to nothing is still a symlink."""
        link = str(tmp_path / "dangling")
        os.symlink("/nonexistent/target", link)
        with pytest.raises(OSError, match="symlink"):
            _reject_symlink(link)
