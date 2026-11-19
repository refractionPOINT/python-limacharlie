"""Native investigation sync and report contract tests (no network)."""
import base64
import gzip
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from click.testing import CliRunner
from limacharlie.cli import cli
from limacharlie.commands.sync import _resolve_sync_flags
from limacharlie.errors import error_from_status_code
from limacharlie.sdk.configs import Configs
from limacharlie.sdk.investigation import Investigation, InvestigationError

FIXTURES = Path(__file__).parent / "fixtures" / "investigation_sync"

STATS_FIXTURE = {
    "window": {"since": "2026-11-16T00:00:00-08:00", "truncated": False},
    "actions": {
        "by_class_state": {"close.false_positive": {"executed": 8, "proposed": 2}},
        "by_template_class": [{
            "template": "fictional-triage",
            "action_class": "close.false_positive",
            "total": 12, "suggested": 3, "approved": 4, "denied": 1, "expired": 1,
            "auto_executed": 5, "failed": 0, "undone": 1, "held": 2,
            "held_by_reason": {"policy_no_approvers": 1, "rate_cap": 1},
            "by_state": {"executed": 8, "proposed": 2, "denied": 1, "expired": 1},
        }],
    },
    "feedback": {"labels": 4, "corrections": 1},
}


def test_get_stats_passes_scalars_and_response_through():
    org = MagicMock(oid="fictional")
    org.client.request.return_value = STATS_FIXTURE
    assert Investigation(org).get_stats(
        template="fictional-triage", since="2026-11-16T00:00:00-08:00", until="2026-11-17T00:00:00-08:00",
    ) == STATS_FIXTURE
    call = org.client.request.call_args
    assert call.args[:2] == ("GET", "investigate/fictional/stats")
    assert dict(call.kwargs["query_params"]) == {
        "template": "fictional-triage", "since": "2026-11-16T00:00:00-08:00", "until": "2026-11-17T00:00:00-08:00",
    }


def test_get_stats_omits_unset_parameters():
    org = MagicMock(oid="fictional")
    org.client.request.return_value = STATS_FIXTURE
    Investigation(org).get_stats(since="2026-11-16T00:00:00Z")
    assert dict(org.client.request.call_args.kwargs["query_params"]) == {"since": "2026-11-16T00:00:00Z"}
    Investigation(org).get_stats()
    assert not org.client.request.call_args.kwargs["query_params"]


@pytest.mark.parametrize("status,body,code", [
    (400, {"error_code": "bad_request", "error": "bad since"}, "bad_request"),
    (403, {"error_code": "forbidden"}, "forbidden"),
    (503, {"error_code": "unavailable", "error": "engine unavailable"}, "unavailable"),
])
def test_get_stats_errors_are_investigation_errors(status, body, code):
    org = MagicMock(oid="fictional")
    org.client.request.side_effect = error_from_status_code(status, body)
    with pytest.raises(InvestigationError) as err:
        Investigation(org).get_stats()
    assert err.value.status_code == status
    assert err.value.error_code == code


def test_get_stats_gateway_404_keeps_disabled_guidance():
    org = MagicMock(oid="fictional")
    org.client.request.side_effect = error_from_status_code(404, {})
    with pytest.raises(InvestigationError) as err:
        Investigation(org).get_stats()
    assert err.value.error_code is None
    assert "gated per deployment" in err.value.suggestion


@pytest.mark.parametrize("output", ["json", "yaml"])
def test_stats_cli_passes_filters_and_prints_the_response(output):
    with patch("limacharlie.commands.investigate._get_investigation") as get:
        get.return_value.get_stats.return_value = STATS_FIXTURE
        result = CliRunner().invoke(cli, [
            "--output", output, "investigate", "stats", "--template", "fictional-triage",
            "--since", "2026-11-16T00:00:00-08:00", "--until", "2026-11-17T00:00:00-08:00",
        ])
    assert result.exit_code == 0, result.output
    assert yaml.safe_load(result.output) == STATS_FIXTURE
    get.return_value.get_stats.assert_called_once_with(
        template="fictional-triage", since="2026-11-16T00:00:00-08:00", until="2026-11-17T00:00:00-08:00",
    )


def test_stats_cli_defaults_to_no_filters():
    with patch("limacharlie.commands.investigate._get_investigation") as get:
        get.return_value.get_stats.return_value = STATS_FIXTURE
        result = CliRunner().invoke(cli, ["--output", "json", "investigate", "stats"])
    assert result.exit_code == 0, result.output
    get.return_value.get_stats.assert_called_once_with(template=None, since=None, until=None)


@pytest.mark.parametrize("all_", [True, False])
def test_sync_selection(all_):
    flags = _resolve_sync_flags(all_, False,False,False,False,False,False,False,False,False, investigation_policy=True, investigation_plan=all_)
    assert flags["sync_hives"]["investigation_policy"]
    assert flags["sync_hives"].get("investigation_plan", False) == all_
    assert {"investigation_policy", "investigation_plan"} <= Configs.ALL_HIVES


def test_native_sync_fixture():
    cfg = yaml.safe_load((FIXTURES / "policy-plan.yaml").read_text())
    cfg["version"] = 3
    org = MagicMock(oid="fictional")
    org.client.request.return_value = {"data":{"org":cfg}}
    sdk = Configs(org)
    hives = {"investigation_policy":True,"investigation_plan":True}
    fetched = sdk.fetch(sync_hives=hives)
    assert fetched == cfg
    org.client.request.return_value = {"data":{"ops":[]}}
    results, errors = sdk.push(fetched, sync_hives=hives)
    assert errors == []
    # Verify opaque policy and metadata reach the extension unmodified.
    params = org.client.request.call_args.kwargs["params"]
    data = json.loads(gzip.decompress(base64.b64decode(params["gzdata"])))
    assert yaml.safe_load(data["config"]) == cfg
    assert data["options"]["sync_hives"] == hives

@pytest.mark.parametrize("flags", [["--investigation-policy", "--investigation-plan"], ["--all"]])
def test_sync_cli_native_roundtrip(tmp_path, flags):
    cfg = yaml.safe_load((FIXTURES / "policy-plan.yaml").read_text())
    cfg["version"] = 3
    seen = []
    def request(*args, **kwargs):
        payload = json.loads(gzip.decompress(base64.b64decode(kwargs["params"]["gzdata"])))
        seen.append(payload)
        assert payload["options"]["sync_hives"]["investigation_policy"]
        assert payload["options"]["sync_hives"]["investigation_plan"]
        if kwargs["params"]["action"] == "fetch":
            return {"data":{"org":cfg}}
        assert yaml.safe_load(payload["config"]) == cfg
        return {"data":{"ops":[]}}
    with patch("limacharlie.commands.sync._get_org") as get:
        get.return_value = MagicMock(oid="fictional")
        get.return_value.client.request.side_effect = request
        filename = str(tmp_path / "org.yaml")
        for verb in ("pull", "push"):
            result = CliRunner().invoke(cli, ["sync", verb, "--config-file", filename] + flags)
            assert result.exit_code == 0, (result.output, result.exception)
    assert len(seen) == 2
