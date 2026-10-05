"""Exercise Code Security identities, bounded writes and honest paging."""
import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from limacharlie.cli import cli
from limacharlie.commands import cloudsec as commands
from limacharlie.sdk.cloudsec import CloudSec, chain_stage_summary
from limacharlie.sdk.iac_map import _TYPES, validate_iac_map

FIXTURES = Path(__file__).parent / "fixtures"


def test_full_iac_wire_vocabulary_and_preflight():
    pinned = (FIXTURES / "iac-map-vocabulary.txt").read_text().rstrip("\n")
    actual = "\n".join(" ".join((name, provider, *sorted(controls)))
                       for name, (provider, controls) in sorted(_TYPES.items()))
    assert actual == pinned
    document = json.loads((FIXTURES / "iac-map-v1.json").read_bytes())
    document["source_kind"] = "plan_desired"
    document["resources"] = [
        {"address": name + ".example", "type": name, "provider": provider,
         "scope": {}, "identity": {"name": "example"},
         "desired": {control: True for control in controls}}
        for name, (provider, controls) in _TYPES.items()]
    raw = json.dumps(document).encode()
    assert validate_iac_map(raw) == raw
    org = MagicMock(oid="tenant")
    CloudSec(org).push_iac_map(raw)
    assert org.client.request.call_args.kwargs["raw_body"] == raw
    for resource in document["resources"]:
        original = resource["desired"]
        resource["desired"] = {"arbitrary_control": True}
        with pytest.raises(ValueError):
            validate_iac_map(json.dumps(document))
        resource["desired"] = original


def _git(checkout, *args):
    return subprocess.run(["git", "-C", str(checkout), *args],
                          check=True, capture_output=True, text=True).stdout.strip()


def _checkout(checkout, remote, default_branch):
    _git(checkout, "init", "--initial-branch=topic")
    _git(checkout, "-c", "user.name=Test", "-c", "user.email=test@example.com",
         "commit", "--allow-empty", "-m", "Test fixture")
    if remote:
        _git(checkout, "remote", "add", "origin", remote)
    if default_branch:
        _git(checkout, "update-ref", "refs/remotes/origin/" + default_branch, "HEAD")
        _git(checkout, "symbolic-ref", "refs/remotes/origin/HEAD",
             "refs/remotes/origin/" + default_branch)


def _scan(args, monkeypatch):
    cs = MagicMock()
    cs.ingest_code_results.return_value = {"result": {"accepted": True}}
    monkeypatch.setattr(commands, "_get_cloudsec", lambda _: cs)
    def scanner(spec, root, report_path, workdir, **kwargs):
        Path(report_path).write_bytes(b'{"schema":"lc-code-report/v1"}')
    monkeypatch.setattr(commands, "_run_code_scanner", scanner)
    result = CliRunner().invoke(cli, ["--output", "json", "cloudsec", "code", "scan", *args])
    return result, cs


@pytest.mark.parametrize("remote,provider,key", [
    ("git@github.com:acme/api.git", "github", "acme/api"),
    ("https://gitlab.com/acme/platform/api.git", "gitlab", "acme/platform/api"),
    ("ssh://git@gitlab.com:2222/acme/platform/api.git", "gitlab", "acme/platform/api"),
    ("https://user@bitbucket.org/acme/api.git", "bitbucket", "acme/api"),
])
def test_scan_infers_remote_identity_and_origin_default(tmp_path, monkeypatch, remote, provider, key):
    _checkout(tmp_path, remote, "shipping")
    result, cs = _scan([str(tmp_path), "--ingest", "--ref", "refs/heads/shipping"], monkeypatch)
    assert result.exit_code == 0, result.output
    call = cs.ingest_code_results.call_args
    assert call.args[:2] == (key, "report")
    assert call.kwargs == {"commit": _git(tmp_path, "rev-parse", "HEAD"),
                           "ref": "refs/heads/shipping", "default_branch": "shipping",
                           "provider": provider}


def test_scan_explicit_provider_and_branch_override_origin(tmp_path, monkeypatch):
    _checkout(tmp_path, "ssh://git@scm.example.com/acme/api.git", "shipping")
    result, cs = _scan([str(tmp_path), "--ingest", "--provider", "gitlab",
                        "--default-branch", "release", "--ref", "refs/heads/release"], monkeypatch)
    assert result.exit_code == 0, result.output
    assert cs.ingest_code_results.call_args.kwargs["provider"] == "gitlab"
    assert cs.ingest_code_results.call_args.kwargs["default_branch"] == "release"


@pytest.mark.parametrize("remote", ["git@scm.example.com:acme/api.git", None,
                                   "https://github.com.example.com/acme/api.git"])
def test_scan_unknown_host_requires_provider_before_scanning(tmp_path, monkeypatch, remote):
    _checkout(tmp_path, remote, None)
    with patch.object(commands, "_run_code_scanner") as scanner:
        result = CliRunner().invoke(cli, ["cloudsec", "code", "scan", str(tmp_path),
                                         "--repo", "acme/api", "--ingest"])
    assert result.exit_code != 0
    assert "--provider" in result.output
    scanner.assert_not_called()


def test_scan_does_not_guess_a_default_branch(tmp_path, monkeypatch):
    _checkout(tmp_path, "git@github.com:acme/api.git", None)
    result, cs = _scan([str(tmp_path), "--ingest"], monkeypatch)
    assert result.exit_code == 0, result.output
    assert cs.ingest_code_results.call_args.kwargs["default_branch"] is None


@pytest.mark.parametrize("status,expected", [("unknown", ""), ("partial", ""),
                                            ("not_applicable", ""), ("proven", "not_running")])
def test_not_running_requires_proven_evidence(status, expected):
    result = chain_stage_summary({"chain": {"stages": [
        {"stage": "running", "status": status, "outcome": "not_running"}]}})
    assert result[0]["outcome"] == expected


@pytest.mark.parametrize("total,truncated", [(10021, True), (2, False)])
def test_fixes_all_preserves_total_scope_and_truncation(monkeypatch, total, truncated):
    cs = MagicMock()
    cs.get_code_fixes.side_effect = [
        {"fixes": [{"cause_key": "one"}], "distinct": total, "next_cursor": "next"},
        {"fixes": [{"cause_key": "two"}], "distinct": total, "next_cursor": "",
         "scope": "open repository SCA", "caveat": "repository findings only"}]
    monkeypatch.setattr(commands, "_get_cloudsec", lambda _: cs)
    result = CliRunner().invoke(cli, ["--output", "json", "cloudsec", "code", "fixes", "--all"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["distinct"] == total and payload["truncated"] is truncated
    assert payload["scope"] == "open repository SCA"
    assert payload["caveat"] == "repository findings only"
    assert payload["fixes"] == [{"cause_key": "one"}, {"cause_key": "two"}]
    assert [c.kwargs["cursor"] for c in cs.get_code_fixes.call_args_list] == [None, "next"]


def test_fixes_refuses_repeating_cursor(monkeypatch):
    cs = MagicMock()
    cs.get_code_fixes.return_value = {"fixes": [], "distinct": 1, "next_cursor": "same"}
    monkeypatch.setattr(commands, "_get_cloudsec", lambda _: cs)
    result = CliRunner().invoke(cli, ["cloudsec", "code", "fixes", "--all"])
    assert result.exit_code != 0 and "incomplete" in result.output
    assert cs.get_code_fixes.call_count == 2


def test_bulk_resolution_limit_applies_before_network(monkeypatch):
    ids = ["fnd_" + str(n).zfill(32) for n in range(501)]
    org = MagicMock(oid="tenant")
    with pytest.raises(ValueError, match="500"):
        CloudSec(org).bulk_set_finding_status(ids, "mitigated")
    org.client.request.assert_not_called()
    CloudSec(org).bulk_set_finding_status(ids[:500], "mitigated")
    assert json.loads(org.client.request.call_args.kwargs["raw_body"])["finding_ids"] == ids[:500]
    cs = MagicMock()
    cs.bulk_set_finding_status.return_value = {"updated": 500}
    monkeypatch.setattr(commands, "_get_cloudsec", lambda _: cs)
    args = ["cloudsec", "finding", "bulk-resolve", "--kind", "mitigated"]
    for finding_id in ids:
        args.extend(["--finding-id", finding_id])
    result = CliRunner().invoke(cli, args)
    assert result.exit_code != 0 and "500" in result.output
    cs.bulk_set_finding_status.assert_not_called()
    result = CliRunner().invoke(cli, args[:-2])
    assert result.exit_code == 0, result.output
    assert cs.bulk_set_finding_status.call_args.args[0] == ids[:500]
