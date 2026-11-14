"""Tests for limacharlie.sdk.configs module."""

import base64
import datetime
import gzip
import json
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


def _sent_push_config(mock_org):
    """Return the config text the SDK sent to ext-infrastructure's push action."""
    params = mock_org.client.request.call_args.kwargs["params"]
    assert params["action"] == "push"
    data = json.loads(gzip.decompress(base64.b64decode(params["gzdata"])))
    return data["config"]


def _scalar_nodes(node):
    """Yield every scalar node of a composed YAML document, keys included."""
    if isinstance(node, yaml.ScalarNode):
        yield node
    elif isinstance(node, yaml.SequenceNode):
        for item in node.value:
            yield from _scalar_nodes(item)
    elif isinstance(node, yaml.MappingNode):
        for k, v in node.value:
            yield from _scalar_nodes(k)
            yield from _scalar_nodes(v)


# Strings that PyYAML (YAML 1.1) leaves unquoted but that a YAML 1.2 reader,
# such as ext-infrastructure's gopkg.in/yaml.v3, reads as numbers.
YAML12_NUMBER_LOOKALIKES = [
    "0308", "0129", "0389", "08", "09",
    "00000000000000000000000000000308",
    "1e3", "2e5", "1E10", "-1e3",
    "0o17", "0o0",
]


class TestConfigsPushStringTyping:
    """Strings must reach ext-infrastructure as strings under YAML 1.1 and 1.2."""

    @pytest.mark.parametrize("value", YAML12_NUMBER_LOOKALIKES)
    def test_number_lookalike_is_sent_double_quoted(self, configs, mock_org, value):
        mock_org.client.request.return_value = {"data": {"ops": []}}
        config = {"version": 3, "hives": {"dr-general": {"r1": {"data": {
            "detect": {"event": "NEW_PROCESS", "op": "is", "path": "event/COMMAND_LINE", "value": value},
            "respond": [{"action": "report", "name": "r1"}],
        }}}}}
        configs.push(config, sync_hives={"dr-general": True})

        sent = _sent_push_config(mock_org)
        assert f'"value": "{value}"' in sent
        assert yaml.safe_load(sent) == config

    def test_every_string_is_double_quoted_and_other_types_are_plain(self, configs, mock_org):
        mock_org.client.request.return_value = {"data": {"ops": []}}
        strings = YAML12_NUMBER_LOOKALIKES + [
            "0307", "0123", "true", "yes", "off", "null", "~", "", " ", ".inf", ".nan",
            "1.0", "1_000", "0x1F", "0b101", "12:30", "2026-01-01", "a: b", "- a", "#c",
            "&a", "*a", "!tag", "|", ">", "%x", "@x", "'single'", '"double"', "back\\slash",
            "line1\nline2", "trailing\n", "tab\there", " lead", "trail ", "\u00e9t\u00e9",
            "\U0001F600", "\x7f", "\x85", "\u2028", "\ufeff", "\x00", "\x1b",
            "x" * 3000, " ".join(["word"] * 500),
        ]
        config = {"version": 3, "hives": {"lookup": {"l1": {
            "usr_mtd": {"enabled": True, "expiry": 0, "tags": ["0308"], "comment": "1e3"},
            "data": {
                "values": strings,
                "keyed": {s: i for i, s in enumerate(strings)},
                "long-key-" + "k" * 2000: "v",
                "ints": [0, -5, 2**40, 2**63 - 1],
                "floats": [0.5, 1.0, -2.25, 1e20, 1e-05],
                "bools": [True, False],
                "nothing": None,
                "nested": [{"a": [{"b": s}]} for s in strings[:5]],
            },
        }}}}
        configs.push(config, sync_hives={"lookup": True})

        sent = _sent_push_config(mock_org)
        assert yaml.safe_load(sent) == config
        nodes = list(_scalar_nodes(yaml.compose(sent)))
        str_nodes = [n for n in nodes if n.tag == "tag:yaml.org,2002:str"]
        other_nodes = [n for n in nodes if n.tag != "tag:yaml.org,2002:str"]
        assert len(str_nodes) > len(strings) * 2
        assert {n.style for n in str_nodes} == {'"'}
        assert other_nodes
        assert {n.style for n in other_nodes} == {None}

    def test_non_string_scalars_are_written_as_before(self, configs, mock_org):
        mock_org.client.request.return_value = {"data": {"ops": []}}
        config = {"version": 3, "hives": {"lookup": {"l1": {"data": {
            "ints": [0, 7, -5, 2**63 - 1],
            "floats": [0.5, 1e20, float("inf")],
            "bools": [True, False],
            "nothing": None,
            "day": datetime.date(2026, 1, 1),
            "when": datetime.datetime(2026, 1, 1, 10, 0, 0),
            "raw": b"\x00\x01",
        }}}}}
        configs.push(config, sync_hives={"lookup": True})

        def non_str(text):
            return [(n.tag, n.value, n.style) for n in _scalar_nodes(yaml.compose(text))
                    if n.tag != "tag:yaml.org,2002:str"]

        sent = _sent_push_config(mock_org)
        assert non_str(sent) == non_str(yaml.safe_dump(config, version=(1, 1)))
        assert yaml.safe_load(sent) == config

    def test_push_from_file_keeps_quoted_values_as_strings(self, configs, mock_org):
        mock_org.client.request.return_value = {"data": {"ops": []}}
        content = """version: 3
hives:
  dr-general:
    zero-padded-ids:
      usr_mtd:
        enabled: false
      data:
        detect:
          op: or
          rules:
            - op: is
              path: event/COMMAND_LINE
              value: '0389'
            - op: is
              path: event/FILE_PATH
              value: '1e3'
        respond:
          - action: report
            name: zero-padded-ids
        tests:
          non_match:
            - - event:
                  A: '00000000000000000000000000000307'
                  B: '00000000000000000000000000000308'
                  C: '0123'
                  D: '0129'
                  E: '0o17'
                  N: 42
                routing:
                  event_type: NEW_PROCESS
                  this: '00000000000000000000000000000309'
"""
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "config.yaml")
            with open(path, "w") as f:
                f.write(content)
            configs.push_from_file(path, sync_hives={"dr-general": True})

        sent = _sent_push_config(mock_org)
        assert yaml.safe_load(sent) == yaml.safe_load(content)
        for value in ("0389", "1e3", "00000000000000000000000000000308", "0129", "0o17",
                      "00000000000000000000000000000309"):
            assert f'"{value}"' in sent
        assert '"N": 42' in sent


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


class TestConfigsIncludeOrder:
    """Include precedence must be deterministic and match the Go SDK."""

    @staticmethod
    def _tree(tmpdir, files):
        for rel, data in files.items():
            path = os.path.join(tmpdir, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            _write_yaml_file(path, data)
        return os.path.join(tmpdir, "main.yaml")

    @staticmethod
    def _rec(tag):
        return {"data": {"detect": {"tag": tag}}}

    def test_later_listed_include_wins(self, configs):
        with tempfile.TemporaryDirectory() as tmpdir:
            main = self._tree(tmpdir, {
                "main.yaml": {"version": 3, "include": ["b.yaml", "a.yaml", "c.yaml"]},
                "a.yaml": {"version": 3, "hives": {"dr-general": {"r": self._rec("a")}},
                           "outputs": {"o": {"module": "a"}}},
                "b.yaml": {"version": 3, "hives": {"dr-general": {"r": self._rec("b")}},
                           "outputs": {"o": {"module": "b"}}},
                "c.yaml": {"version": 3, "hives": {"dr-general": {"r": self._rec("c")}},
                           "outputs": {"o": {"module": "c"}}},
            })
            config, includes = configs._load_effective_config(main)
        assert config["hives"]["dr-general"]["r"] == self._rec("c")
        assert config["outputs"]["o"] == {"module": "c"}
        assert [os.path.basename(i) for i in includes] == ["b.yaml", "a.yaml", "c.yaml"]

    @pytest.mark.parametrize("seed", ["0", "1", "42"])
    def test_result_independent_of_hash_seed(self, seed):
        import subprocess
        import sys
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        with tempfile.TemporaryDirectory() as tmpdir:
            names = [f"inc{i}.yaml" for i in range(12)]
            files = {"main.yaml": {"version": 3, "include": names}}
            for n in names:
                files[n] = {"version": 3, "outputs": {"o": {"module": n}}}
            main = self._tree(tmpdir, files)
            code = (
                "import sys\n"
                "from unittest.mock import MagicMock\n"
                "from limacharlie.sdk.configs import Configs\n"
                "c, _ = Configs(MagicMock())._load_effective_config(sys.argv[1])\n"
                "print(c['outputs']['o']['module'])\n"
            )
            out = subprocess.run([sys.executable, "-c", code, main], capture_output=True, text=True,
                                 env={**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": repo_root}, check=True)
        assert out.stdout.strip() == "inc11.yaml"

    def test_included_overrides_includer(self, configs):
        with tempfile.TemporaryDirectory() as tmpdir:
            main = self._tree(tmpdir, {
                "main.yaml": {"version": 3, "include": ["a.yaml"],
                              "outputs": {"o": {"module": "main"}, "only-main": {"module": "m"}},
                              "hives": {"dr-general": {"r": self._rec("main")}}},
                "a.yaml": {"version": 3, "outputs": {"o": {"module": "a"}},
                           "hives": {"dr-general": {"r": self._rec("a")}}},
            })
            config, _ = configs._load_effective_config(main)
        assert config["outputs"] == {"o": {"module": "a"}, "only-main": {"module": "m"}}
        assert config["hives"]["dr-general"]["r"] == self._rec("a")

    def test_nested_include_overrides_its_includer(self, configs):
        with tempfile.TemporaryDirectory() as tmpdir:
            main = self._tree(tmpdir, {
                "main.yaml": {"version": 3, "include": ["a.yaml"]},
                "a.yaml": {"version": 3, "include": ["deep/d.yaml"], "outputs": {"o": {"module": "a"}}},
                "deep/d.yaml": {"version": 3, "outputs": {"o": {"module": "d"}, "p": {"module": "d"}}},
            })
            config, includes = configs._load_effective_config(main)
        # Included beats includer at every level (Go: thisConfig.Merge(incConf)).
        assert config["outputs"] == {"o": {"module": "d"}, "p": {"module": "d"}}
        assert [os.path.basename(i) for i in includes] == ["a.yaml", "d.yaml"]

    def test_glob_expands_sorted_in_listed_position(self, configs):
        with tempfile.TemporaryDirectory() as tmpdir:
            files = {"main.yaml": {"version": 3, "include": ["z-first.yaml", "g/*.yaml", "last.yaml"]}}
            for n in ("g/b.yaml", "g/c.yaml", "g/a.yaml", "z-first.yaml", "last.yaml"):
                files[n] = {"version": 3, "outputs": {os.path.basename(n): {"module": n}}}
            files["g/a.yaml"]["outputs"]["shared"] = {"module": "a"}
            files["g/c.yaml"]["outputs"]["shared"] = {"module": "c"}
            files["g/b.yaml"]["outputs"]["shared"] = {"module": "b"}
            main = self._tree(tmpdir, files)
            config, includes = configs._load_effective_config(main)
        assert [os.path.relpath(i, os.path.realpath(tmpdir)) for i in includes] == [
            "z-first.yaml", os.path.join("g", "a.yaml"), os.path.join("g", "b.yaml"),
            os.path.join("g", "c.yaml"), "last.yaml"]
        assert config["outputs"]["shared"] == {"module": "c"}

    def test_duplicate_includes_processed_at_first_occurrence(self, configs):
        with tempfile.TemporaryDirectory() as tmpdir:
            main = self._tree(tmpdir, {
                "main.yaml": {"version": 3, "include": ["a.yaml", "b.yaml", "./a.yaml", "[ab].yaml"]},
                "a.yaml": {"version": 3, "outputs": {"o": {"module": "a"}}},
                "b.yaml": {"version": 3, "outputs": {"o": {"module": "b"}}},
            })
            config, includes = configs._load_effective_config(main)
        # a.yaml is not re-applied after b.yaml, so b still wins.
        assert config["outputs"]["o"] == {"module": "b"}
        assert [os.path.basename(i) for i in includes] == ["a.yaml", "b.yaml"]

    def test_same_name_in_different_directories_is_not_a_duplicate(self, configs):
        with tempfile.TemporaryDirectory() as tmpdir:
            main = self._tree(tmpdir, {
                "main.yaml": {"version": 3, "include": ["a.yaml", "deep/x.yaml"]},
                "a.yaml": {"version": 3, "outputs": {"root": {"module": "a"}}},
                "deep/x.yaml": {"version": 3, "include": ["a.yaml"]},
                "deep/a.yaml": {"version": 3, "outputs": {"deep": {"module": "a"}}},
            })
            config, includes = configs._load_effective_config(main)
        assert set(config["outputs"]) == {"root", "deep"}
        assert len(includes) == 3 and all(os.path.isabs(i) for i in includes)

    def test_yaml_aliases_do_not_leak_between_records(self, configs):
        with tempfile.TemporaryDirectory() as tmpdir:
            main = os.path.join(tmpdir, "main.yaml")
            with open(os.path.join(tmpdir, "a.yaml"), "w") as f:
                f.write("version: 3\nhives:\n  dr-general:\n    r1: &x {data: {k: 1}}\n    r2: *x\n")
            with open(os.path.join(tmpdir, "b.yaml"), "w") as f:
                f.write("version: 3\nhives:\n  dr-general:\n    r1: {extra: 1}\n")
            _write_yaml_file(main, {"version": 3, "include": ["a.yaml", "b.yaml"]})
            config, _ = configs._load_effective_config(main)
        assert config["hives"]["dr-general"]["r2"] == {"data": {"k": 1}}
        assert config["hives"]["dr-general"]["r1"] == {"extra": 1}

    def test_non_glob_include_without_match_errors(self, configs):
        with tempfile.TemporaryDirectory() as tmpdir:
            main = self._tree(tmpdir, {"main.yaml": {"version": 3, "include": ["missing.yaml"]}})
            with pytest.raises(ConfigException, match="No files matched"):
                configs._load_effective_config(main)

    def test_glob_without_match_is_ignored(self, configs):
        with tempfile.TemporaryDirectory() as tmpdir:
            main = self._tree(tmpdir, {"main.yaml": {"version": 3, "include": ["none/*.yaml"],
                                                     "outputs": {"o": {"module": "m"}}}})
            config, includes = configs._load_effective_config(main)
        assert config["outputs"] == {"o": {"module": "m"}}
        assert includes == []

    def test_go_parity_precedence(self, configs):
        """Mirrors go-limacharlie OrgConfig.Merge applied as parent.Merge(include) in order."""
        with tempfile.TemporaryDirectory() as tmpdir:
            main = self._tree(tmpdir, {
                "main.yaml": {
                    "version": 3, "include": ["one.yaml", "two.yaml"],
                    "extensions": ["ext-a"],
                    "resources": {"replicant": ["r1"]},
                    "hives": {"dr-general": {"keep": self._rec("main"), "shared": self._rec("main")}},
                    "org-value": {"v": "main"},
                    "installation_keys": {"k": {"desc": "main"}},
                    "exfil": {"performance": {"p": 1}, "events": {"e": {"events": ["main"]}}},
                    "rules": {"legacy": {"detect": "main"}},
                },
                "one.yaml": {
                    "version": 3,
                    "extensions": ["ext-b", "ext-a"],
                    "resources": {"replicant": ["r2", "r1"], "other": ["x"]},
                    "hives": {"dr-general": {"shared": self._rec("one"), "one": self._rec("one")}, "fp": {"f": self._rec("one")}},
                    "org-value": {"v": "one", "w": "one"},
                    "installation_keys": {"k": {"desc": "one"}},
                    "exfil": {"performance": {"p": 2, "q": 2}, "watches": {"w": {"value": "one"}}},
                    "rules": {"legacy": {"detect": "one"}},
                    "yara": {"rules": {"yr": {"rule": "one"}}, "sources": {"ys": {"source": "one"}}},
                },
                "two.yaml": {
                    "version": 3,
                    "extensions": ["ext-c"],
                    "resources": {"replicant": ["r3"]},
                    "hives": {"dr-general": {"shared": self._rec("two")}},
                    "org-value": {"v": "two"},
                    "installation_keys": {"k": {"desc": "two"}},
                    "exfil": {"performance": {"p": 3}, "events": {"e": {"events": ["two"]}}},
                    "fps": {"fp1": {"data": "two"}},
                    "yara": {"rules": {"yr2": {"rule": "two"}}},
                },
            })
            config, _ = configs._load_effective_config(main)

        assert config["hives"] == {
            "dr-general": {"keep": self._rec("main"), "shared": self._rec("two"), "one": self._rec("one")},
            "fp": {"f": self._rec("one")},
        }
        assert config["org-value"] == {"v": "two", "w": "one"}
        assert config["installation_keys"] == {"k": {"desc": "two"}}
        assert config["exfil"] == {
            "performance": {"p": 3, "q": 2},
            "events": {"e": {"events": ["two"]}},
            "watches": {"w": {"value": "one"}},
        }
        assert config["resources"] == {"replicant": ["r1", "r2", "r3"], "other": ["x"]}
        assert config["extensions"] == ["ext-a", "ext-b", "ext-c"]
        assert config["rules"] == {"legacy": {"detect": "one"}}
        assert config["fps"] == {"fp1": {"data": "two"}}
        assert config["yara"] == {"rules": {"yr": {"rule": "one"}, "yr2": {"rule": "two"}},
                                  "sources": {"ys": {"source": "one"}}}


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
            "cloudsec_policy", "cloudsec_provider", "cloudsec_query",
            "cloudsec_code_rule", "mailsec_provider",
            "acl", "dr-mail", "mailsec_policy", "app_control_policy", "app_control_rule", "dr-general", "dr-managed", "dr-service", "fp",
            "cloud_sensor", "extension_config", "yara", "lookup",
            "secret", "query", "playbook", "ai_agent",
            "ai_skill", "ai_memory", "external_adapter",
        }
        assert Configs.ALL_HIVES == expected

    def test_no_use_extension_parameter(self):
        """Configs no longer accepts use_extension; it always uses the extension."""
        import inspect
        sig = inspect.signature(Configs.__init__)
        assert "use_extension" not in sig.parameters
