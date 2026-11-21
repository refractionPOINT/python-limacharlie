"""Investigation hive records are read with the YAML 1.2 boolean rule; nothing else is.

PyYAML reads the bare words on/off/yes/no as booleans (YAML 1.1). The investigation services read them as
text, and ``ai_may_decide: {"*": off}`` sent as ``false`` is refused by the Hive (``policy_type``). Every
other file the CLI reads keeps ``yaml.safe_load`` and its YAML 1.1 meaning: existing customer files rely on it.
"""

from unittest.mock import MagicMock, patch

import pytest
import yaml
from click.testing import CliRunner

from limacharlie.cli import cli
from limacharlie.sdk.hive import HiveRecord
from limacharlie.sdk.configs import Configs
from limacharlie.yaml_input import load_record_yaml, load_yaml

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


class TestLoadRecordYaml:
    @pytest.mark.parametrize("hive_name", ["investigation_policy", "investigation_plan"])
    def test_the_investigation_hives_use_the_yaml_12_rule(self, hive_name):
        assert load_record_yaml("a: off\nb: yes\n", hive_name) == {"a": "off", "b": "yes"}

    @pytest.mark.parametrize("hive_name", ["dr-general", "dr-service", "secret", "lookup", "extension_config", "fp", "cloud_sensor", "", None])
    def test_every_other_hive_keeps_safe_load(self, hive_name):
        text = "a: off\nb: yes\nc: [on, no]\nd: 012\ne: 2026-11-10\n"
        assert load_record_yaml(text, hive_name) == yaml.safe_load(text)
        assert load_record_yaml("a: off", hive_name) == {"a": False}


def _hive():
    hive = MagicMock()
    hive.get_metadata.return_value = HiveRecord("k")
    hive.set.return_value = {"guid": "g1"}
    return hive


DR_RULE = "detect:\n  event: NEW_PROCESS\n  op: is\n  path: event/FILE_IS_SIGNED\n  value: on\nrespond:\n  - action: report\n    name: x\nenabled: yes\n"


@patch("limacharlie.commands.hive.Client")
@patch("limacharlie.commands.hive.Organization")
@patch("limacharlie.commands.hive.Hive")
class TestHiveSet:
    def _set(self, mock_hive_cls, hive_name, key, path=None, stdin=None):
        hive = _hive()
        mock_hive_cls.return_value = hive
        args = ["hive", "set", "--hive-name", hive_name, "--key", key]
        if path:
            args += ["--input-file", str(path)]
        result = CliRunner().invoke(cli, args, input=stdin)
        assert result.exit_code == 0, result.output
        return hive.set.call_args[0][0]

    def test_an_investigation_policy_file_keeps_off_as_a_string(self, mock_hive_cls, _org, _client, tmp_path):
        path = tmp_path / "policy.yaml"
        path.write_text(POLICY, encoding="utf-8")
        record = self._set(mock_hive_cls, "investigation_policy", "default", path)
        assert record.data == WANT and record.data["ai_may_decide"]["*"] == "off"

    def test_investigation_policy_stdin_keeps_off_as_a_string(self, mock_hive_cls, _org, _client):
        assert self._set(mock_hive_cls, "investigation_policy", "default", stdin=POLICY).data == WANT

    def test_an_investigation_plan_keeps_off_as_a_string(self, mock_hive_cls, _org, _client, tmp_path):
        path = tmp_path / "plan.yaml"
        path.write_text("description: d\ngather:\n  a: {op: plan.pick, args: {value: off}}\n", encoding="utf-8")
        assert self._set(mock_hive_cls, "investigation_plan", "p", path).data["gather"]["a"]["args"]["value"] == "off"

    def test_a_data_wrapper_for_a_policy_keeps_off_and_the_metadata(self, mock_hive_cls, _org, _client, tmp_path):
        path = tmp_path / "wrapped.yaml"
        path.write_text("data:\n  ai_may_decide: {'*': off}\nusr_mtd:\n  enabled: true\n", encoding="utf-8")
        record = self._set(mock_hive_cls, "investigation_policy", "default", path)
        assert record.data == {"ai_may_decide": {"*": "off"}} and record.enabled is True

    def test_a_dr_rule_behaves_exactly_as_before(self, mock_hive_cls, _org, _client, tmp_path):
        path = tmp_path / "rule.yaml"
        path.write_text(DR_RULE, encoding="utf-8")
        record = self._set(mock_hive_cls, "dr-general", "r", path)
        assert record.data == yaml.safe_load(DR_RULE)
        assert record.data["detect"]["value"] is True and record.data["enabled"] is True

    def test_a_dr_rule_on_stdin_behaves_exactly_as_before(self, mock_hive_cls, _org, _client):
        assert self._set(mock_hive_cls, "dr-general", "r", stdin=DR_RULE).data["detect"]["value"] is True

    def test_an_output_with_enabled_yes_behaves_exactly_as_before(self, mock_hive_cls, _org, _client, tmp_path):
        path = tmp_path / "out.yaml"
        path.write_text("data:\n  module: s3\nusr_mtd:\n  enabled: yes\n", encoding="utf-8")
        record = self._set(mock_hive_cls, "extension_config", "o", path)
        assert record.enabled is True and record.data == {"module": "s3"}


@pytest.fixture
def configs():
    return Configs(MagicMock())


def _config(tmp_path, body):
    path = tmp_path / "config.yaml"
    path.write_text("version: 3\n" + body, encoding="utf-8")
    return str(path)


class TestSyncConfig:
    def test_investigation_hives_keep_off_as_a_string(self, configs, tmp_path):
        path = _config(tmp_path, "hives:\n  investigation_policy:\n    default:\n      data:\n        ai_may_decide: {'*': off}\n"
                                 "  investigation_plan:\n    p:\n      data: {description: d, gather: {a: {op: plan.pick, args: {value: no}}}}\n")
        config, _ = configs._load_effective_config(path)
        assert config["hives"]["investigation_policy"]["default"]["data"]["ai_may_decide"] == {"*": "off"}
        assert config["hives"]["investigation_plan"]["p"]["data"]["gather"]["a"]["args"]["value"] == "no"

    def test_everything_else_in_the_same_file_keeps_its_yaml_11_meaning(self, configs, tmp_path):
        body = ("hives:\n  investigation_policy:\n    default:\n      data:\n        ai_may_decide: {'*': off}\n"
                "  dr-general:\n    r:\n      data: {detect: {op: is, value: on}, respond: []}\n      usr_mtd: {enabled: yes}\n"
                "outputs:\n  o1: {module: s3, enabled: yes, flag: off}\n")
        config, _ = configs._load_effective_config(_config(tmp_path, body))
        assert config["hives"]["investigation_policy"]["default"]["data"]["ai_may_decide"] == {"*": "off"}
        assert config["hives"]["dr-general"]["r"]["data"]["detect"]["value"] is True
        assert config["hives"]["dr-general"]["r"]["usr_mtd"]["enabled"] is True
        assert config["outputs"]["o1"] == {"module": "s3", "enabled": True, "flag": False}

    def test_a_file_without_investigation_hives_is_loaded_exactly_as_before(self, configs, tmp_path):
        body = "hives:\n  dr-general:\n    r:\n      data: {value: on}\noutputs:\n  o1: {enabled: yes}\n"
        path = _config(tmp_path, body)
        config, _ = configs._load_effective_config(path)
        assert config == yaml.safe_load(open(path, encoding="utf-8").read())

    def test_an_included_file_keeps_the_rule_for_its_own_investigation_hives(self, configs, tmp_path):
        (tmp_path / "inc.yaml").write_text("version: 3\nhives:\n  investigation_policy:\n    default:\n      data:\n        ai_may_decide: {t: off}\n", encoding="utf-8")
        config, _ = configs._load_effective_config(_config(tmp_path, "include:\n  - inc.yaml\n"))
        assert config["hives"]["investigation_policy"]["default"]["data"]["ai_may_decide"] == {"t": "off"}

    def test_the_pushed_text_carries_the_string(self, configs, tmp_path):
        path = _config(tmp_path, "hives:\n  investigation_policy:\n    default:\n      data:\n        ai_may_decide: {'*': off}\n")
        config, _ = configs._load_effective_config(path)
        sent = yaml.safe_load(__import__("limacharlie.sdk.configs", fromlist=["x"])._dump_push_config(config))
        assert sent["hives"]["investigation_policy"]["default"]["data"]["ai_may_decide"] == {"*": "off"}


def test_investigate_template_files_keep_off_as_text():
    """`investigate templates save` reads the template with its own YAML 1.2 style parser, not safe_load."""
    from limacharlie.sdk.investigation import parse_template_source
    data = parse_template_source("description: d\ngather:\n  a: {op: plan.pick, args: {value: off}}\nrules: {escalate: [{id: r, when: off}]}\n")
    assert data["gather"]["a"]["args"]["value"] == "off" and data["rules"]["escalate"][0]["when"] == "off"
