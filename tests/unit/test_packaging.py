"""Tests for pyproject.toml packaging migration."""

import pathlib
import sys

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent


class TestPyprojectToml:
    def test_pyproject_exists(self):
        assert (PROJECT_ROOT / "pyproject.toml").exists()

    def test_setup_py_removed(self):
        assert not (PROJECT_ROOT / "setup.py").exists()

    def test_setup_cfg_removed(self):
        assert not (PROJECT_ROOT / "setup.cfg").exists()

    def test_requirements_txt_removed(self):
        assert not (PROJECT_ROOT / "requirements.txt").exists()

    def test_requirements_tests_removed(self):
        assert not (PROJECT_ROOT / "requirements-tests.txt").exists()

    def test_pyproject_parseable(self):
        with open(PROJECT_ROOT / "pyproject.toml", "rb") as f:
            data = tomllib.load(f)
        assert "project" in data
        assert "build-system" in data

    def test_entry_point_defined(self):
        with open(PROJECT_ROOT / "pyproject.toml", "rb") as f:
            data = tomllib.load(f)
        scripts = data.get("project", {}).get("scripts", {})
        assert "limacharlie" in scripts
        assert scripts["limacharlie"] == "limacharlie.cli:main"

    def test_version(self):
        with open(PROJECT_ROOT / "pyproject.toml", "rb") as f:
            data = tomllib.load(f)
        assert data["project"]["version"] == "2.0.0"

    def test_dev_dependencies(self):
        with open(PROJECT_ROOT / "pyproject.toml", "rb") as f:
            data = tomllib.load(f)
        dev_deps = data["project"].get("optional-dependencies", {}).get("dev", [])
        dep_names = [d.split("==")[0].split(">=")[0] for d in dev_deps]
        assert "pytest" in dep_names
