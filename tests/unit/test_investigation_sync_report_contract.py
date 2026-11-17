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
from limacharlie.errors import ApiError, ValidationError, error_from_status_code
from limacharlie.sdk.configs import Configs
from limacharlie.sdk.investigation import Investigation, InvestigationError

FIXTURES = Path(__file__).parent / "fixtures" / "investigation_sync"

@pytest.mark.parametrize("name", ["first-install", "live-outage", "no-policy-permission", "paused", "reopenings"])
def test_report_fixture_passthrough(name):
    org = MagicMock(oid="fictional")
    page = json.loads((FIXTURES / (name + ".json")).read_text())
    org.client.request.return_value = page
    sdk = Investigation(org)
    method = sdk.list_reopenings if name == "reopenings" else sdk.get_track_record
    assert method(**{"product": "cases", "from": "2026-11-16T00:00:00-08:00", "limit": 100}) == page
    call = org.client.request.call_args
    assert call.args[:2] == ("GET", "investigate/fictional/track-record" + ("/reopenings" if name == "reopenings" else ""))
    assert dict(call.kwargs["query_params"])["from"] == "2026-11-16T00:00:00-08:00"

@pytest.mark.parametrize("transport", ["sdk", "cli-json", "cli-yaml"])
def test_first_install_has_no_reopen_or_dispute_history(transport):
    fixture = json.loads((FIXTURES / "first-install.json").read_text())
    org = MagicMock(oid="fictional")
    org.client.request.return_value = fixture
    sdk = Investigation(org)
    if transport == "sdk":
        page = sdk.get_track_record()
    else:
        output = transport.removeprefix("cli-")
        with patch("limacharlie.commands.investigate._get_investigation", return_value=sdk):
            result = CliRunner().invoke(cli, ["--output", output, "investigate", "track-record"])
        assert result.exit_code == 0, result.output
        page = yaml.safe_load(result.output)
    org.client.request.assert_called_once()
    assert org.client.request.call_args.args[:2] == ("GET", "investigate/fictional/track-record")
    assert page == fixture
    assert page["coverage"]["status"] == "healthy"
    assert page["coverage"]["complete"] is False
    for item in page["items"]:
        counts = item["counts"]
        assert counts["reopened_subjects"] == 0
        assert counts["disputed_subjects"] == 0
        assert counts["reopen_events_by_principal"] == {
            "user": 0, "api_key": 0, "ai_session": 0, "service": 0, "unknown": 0,
        }
        for guard in item["guards"]:
            assert guard["count"] == 0
            assert guard["status"] == "clear"


@pytest.mark.parametrize("output", ["json", "yaml"])
@pytest.mark.parametrize("command,method", [
    (["policy", "get"], "get_effective_policy"),
    (["track-record"], "get_track_record"),
])
def test_cli_preserves_resolved_mode_reason(output, command, method):
    policy = {
        "mode": "approve",
        "undo_supported": False,
        "reasons": ["irreversible_requires_exact_class"],
    }
    page = {"schema_version": 1, "items": [
        {"action_class": "eradicate.file", "policy": policy},
    ]}
    with patch("limacharlie.commands.investigate._get_investigation") as get:
        getattr(get.return_value, method).return_value = page
        result = CliRunner().invoke(cli, ["--output", output, "investigate"] + command)
    assert result.exit_code == 0, result.output
    assert yaml.safe_load(result.output) == page


@pytest.mark.parametrize("page", [{}, {"schema_version": 2}, {"schema_version": True}, {"routes": []}])
def test_report_schema_upgrade(page):
    org = MagicMock(oid="fictional")
    org.client.request.return_value = page
    with pytest.raises(InvestigationError) as err:
        Investigation(org).get_track_record()
    assert err.value.error_code == "upgrade_required"

@pytest.mark.parametrize("status,body,code", [(404, {}, "upgrade_required"), (503, {"error_code":"source_unavailable", "error":"source is unavailable"}, "source_unavailable"), (403, {"error_code":"forbidden"}, "forbidden"), (410, {"error_code":"cursor_expired"}, "cursor_expired")])
def test_report_errors(status, body, code):
    org = MagicMock(oid="fictional")
    org.client.request.side_effect = error_from_status_code(status, body)
    with pytest.raises(ApiError) as err:
        Investigation(org).list_reopenings()
    assert err.value.error_code == code

@pytest.mark.parametrize("method", ["get_track_record", "list_reopenings"])
@pytest.mark.parametrize("body", [{}, {"error": "not found"}])
def test_report_gateway_404_retains_disabled_guidance(method, body):
    org = MagicMock(oid="fictional")
    org.client.request.side_effect = error_from_status_code(404, body)
    with pytest.raises(InvestigationError) as err:
        getattr(Investigation(org), method)()
    assert err.value.error_code == "upgrade_required"
    assert "gated per deployment" in err.value.suggestion
    assert "region" in str(err.value)


@pytest.mark.parametrize("method", ["get_track_record", "list_reopenings"])
def test_report_engine_not_found_passes_through(method):
    org = MagicMock(oid="fictional")
    body = {"error_code": "not_found", "error": "unknown template"}
    org.client.request.side_effect = error_from_status_code(404, body)
    with pytest.raises(InvestigationError) as err:
        getattr(Investigation(org), method)()
    assert err.value.status_code == 404
    assert err.value.error_code == "not_found"
    assert err.value.response_body == body
    assert not err.value.suggestion


@pytest.mark.parametrize("filters", [{"route_id":"x"}, {"by":"robot"}, {"limit":True}, {"limit":201}, {"product":["cases"]}, {"cursor":""}, {"cursor":"é"*2049}])
def test_reopening_invalid_filters(filters):
    org = MagicMock(oid="fictional")
    with pytest.raises(ValidationError):
        Investigation(org).list_reopenings(**filters)
    org.client.request.assert_not_called()

@pytest.mark.parametrize("cmd,method,extra", [("track-record","get_track_record",["--route-id","fictional"]),("reopenings","list_reopenings",["--by","people"])])
def test_report_cli(cmd, method, extra):
    with patch("limacharlie.commands.investigate._get_investigation") as get:
        getattr(get.return_value, method).return_value = {"schema_version":1,"items":[],"next_cursor":"next"}
        result = CliRunner().invoke(cli, ["--output","json","investigate",cmd,"--product","cases","--from","2026-11-16T00:00:00-08:00","--cursor","opaque"]+extra)
        assert result.exit_code == 0, result.output
        assert json.loads(result.output)["next_cursor"] == "next"
        kw = getattr(get.return_value, method).call_args.kwargs
        assert kw["from"] == "2026-11-16T00:00:00-08:00"
        assert kw["cursor"] == "opaque"

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
