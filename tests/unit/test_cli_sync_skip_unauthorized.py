"""`sync pull --all-available` skips hives the key cannot read; explicit hive flags stay strict."""

import base64
import gzip
import json
from unittest.mock import MagicMock

import pytest
import yaml
from click.testing import CliRunner

from limacharlie.cli import cli
from limacharlie.sdk.configs import Configs


@pytest.fixture
def transport(monkeypatch):
    org = MagicMock()
    org.oid = "test-oid"
    org.client._jwt = "sync-test-jwt"
    monkeypatch.setattr("limacharlie.commands.sync._get_org", lambda _ctx: org)
    return org.client.request


def _payload(*args, **kwargs):
    params = kwargs["params"]
    assert params["action"] == "fetch"
    return json.loads(gzip.decompress(base64.b64decode(params["gzdata"])))


def _invoke(tmp_path, *args):
    path = tmp_path / "org.yaml"
    result = CliRunner(mix_stderr=False).invoke(
        cli, ["sync", "pull", "--config-file", str(path), *args])
    return result, path


SKIPPED = [
    {"hive": "host_posture_rule", "permission": "host_posture.get", "error": "UNAUTHORIZED"},
    {"hive": "app_control_rule", "error": "UNAUTHORIZED - no access"},
]


def test_all_available_sends_flag_warns_per_skipped_hive_and_writes_file(tmp_path, transport):
    seen = []

    def fake(*args, **kwargs):
        seen.append(_payload(*args, **kwargs))
        return {"data": {"org": {"version": 3, "hives": {"fp": {}}}, "skipped_hives": SKIPPED}}

    transport.side_effect = fake
    result, path = _invoke(tmp_path, "--all-available")
    assert result.exit_code == 0, result.output
    assert seen[0]["options"]["skip_unauthorized_hives"] is True
    assert yaml.safe_load(path.read_text()) == {"version": 3, "hives": {"fp": {}}}
    assert ("Warning: skipped hive host_posture_rule: this key lacks host_posture.get; "
            "grant it to include this hive in the sync.") in result.stderr
    assert "Warning: skipped hive app_control_rule:" in result.stderr
    assert result.stderr.count("Warning: skipped hive") == 2


def test_warning_survives_quiet(tmp_path, transport):
    transport.side_effect = lambda *a, **k: {
        "data": {"org": {"version": 3}, "skipped_hives": SKIPPED[:1]}}
    path = tmp_path / "org.yaml"
    result = CliRunner(mix_stderr=False).invoke(
        cli, ["--quiet", "sync", "pull", "--config-file", str(path), "--all-available"])
    assert result.exit_code == 0, result.output
    assert "skipped hive host_posture_rule" in result.stderr
    assert result.stdout == ""
    assert path.exists()


def test_explicit_hive_flag_stays_strict(tmp_path, transport):
    seen = []

    def fake(*args, **kwargs):
        seen.append(_payload(*args, **kwargs))
        return {"data": {"org": {"version": 3, "hives": {}}}}

    transport.side_effect = fake
    result, _ = _invoke(tmp_path, "--hive-host-posture-rule")
    assert result.exit_code == 0, result.output
    assert "skip_unauthorized_hives" not in seen[0]["options"]
    assert "Warning" not in result.stderr


def test_all_available_with_explicit_flags_is_lenient(tmp_path, transport):
    seen = []

    def fake(*args, **kwargs):
        seen.append(_payload(*args, **kwargs))
        return {"data": {"org": {"version": 3}}}

    transport.side_effect = fake
    result, _ = _invoke(tmp_path, "--all-available", "--hive-fp")
    assert result.exit_code == 0, result.output
    assert seen[0]["options"]["skip_unauthorized_hives"] is True


def test_old_backend_without_skipped_hives_works(tmp_path, transport):
    transport.side_effect = lambda *a, **k: {"data": {"org": {"version": 3, "hives": {"fp": {}}}}}
    result, path = _invoke(tmp_path, "--all-available")
    assert result.exit_code == 0, result.output
    assert "Warning" not in result.stderr
    assert yaml.safe_load(path.read_text())["hives"] == {"fp": {}}


def test_sdk_fetch_keeps_returning_org_dict(transport):
    transport.side_effect = lambda *a, **k: {
        "data": {"org": {"version": 3}, "skipped_hives": SKIPPED}}
    org = MagicMock()
    org.client.request = transport
    configs = Configs(org)
    assert configs.fetch(sync_hives={"fp": True}, skip_unauthorized_hives=True) == {"version": 3}
    report = configs.fetch_with_report(sync_hives={"fp": True}, skip_unauthorized_hives=True)
    assert report["skipped_hives"] == SKIPPED


def test_push_all_never_sends_skip_flag(tmp_path, transport):
    f = tmp_path / "org.yaml"
    f.write_text("version: 3\nhives:\n  fp: {}\n")
    seen = []

    def fake(*args, **kwargs):
        params = kwargs["params"]
        seen.append(json.loads(gzip.decompress(base64.b64decode(params["gzdata"]))))
        return {"data": {"ops": []}}

    transport.side_effect = fake
    result = CliRunner().invoke(cli, ["sync", "push", "--config-file", str(f), "--all"])
    assert result.exit_code == 0, result.output
    assert "skip_unauthorized_hives" not in seen[0]["options"]


def test_all_stays_strict_and_does_not_send_flag(tmp_path, transport):
    seen = []

    def fake(*args, **kwargs):
        seen.append(_payload(*args, **kwargs))
        return {"data": {"org": {"version": 3}}}

    transport.side_effect = fake
    result, _ = _invoke(tmp_path, "--all")
    assert result.exit_code == 0, result.output
    assert "skip_unauthorized_hives" not in seen[0]["options"]
    assert seen[0]["options"]["sync_hives"]["host_posture_rule"] is True


def test_all_available_selects_same_set_as_all(tmp_path, transport):
    seen = []

    def fake(*args, **kwargs):
        seen.append(_payload(*args, **kwargs))
        return {"data": {"org": {"version": 3}}}

    transport.side_effect = fake
    _invoke(tmp_path, "--all")
    _invoke(tmp_path, "--all-available")
    strict = {k: v for k, v in seen[0]["options"].items()}
    lenient = {k: v for k, v in seen[1]["options"].items() if k != "skip_unauthorized_hives"}
    assert strict == lenient


def test_all_and_all_available_are_mutually_exclusive(tmp_path, transport):
    result, path = _invoke(tmp_path, "--all", "--all-available")
    assert result.exit_code == 4
    assert "cannot be used together" in result.stderr
    transport.assert_not_called()
    assert not path.exists()


def test_push_rejects_all_available(tmp_path, transport):
    f = tmp_path / "org.yaml"
    f.write_text("version: 3\n")
    result = CliRunner(mix_stderr=False).invoke(
        cli, ["sync", "push", "--config-file", str(f), "--all-available"])
    assert result.exit_code == 2
    transport.assert_not_called()


UNKNOWN = [
    {"hive": "investigation_policy", "reason": "unknown_hive", "error": "UNKNOWN_HIVE"},
]
UNKNOWN_NOTE = ("Note: skipped hive investigation_policy: it is not available for this "
                "organization, so there is nothing to back up.")


@pytest.mark.parametrize("flag", ["--all", "--all-available", "--hive-fp"])
def test_unknown_hive_prints_note_exits_0_and_writes_file(tmp_path, transport, flag):
    transport.side_effect = lambda *a, **k: {
        "data": {"org": {"version": 3, "hives": {"fp": {}}}, "skipped_hives": UNKNOWN}}
    result, path = _invoke(tmp_path, flag)
    assert result.exit_code == 0, result.output
    assert UNKNOWN_NOTE in result.stderr
    assert "Warning" not in result.stderr
    assert yaml.safe_load(path.read_text()) == {"version": 3, "hives": {"fp": {}}}


def test_unknown_hive_note_survives_quiet(tmp_path, transport):
    transport.side_effect = lambda *a, **k: {
        "data": {"org": {"version": 3}, "skipped_hives": UNKNOWN}}
    path = tmp_path / "org.yaml"
    result = CliRunner(mix_stderr=False).invoke(
        cli, ["--quiet", "sync", "pull", "--config-file", str(path), "--all"])
    assert result.exit_code == 0, result.output
    assert UNKNOWN_NOTE in result.stderr
    assert path.exists()


def test_mixed_reasons_and_explicit_unauthorized_reason(tmp_path, transport):
    transport.side_effect = lambda *a, **k: {"data": {"org": {"version": 3}, "skipped_hives": [
        UNKNOWN[0],
        {"hive": "host_posture_rule", "permission": "host_posture.get",
         "reason": "unauthorized", "error": "UNAUTHORIZED"},
    ]}}
    result, _ = _invoke(tmp_path, "--all-available")
    assert result.exit_code == 0, result.output
    assert UNKNOWN_NOTE in result.stderr
    assert ("Warning: skipped hive host_posture_rule: this key lacks host_posture.get; "
            "grant it to include this hive in the sync.") in result.stderr


def test_no_reason_entry_keeps_old_text(tmp_path, transport):
    transport.side_effect = lambda *a, **k: {"data": {"org": {"version": 3}, "skipped_hives": [
        {"hive": "app_control_rule", "error": "UNAUTHORIZED - no access"}]}}
    result, _ = _invoke(tmp_path, "--all")
    assert result.exit_code == 0, result.output
    assert ("Warning: skipped hive app_control_rule: this key is not authorized to read it "
            "(UNAUTHORIZED - no access); grant access to include this hive in the sync.") in result.stderr
    assert "Note:" not in result.stderr
