"""Tests for pyproject.toml packaging and distribution."""

import pathlib
import sys

import pytest

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
        assert "3.10" in requires, "Minimum Python should be 3.10"
        assert "3.9" not in requires, "Python 3.9 is EOL and no longer supported"

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

    def test_orjson_is_uncapped(self):
        """orjson should be a single uncapped dependency.

        orjson 3.11+ requires Python 3.10+. Now that our minimum is 3.10, the
        old python_version<3.10 split (which capped orjson at <3.11 to keep 3.9
        working) is gone, and every supported version can take the latest orjson.
        """
        with open(PROJECT_ROOT / "pyproject.toml", "rb") as f:
            data = tomllib.load(f)
        deps = data["project"].get("dependencies", [])
        orjson_deps = [d for d in deps if d.startswith("orjson")]
        assert len(orjson_deps) == 1, (
            f"Expected a single orjson dep, got {len(orjson_deps)}: {orjson_deps}"
        )
        spec = orjson_deps[0]
        assert ">=3.10.0" in spec, f"orjson should floor at >=3.10.0, got {spec!r}"
        assert "<3.11" not in spec, f"orjson should not be capped below 3.11, got {spec!r}"
        assert "python_version" not in spec, (
            f"orjson no longer needs a python_version marker, got {spec!r}"
        )

    def test_orjson_available_on_current_python(self):
        """orjson should be importable on any supported Python version."""
        try:
            import orjson
            assert orjson is not None
        except ImportError:
            # Only acceptable if we're on a platform without wheels
            import platform
            pytest.skip(f"orjson not available on {platform.system()}/{platform.machine()}")

    def test_json_compat_works_regardless_of_orjson(self):
        """json_compat module should work whether orjson is available or not."""
        from limacharlie.json_compat import dumps, loads, backend_name
        data = {"key": "value", "nested": [1, 2, 3]}
        roundtrip = loads(dumps(data))
        assert roundtrip == data
        assert backend_name() in ("orjson", "stdlib json")

    def test_project_description_not_empty(self):
        with open(PROJECT_ROOT / "pyproject.toml", "rb") as f:
            data = tomllib.load(f)
        desc = data["project"].get("description", "")
        assert len(desc) > 10, "Description too short or missing"
