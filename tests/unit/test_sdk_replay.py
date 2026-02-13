"""Tests for limacharlie.sdk.replay module."""

from unittest.mock import MagicMock
import json
import pytest

from limacharlie.sdk.replay import Replay


@pytest.fixture
def mock_org():
    org = MagicMock()
    org.oid = "test-oid"
    org.client = MagicMock()
    org.get_urls = MagicMock(return_value={"replay": "replay.lc.io"})
    org.service_request = MagicMock(return_value={"job_id": "j-1"})
    return org


@pytest.fixture
def replay(mock_org):
    return Replay(mock_org)


class TestReplayRun:
    def test_run_with_rule_name(self, replay, mock_org):
        replay.run(rule_name="my-rule", start=1000, end=2000)
        mock_org.service_request.assert_called_once()
        args, kwargs = mock_org.service_request.call_args
        assert args[0] == "replay"
        params = args[1]
        assert params["rule_name"] == "my-rule"
        assert params["start"] == "1000"
        assert params["end"] == "2000"
        assert kwargs["is_async"] is True

    def test_run_with_detect_respond_passes_dicts(self, replay, mock_org):
        detect = {"op": "is", "event": "NEW_PROCESS"}
        respond = [{"action": "report", "name": "test-det"}]
        replay.run(detect=detect, respond=respond, start=100, end=200)
        params = mock_org.service_request.call_args[0][1]
        # detect/respond should be native dicts, NOT json strings
        assert isinstance(params["detect"], dict)
        assert isinstance(params["respond"], list)
        assert params["detect"] == detect
        assert params["respond"] == respond

    def test_run_with_trace_and_dry_run(self, replay, mock_org):
        replay.run(rule_name="r", start=1, end=2, trace=True, dry_run=True)
        params = mock_org.service_request.call_args[0][1]
        assert params["trace"] == "true"
        assert params["dry_run"] == "true"

    def test_run_with_limits(self, replay, mock_org):
        replay.run(rule_name="r", start=1, end=2, limit_events=500, limit_evals=100)
        params = mock_org.service_request.call_args[0][1]
        assert params["limit_events"] == "500"
        assert params["limit_evals"] == "100"

    def test_run_with_sid(self, replay, mock_org):
        replay.run(rule_name="r", start=1, end=2, sid="sensor-abc")
        params = mock_org.service_request.call_args[0][1]
        assert params["sid"] == "sensor-abc"

    def test_run_with_selector(self, replay, mock_org):
        replay.run(rule_name="r", start=1, end=2, selector="plat == windows")
        params = mock_org.service_request.call_args[0][1]
        assert params["selector"] == "plat == windows"


class TestReplayScanEvents:
    def test_scan_events_with_rule_content(self, replay, mock_org):
        rule = {"detect": {"op": "is"}, "respond": [{"action": "report"}]}
        events = [{"event": {"type": "NEW_PROCESS"}, "routing": {"sid": "s-1"}}]
        mock_org.client.request.return_value = {"results": []}

        replay.scan_events(events=events, rule_content=rule)

        call_args = mock_org.client.request.call_args
        assert call_args[0][0] == "POST"
        assert call_args[0][1] == ""
        assert call_args[1]["alt_root"] == "https://replay.lc.io/"
        body = json.loads(call_args[1]["raw_body"])
        assert body["oid"] == "test-oid"
        assert body["rule_source"]["rule"] == rule
        assert body["event_source"]["events"] == events
        assert body["event_source"]["stream"] == "event"

    def test_scan_events_with_rule_name(self, replay, mock_org):
        mock_org.client.request.return_value = {}
        replay.scan_events(events=[], rule_name="existing-rule", namespace="general")
        body = json.loads(mock_org.client.request.call_args[1]["raw_body"])
        assert body["rule_source"]["rule_name"] == "existing-rule"
        assert body["rule_source"]["namespace"] == "general"

    def test_scan_events_trace_and_limits(self, replay, mock_org):
        mock_org.client.request.return_value = {}
        replay.scan_events(
            events=[], rule_content={}, trace=True,
            limit_events=10, limit_evals=5, dry_run=True,
        )
        body = json.loads(mock_org.client.request.call_args[1]["raw_body"])
        assert body["trace"] is True
        assert body["limit_event"] == 10
        assert body["limit_eval"] == 5
        assert body["is_dry_run"] is True

    def test_scan_events_caches_replay_url(self, replay, mock_org):
        mock_org.client.request.return_value = {}
        replay.scan_events(events=[], rule_content={})
        replay.scan_events(events=[], rule_content={})
        # get_urls should only be called once (cached)
        mock_org.get_urls.assert_called_once()


class TestReplayValidateRule:
    def test_validate_rule_sends_minimal_event(self, replay, mock_org):
        mock_org.client.request.return_value = {}
        rule = {"detect": {"op": "is"}, "respond": []}
        replay.validate_rule(rule)
        body = json.loads(mock_org.client.request.call_args[1]["raw_body"])
        assert body["event_source"]["events"] == [{"event": {}, "routing": {}}]
        assert body["rule_source"]["rule"] == rule
        assert body["event_source"]["stream"] == "event"
