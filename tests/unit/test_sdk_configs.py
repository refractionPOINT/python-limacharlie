"""Tests for limacharlie.sdk.configs module."""

import os
import tempfile
from unittest.mock import MagicMock
import pytest
import yaml

from limacharlie.sdk.configs import Configs, ConfigException


@pytest.fixture
def mock_org():
    org = MagicMock()
    org.oid = "test-oid"
    org.client = MagicMock()
    return org


@pytest.fixture
def configs(mock_org):
    return Configs(mock_org)


def _write_yaml_file(path, data):
    """Write YAML data to a file properly."""
    with open(path, "w") as f:
        yaml.safe_dump(data, f)


class TestConfigsFetch:
    def test_fetch_via_service(self, configs, mock_org):
        org_yaml = yaml.safe_dump({"rules": {"r1": {"detect": {}}}})
        mock_org.service_request.return_value = {"org": org_yaml}
        result = configs.fetch(sync_rules=True)
        mock_org.service_request.assert_called_once()
        call_args = mock_org.service_request.call_args
        assert call_args[0][0] == "infrastructure-service"
        params = call_args[0][1]
        assert params["sync_dr"] is True
        assert "rules" in result

    def test_fetch_via_extension(self, mock_org):
        ext_configs = Configs(mock_org, use_extension=True)
        mock_org.extension_request.return_value = {
            "data": {"org": {"rules": {"r1": {"detect": {}}}}}
        }
        result = ext_configs.fetch(sync_rules=True)
        mock_org.extension_request.assert_called_once()
        assert "rules" in result


class TestConfigsPush:
    def test_push_via_service(self, configs, mock_org):
        mock_org.service_request.return_value = {
            "ops": [
                {"type": "rule", "name": "r1", "is_added": True, "is_removed": False},
                {"type": "rule", "name": "r2", "is_added": False, "is_removed": False},
            ]
        }
        config = {"version": 3, "rules": {"r1": {"detect": {}}}}
        results = configs.push(config, sync_rules=True)
        assert len(results) == 2
        assert results[0] == ("+", "rule", "r1")
        assert results[1] == ("=", "rule", "r2")

    def test_push_dry_run(self, configs, mock_org):
        mock_org.service_request.return_value = {"ops": []}
        configs.push({"version": 3}, is_dry_run=True, sync_rules=True)
        params = mock_org.service_request.call_args[0][1]
        assert params["is_dry_run"] is True

    def test_push_force(self, configs, mock_org):
        mock_org.service_request.return_value = {
            "ops": [
                {"type": "rule", "name": "old", "is_added": False, "is_removed": True},
            ]
        }
        results = configs.push({"version": 3}, is_force=True, sync_rules=True)
        assert results[0] == ("-", "rule", "old")

    def test_push_via_extension(self, mock_org):
        ext_configs = Configs(mock_org, use_extension=True)
        mock_org.extension_request.return_value = {
            "data": {"ops": [{"type": "fp", "name": "f1", "is_added": True, "is_removed": False}]}
        }
        results = ext_configs.push({"version": 3}, sync_fps=True)
        assert len(results) == 1
        assert results[0] == ("+", "fp", "f1")


class TestConfigsLoadEffectiveConfig:
    def test_load_simple_config(self, configs):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.safe_dump({"version": 3, "rules": {"r1": {"detect": {}}}}, f)
            path = f.name
        try:
            config, includes = configs._load_effective_config(path)
            assert config["version"] == 3
            assert "r1" in config["rules"]
            assert includes == []
        finally:
            os.unlink(path)

    def test_load_config_version_check(self, configs):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.safe_dump({"version": 99}, f)
            path = f.name
        try:
            with pytest.raises(ConfigException, match="not supported"):
                configs._load_effective_config(path)
        finally:
            os.unlink(path)

    def test_load_config_missing_version(self, configs):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.safe_dump({"rules": {}}, f)
            path = f.name
        try:
            with pytest.raises(ConfigException, match="Version not found"):
                configs._load_effective_config(path)
        finally:
            os.unlink(path)


class TestConfigsFetchToFile:
    def test_fetch_to_file(self, configs, mock_org):
        org_yaml = yaml.safe_dump({"rules": {"r1": {"detect": {}}}})
        mock_org.service_request.return_value = {"org": org_yaml}

        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
            path = f.name
        try:
            configs.fetch_to_file(path, sync_rules=True)
            with open(path, "rb") as f:
                content = yaml.safe_load(f.read())
            assert "rules" in content
        finally:
            os.unlink(path)
