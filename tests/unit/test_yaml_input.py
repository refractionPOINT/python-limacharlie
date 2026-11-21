"""Files and stdin that become hive or API records are read with the YAML 1.2 boolean rule.

PyYAML reads the bare words on/off/yes/no as booleans (YAML 1.1). The services read them as text, and
``ai_may_decide: {"*": off}`` sent as ``false`` is refused by the Hive (``policy_type``).
"""

from unittest.mock import MagicMock, patch

import pytest
import yaml
from click.testing import CliRunner

from limacharlie.cli import cli
from limacharlie.sdk.hive import HiveRecord
from limacharlie.sdk.configs import Configs
from limacharlie.yaml_input import load_yaml

POLICY = 'ai_may_decide:\n  mailsec-message: close_and_escalate\n  "*": off\nautonomy:\n  close.false_positive: {mode: suggest}\n'
WANT = {"ai_may_decide": {"mailsec-message": "close_and_escalate", "*": "off"}, "autonomy": {"close.false_positive": {"mode": "suggest"}}}


class TestLoadYaml:
    @pytest.mark.parametrize("word", ["on", "off", "yes", "no", "On", "Off", "YES", "No", "y", "n"])
    def test_the_yaml_11_boolean_words_stay_text(self, word):
        assert load_yaml(f"k: {word}\nl: [{word}]\n") == {"k": word, "l": [word]}
        assert yaml.safe_load(f"k: {word}") != {"k": word} or word in ("y", "n"), "PyYAML would have turned it into a boolean"

    @pytest.mark.parametrize("word,want", [("true", True), ("True", True), ("TRUE", True), ("false", False), ("False", False), ("FALSE", False)])
    def test_true_and_false_stay_booleans(self, word, want):
        got = load_yaml(f"k: {word}")["k"]
        assert got is want

    def test_quoted_words_and_other_scalars_read_as_before(self):
        assert load_yaml('a: "off"\nb: 012\nc: ~\nd: 1e3\ne: 2026-11-10\nf: [1, 2]\ng: "true"\n') == yaml.safe_load('a: "off"\nb: 012\nc: ~\nd: 1e3\ne: 2026-11-10\nf: [1, 2]\ng: "true"\n')

    def test_json_still_loads(self):
        assert load_yaml('{"a": [1, true, null, "off"]}') == {"a": [1, True, None, "off"]}

    def test_a_malformed_document_raises_like_safe_load(self):
        with pytest.raises(yaml.YAMLError):
            load_yaml("a: [unclosed\n")

    def test_it_is_a_safe_loader(self):
        with pytest.raises(yaml.YAMLError):
            load_yaml("!!python/object/apply:os.system ['true']")


def _hive():
    hive = MagicMock()
    hive.get_metadata.return_value = HiveRecord("k")
    hive.set.return_value = {"guid": "g1"}
    return hive


@patch("limacharlie.commands.hive.Client")
@patch("limacharlie.commands.hive.Organization")
@patch("limacharlie.commands.hive.Hive")
class TestHiveSet:
    def test_an_input_file_keeps_off_as_a_string(self, mock_hive_cls, _org, _client, tmp_path):
        hive = _hive()
        mock_hive_cls.return_value = hive
        path = tmp_path / "policy.yaml"
        path.write_text(POLICY, encoding="utf-8")
        result = CliRunner().invoke(cli, ["hive", "set", "--hive-name", "investigation_policy", "--key", "default", "--input-file", str(path)])
        assert result.exit_code == 0, result.output
        assert hive.set.call_args[0][0].data == WANT
        assert hive.set.call_args[0][0].data["ai_may_decide"]["*"] == "off"

    def test_stdin_keeps_off_as_a_string(self, mock_hive_cls, _org, _client):
        hive = _hive()
        mock_hive_cls.return_value = hive
        result = CliRunner().invoke(cli, ["hive", "set", "--hive-name", "investigation_policy", "--key", "default"], input=POLICY)
        assert result.exit_code == 0, result.output
        assert hive.set.call_args[0][0].data == WANT

    def test_a_record_with_a_data_wrapper_keeps_off_as_a_string(self, mock_hive_cls, _org, _client, tmp_path):
        hive = _hive()
        mock_hive_cls.return_value = hive
        path = tmp_path / "wrapped.yaml"
        path.write_text("data:\n  ai_may_decide: {'*': off}\nusr_mtd:\n  enabled: true\n", encoding="utf-8")
        result = CliRunner().invoke(cli, ["hive", "set", "--hive-name", "investigation_policy", "--key", "default", "--input-file", str(path)])
        assert result.exit_code == 0, result.output
        record = hive.set.call_args[0][0]
        assert record.data == {"ai_may_decide": {"*": "off"}}
        assert record.enabled is True


def test_a_sync_push_config_keeps_off_as_a_string(tmp_path):
    configs = Configs(MagicMock())
    path = tmp_path / "config.yaml"
    path.write_text("version: 3\nhives:\n  investigation_policy:\n    default:\n      data:\n        ai_may_decide: {'*': off}\n", encoding="utf-8")
    config, _ = configs._load_effective_config(str(path))
    assert config["hives"]["investigation_policy"]["default"]["data"]["ai_may_decide"] == {"*": "off"}
