"""The CLI must preserve target-specific event layouts at the Replay boundary."""
import json
from unittest.mock import patch

import pytest
from click.testing import CliRunner
from limacharlie.cli import cli


@pytest.mark.parametrize("target,stream,event", [
    ("edr", "event", {"routing": {"event_type": "NEW_PROCESS"}, "event": {}}),
    ("detection", "detect", {"cat": "original-report", "routing": {"event_type": "NEW_PROCESS"}}),
    ("audit", "audit", {"etype": "user_login", "oid": "org"}),
    ("schedule", "event", {"routing": {"event_type": "1h_per_org"}, "event": {"frequency": 3600}}),
])
def test_inline_target_selects_replay_layout(tmp_path, target, stream, event):
    rule = {"detect": {"target": target, "op": "exists", "path": "marker"},
            "respond": [{"action": "report", "name": "fixture"}]}
    rp, ep = tmp_path / "rule.json", tmp_path / "events.json"
    rp.write_text(json.dumps(rule))
    ep.write_text(json.dumps([event]))
    with patch("limacharlie.commands.dr._get_org"), patch("limacharlie.commands.dr.ReplaySDK") as replay:
        replay.return_value.scan_events.return_value = {"did_match": True}
        result = CliRunner().invoke(cli, ["dr", "test", "--input-file", str(rp), "--events", str(ep)])
        assert result.exit_code == 0, result.output
        call = replay.return_value.scan_events.call_args
        assert call.args[0] == [event]
        assert call.kwargs["rule_content"] == rule
        assert call.kwargs["stream"] == stream


@pytest.mark.parametrize("stream", [None, "event", "detect", "audit"])
def test_named_rule_accepts_explicit_stream(tmp_path, stream):
    ep = tmp_path / "events.json"
    ep.write_text('[{"etype":"login"}]')
    with patch("limacharlie.commands.dr._get_org"), patch("limacharlie.commands.dr.ReplaySDK") as replay:
        replay.return_value.scan_events.return_value = {"did_match": False}
        args = ["dr", "test", "--name", "existing", "--namespace", "managed", "--events", str(ep)]
        if stream:
            args += ["--stream", stream]
        result = CliRunner().invoke(cli, args)
        assert result.exit_code == 0, result.output
        call = replay.return_value.scan_events.call_args
        assert call.kwargs["stream"] == (stream or "event")
        assert call.kwargs["rule_name"] == "existing"
        assert call.kwargs["namespace"] == "managed"
