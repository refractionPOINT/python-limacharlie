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
    org.client._jwt = "test-jwt"
    return org


@pytest.fixture
def configs(mock_org):
    return Configs(mock_org)


def _write_yaml_file(path, data):
    """Write YAML data to a file properly."""
    with open(path, "w") as f:
        yaml.safe_dump(data, f)


class TestConfigsFetch:
    def test_fetch_via_extension(self, configs, mock_org):
        mock_org.client.request.return_value = {
            "data": {"org": {"outputs": {"o1": {"module": "s3"}}}}
        }
        result = configs.fetch(sync_outputs=True)
        mock_org.client.request.assert_called_once()
        call_args = mock_org.client.request.call_args
        assert call_args[0][1] == "extension/request/ext-infrastructure"
        assert "outputs" in result

    def test_fetch_with_hives(self, configs, mock_org):
        mock_org.client.request.return_value = {
            "data": {"org": {"hives": {"dr-general": {"r1": {"data": {}}}}}}
        }
        result = configs.fetch(sync_hives={"dr-general": True})
        mock_org.client.request.assert_called_once()
        assert "hives" in result
        assert "dr-general" in result["hives"]

    def test_fetch_passes_all_flags(self, configs, mock_org):
        mock_org.client.request.return_value = {"data": {"org": {}}}
        configs.fetch(
            sync_outputs=True,
            sync_integrity=True,
            sync_artifact=True,
            sync_exfil=True,
            sync_resources=True,
            sync_extensions=True,
            sync_org_values=True,
            sync_hives={"dr-general": True, "fp": True},
            sync_installation_keys=True,
            sync_yara=True,
        )
        call_args = mock_org.client.request.call_args
        # The data is gzipped+base64 in the params, so check it was called
        assert call_args[0][1] == "extension/request/ext-infrastructure"


class TestConfigsPush:
    def test_push_via_extension(self, configs, mock_org):
        mock_org.client.request.return_value = {
            "data": {"ops": [{"type": "output", "name": "o1", "is_added": True, "is_removed": False}]}
        }
        config = {"version": 3, "outputs": {"o1": {"module": "s3"}}}
        results, errors = configs.push(config, sync_outputs=True)
        assert len(results) == 1
        assert results[0] == ("+", "output", "o1")
        assert errors == []

    def test_push_dry_run(self, configs, mock_org):
        mock_org.client.request.return_value = {"data": {"ops": []}}
        configs.push({"version": 3}, is_dry_run=True, sync_outputs=True)
        mock_org.client.request.assert_called_once()

    def test_push_force(self, configs, mock_org):
        mock_org.client.request.return_value = {
            "data": {"ops": [
                {"type": "output", "name": "old", "is_added": False, "is_removed": True},
            ]}
        }
        results, errors = configs.push({"version": 3}, is_force=True, sync_outputs=True)
        assert results[0] == ("-", "output", "old")
        assert errors == []

    def test_push_with_hives(self, configs, mock_org):
        mock_org.client.request.return_value = {
            "data": {"ops": [{"type": "hive.dr-general", "name": "r1", "is_added": True, "is_removed": False}]}
        }
        config = {"version": 3, "hives": {"dr-general": {"r1": {"data": {}}}}}
        results, errors = configs.push(config, sync_hives={"dr-general": True})
        assert len(results) == 1
        assert results[0] == ("+", "hive.dr-general", "r1")
        assert errors == []

    def test_push_unchanged(self, configs, mock_org):
        mock_org.client.request.return_value = {
            "data": {"ops": [
                {"type": "output", "name": "o1", "is_added": False, "is_removed": False},
            ]}
        }
        results, errors = configs.push({"version": 3}, sync_outputs=True)
        assert results[0] == ("=", "output", "o1")
        assert errors == []

    def test_push_returns_backend_errors(self, configs, mock_org):
        mock_org.client.request.return_value = {
            "data": {
                "ops": [],
                "errors": ["failed to sync output 'bad-output': invalid module"],
            }
        }
        results, errors = configs.push({"version": 3}, sync_outputs=True)
        assert results == []
        assert len(errors) == 1
        assert "bad-output" in errors[0]


class TestConfigsLoadEffectiveConfig:
    def test_load_simple_config(self, configs):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.safe_dump({"version": 3, "outputs": {"o1": {"module": "s3"}}}, f)
            path = f.name
        try:
            config, includes = configs._load_effective_config(path)
            assert config["version"] == 3
            assert "o1" in config["outputs"]
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
            yaml.safe_dump({"outputs": {}}, f)
            path = f.name
        try:
            with pytest.raises(ConfigException, match="Version not found"):
                configs._load_effective_config(path)
        finally:
            os.unlink(path)

    def test_load_config_with_hive_includes(self, configs):
        with tempfile.TemporaryDirectory() as tmpdir:
            sub_path = os.path.join(tmpdir, "sub.yaml")
            _write_yaml_file(sub_path, {
                "version": 3,
                "hives": {"dr-general": {"r2": {"data": {"detect": {}}}}},
            })
            main_path = os.path.join(tmpdir, "main.yaml")
            _write_yaml_file(main_path, {
                "version": 3,
                "include": ["sub.yaml"],
                "hives": {"dr-general": {"r1": {"data": {"detect": {}}}}},
            })
            config, includes = configs._load_effective_config(main_path)
            assert "r1" in config["hives"]["dr-general"]
            assert "r2" in config["hives"]["dr-general"]


class TestConfigsFetchToFile:
    def test_fetch_to_file(self, configs, mock_org):
        mock_org.client.request.return_value = {
            "data": {"org": {"outputs": {"o1": {"module": "s3"}}}}
        }

        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
            path = f.name
        try:
            configs.fetch_to_file(path, sync_outputs=True)
            with open(path, "rb") as f:
                content = yaml.safe_load(f.read())
            assert "outputs" in content
        finally:
            os.unlink(path)


class TestAllHives:
    def test_all_hives_constant(self):
        expected = {
            "dr-general", "dr-managed", "dr-service", "fp",
            "cloud_sensor", "extension_config", "yara", "lookup",
            "secret", "query", "playbook", "ai_agent", "external_adapter",
        }
        assert Configs.ALL_HIVES == expected

    def test_no_use_extension_parameter(self):
        """Configs no longer accepts use_extension; it always uses the extension."""
        import inspect
        sig = inspect.signature(Configs.__init__)
        assert "use_extension" not in sig.parameters
