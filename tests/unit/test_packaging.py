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

    def test_version_is_dynamic(self):
        with open(PROJECT_ROOT / "pyproject.toml", "rb") as f:
            data = tomllib.load(f)
        assert "version" in data["project"].get("dynamic", [])

    def test_dev_dependencies(self):
        with open(PROJECT_ROOT / "pyproject.toml", "rb") as f:
            data = tomllib.load(f)
        dev_deps = data["project"].get("optional-dependencies", {}).get("dev", [])
        dep_names = [d.split("==")[0].split(">=")[0] for d in dev_deps]
        assert "pytest" in dep_names

    def test_classifiers_present(self):
        with open(PROJECT_ROOT / "pyproject.toml", "rb") as f:
            data = tomllib.load(f)
        classifiers = data["project"].get("classifiers", [])
        assert len(classifiers) > 0, "No classifiers defined"

    def test_classifiers_include_current_python(self):
        """The classifiers should include the Python version running the tests."""
        with open(PROJECT_ROOT / "pyproject.toml", "rb") as f:
            data = tomllib.load(f)
        classifiers = data["project"].get("classifiers", [])
        major_minor = f"{sys.version_info.major}.{sys.version_info.minor}"
        expected = f"Programming Language :: Python :: {major_minor}"
        assert expected in classifiers, (
            f"Missing classifier for current Python {major_minor}: {expected}"
        )

    def test_classifiers_include_python3(self):
        with open(PROJECT_ROOT / "pyproject.toml", "rb") as f:
            data = tomllib.load(f)
        classifiers = data["project"].get("classifiers", [])
        assert "Programming Language :: Python :: 3" in classifiers

    def test_requires_python_minimum(self):
        with open(PROJECT_ROOT / "pyproject.toml", "rb") as f:
            data = tomllib.load(f)
        requires = data["project"].get("requires-python", "")
        assert "3.9" in requires, "Minimum Python should be 3.9"

    def test_classifiers_production_stable(self):
        with open(PROJECT_ROOT / "pyproject.toml", "rb") as f:
            data = tomllib.load(f)
        classifiers = data["project"].get("classifiers", [])
        assert "Development Status :: 5 - Production/Stable" in classifiers

    def test_project_urls_present(self):
        with open(PROJECT_ROOT / "pyproject.toml", "rb") as f:
            data = tomllib.load(f)
        urls = data["project"].get("urls", {})
        for key in ("Homepage", "Repository", "Issues", "Documentation", "Changelog"):
            assert key in urls, f"Missing project URL: {key}"

    def test_project_urls_all_https(self):
        """All project URLs should start with https://."""
        with open(PROJECT_ROOT / "pyproject.toml", "rb") as f:
            data = tomllib.load(f)
        urls = data["project"].get("urls", {})
        for name, url in urls.items():
            assert url.startswith("https://"), f"URL for {name} is not HTTPS: {url}"

    def test_project_description_not_empty(self):
        with open(PROJECT_ROOT / "pyproject.toml", "rb") as f:
            data = tomllib.load(f)
        desc = data["project"].get("description", "")
        assert len(desc) > 10, "Description too short or missing"
