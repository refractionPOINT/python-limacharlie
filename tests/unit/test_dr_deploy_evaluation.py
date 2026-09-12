import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from limacharlie.errors import ApiError, NotFoundError
from limacharlie.sdk.dr_deploy import deploy


@pytest.fixture
def setup(tmp_path, monkeypatch):
    candidate = {"data": {"detect": {"event": "NEW_PROCESS", "op": "exists", "path": "event/FILE_PATH"},
                          "respond": [{"action": "report", "name": "test"}]},
                 "usr_mtd": {"enabled": False, "tags": ["preserve"]}}
    paths = [tmp_path / p for p in ("candidate.json", "yes.json", "no.json")]
    for p, value in zip(paths, (candidate, [{"event": {"FILE_PATH": "a"}}], [{"event": {}}])):
        p.write_text(json.dumps(value))
    client = Mock()
    client.request.side_effect = [NotFoundError("missing"), {}, candidate]
    org = SimpleNamespace(oid="00000000-0000-4000-8000-000000000001", client=client,
                          who_am_i=Mock(return_value={"perms": ["ai_agent.operate"]}))
    replay = Mock()
    replay.scan_events.side_effect = [
        {"stats": {"n_proc": 1}, "results": [{}], "did_match": True},
        {"stats": {"n_proc": 1}, "results": [], "did_match": False}]
    monkeypatch.setattr("limacharlie.sdk.dr_deploy.Replay", lambda _: replay)
    return org, paths, candidate, replay


def test_create_verified(setup):
    org, paths, candidate, replay = setup
    assert deploy(org, "test", *paths)["status"] == "verified"
    assert org.client.request.call_args_list[1].args[0] == "POST"
    assert all(not c.kwargs.get("dry_run", False) for c in replay.scan_events.call_args_list)


@pytest.mark.parametrize("fault", ["missing_enabled", "stale_etag", "metadata_loss", "permission", "partial",
                                  "positive_miss", "negative_match", "changed_file", "api_denial"])
def test_preconditions_never_write(setup, fault):
    org, paths, candidate, replay = setup
    if fault == "missing_enabled":
        candidate["usr_mtd"].pop("enabled"); paths[0].write_text(json.dumps(candidate))
    elif fault in ("stale_etag", "metadata_loss"):
        current = dict(candidate, sys_mtd={"etag": "current"})
        if fault == "metadata_loss": current["usr_mtd"] = dict(candidate["usr_mtd"], comment="keep")
        org.client.request.side_effect = [current]
    elif fault == "permission": org.who_am_i.return_value = {"perms": []}
    elif fault == "partial": replay.scan_events.side_effect = [{"stats": {"n_proc": 1, "results_partial": True}, "results": [], "did_match": True}]
    elif fault == "positive_miss": replay.scan_events.side_effect = [{"stats": {"n_proc": 1}, "results": [], "did_match": False}]
    elif fault == "negative_match": replay.scan_events.side_effect = [{"stats": {"n_proc": 1}, "results": [{}], "did_match": True}] * 2
    elif fault == "api_denial": org.client.request.side_effect = ApiError("denied", status_code=403)
    elif fault == "changed_file":
        def scan(*args, **kwargs):
            paths[0].write_text("changed")
            return {"stats": {"n_proc": 1}, "results": [], "did_match": replay.scan_events.call_count == 1}
        replay.scan_events.side_effect = scan
    with pytest.raises((ValueError, ApiError)):
        deploy(org, "test", *paths)
    assert not any(c.args[0] == "POST" for c in org.client.request.call_args_list)


def test_update_preserves_metadata_and_etag(setup):
    org, paths, candidate, _ = setup
    current = dict(candidate, sys_mtd={"etag": "current"})
    candidate["etag"] = "current"
    paths[0].write_text(json.dumps(candidate))
    org.client.request.side_effect = [current, {}, current]
    assert deploy(org, "test", *paths)["status"] == "verified"
    params = org.client.request.call_args_list[1].kwargs["params"]
    assert params["etag"] == "current"
    assert json.loads(params["usr_mtd"]) == candidate["usr_mtd"]


def test_unknown_write_outcome_is_not_retried(setup):
    org, paths, _, _ = setup
    org.client.request.side_effect = [NotFoundError("missing"), TimeoutError("lost reply")]
    with pytest.raises(TimeoutError): deploy(org, "test", *paths)
    assert sum(c.args[0] == "POST" for c in org.client.request.call_args_list) == 1


def test_readback_mismatch_is_not_success(setup):
    org, paths, _, _ = setup
    org.client.request.side_effect = [NotFoundError("missing"), {}, {"data": {}, "usr_mtd": {}}]
    with pytest.raises(ValueError, match="unverified"): deploy(org, "test", *paths)


def test_dry_run_never_writes(setup):
    org, paths, _, _ = setup
    assert deploy(org, "test", *paths, dry_run=True)["status"] == "previewed"
    assert org.client.request.call_count == 1
