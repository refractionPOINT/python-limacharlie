"""Tests for type annotation infrastructure (PEP 561, TypedDict, future annotations)."""

import importlib
import pathlib


class TestPEP561:
    def test_py_typed_marker_exists(self):
        """PEP 561 py.typed marker file must exist for typed package support."""
        import limacharlie
        pkg_dir = pathlib.Path(limacharlie.__file__).parent
        assert (pkg_dir / "py.typed").exists()


class TestCredentialsTypedDict:
    def test_credentials_importable(self):
        from limacharlie.config import Credentials
        assert Credentials is not None

    def test_credentials_keys(self):
        from limacharlie.config import Credentials
        # TypedDict annotations are accessible via __annotations__
        annotations = Credentials.__annotations__
        assert "oid" in annotations
        assert "uid" in annotations
        assert "api_key" in annotations
        assert "oauth" in annotations


class TestFutureAnnotations:
    """Verify that core modules use from __future__ import annotations."""

    CORE_MODULES = [
        "limacharlie.cli",
        "limacharlie.config",
        "limacharlie.client",
        "limacharlie.errors",
        "limacharlie.output",
        "limacharlie.discovery",
        "limacharlie.help_topics",
        "limacharlie.sdk.hive",
        "limacharlie.sdk.organization",
        "limacharlie.sdk.sensor",
    ]

    def test_future_annotations_in_core_modules(self):
        for mod_name in self.CORE_MODULES:
            mod = importlib.import_module(mod_name)
            source_file = mod.__file__
            assert source_file is not None, f"{mod_name} has no __file__"
            with open(source_file) as f:
                content = f.read()
            assert "from __future__ import annotations" in content, (
                f"{mod_name} is missing 'from __future__ import annotations'"
            )
