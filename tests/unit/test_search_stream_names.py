"""The Search API's stream names, checked on the wire.

The Search API accepts ``event``, ``detection`` and ``audit`` in a request's
``stream`` field and rejects anything else with HTTP 400. ``detect`` is the
detection stream's name in other APIs (outputs, Spout, Replay), so the SDK and
CLI send it as ``detection``. These tests drive the real ``Search`` SDK class
and the real CLI against a local HTTP server and read the JSON bodies the
server received.
"""

from __future__ import annotations

import json
import time
import urllib.request

import pytest
from click.testing import CliRunner

from limacharlie import client as client_mod
from limacharlie.sdk.organization import Organization
from limacharlie.sdk.search import SEARCH_STREAMS, Search, search_stream

from test_client_response_compression import (  # noqa: E402  (sibling test module)
    OID,
    LocalServer,
    Reply,
    Seen,
    _make_jwt,
    make_client,
)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    from limacharlie.config import _reset_config_cache
    from limacharlie.jwt_cache import _reset_cache_disabled
    from limacharlie.paths import _reset_path_cache

    config_dir = tmp_path / "lc_config"
    config_dir.mkdir()
    monkeypatch.setenv("LC_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("LC_NO_JWT_CACHE", "1")
    for name in ("LC_CREDS_FILE", "LC_LEGACY_CONFIG", "LC_EPHEMERAL_CREDS", "LC_OID", "LC_API_KEY", "LC_UID"):
        monkeypatch.delenv(name, raising=False)
    _reset_path_cache()
    _reset_config_cache()
    _reset_cache_disabled()
    yield
    _reset_path_cache()
    _reset_config_cache()
    _reset_cache_disabled()


def _json(obj) -> Reply:
    return Reply(200, json.dumps(obj).encode(), [("Content-Type", "application/json")])


@pytest.fixture
def server(monkeypatch):
    """A search API that, like the real one, accepts only SEARCH_STREAMS."""
    with LocalServer() as srv:
        monkeypatch.setattr(client_mod, "urlopen", urllib.request.urlopen)
        monkeypatch.setattr(client_mod, "ROOT_URL", srv.url)
        monkeypatch.setattr(client_mod, "JWT_URL", srv.url + "/jwt")
        search_root = srv.url + "/search-api"

        def route(seen: Seen) -> Reply:
            if seen.path == "/jwt":
                return _json({"jwt": _make_jwt(time.time() + 3600)})
            if seen.path == f"/v1/orgs/{OID}/url":
                return _json({"url": {"search": search_root}})
            if seen.method == "POST" and seen.path.startswith("/search-api/v1/search"):
                stream = json.loads(seen.body).get("stream", "event")
                if stream not in SEARCH_STREAMS:
                    return Reply(400, json.dumps({"error": "invalid stream value"}).encode())
                if seen.path.endswith("/validate"):
                    return _json({"ok": True})
                return _json({"queryId": "q-1"})
            if seen.method == "GET" and seen.path.startswith("/search-api/v1/search/q-1"):
                return _json({"completed": True, "results": [{"type": "events", "rows": [{"ts": 1}]}]})
            if seen.method == "DELETE":
                return _json({})
            if seen.method == "POST":  # hive record write (saved queries)
                return _json({"success": True})
            return Reply(404, b'{"error": "no route"}')

        srv.route = route
        yield srv


def _sent_streams(server: LocalServer) -> list[str | None]:
    return [json.loads(s.body).get("stream") for s in server.seen
            if s.method == "POST" and s.path.startswith("/search-api/v1/search")]


class TestSearchStreamHelper:
    @pytest.mark.parametrize("value,expected", [
        ("detect", "detection"), ("DETECT", "detection"), (" detect ", "detection"),
        ("detection", "detection"), ("event", "event"), ("audit", "audit"),
        ("future-stream", "future-stream"), (None, None),
    ])
    def test_mapping(self, value, expected):
        assert search_stream(value) == expected


class TestSdk:
    @pytest.mark.parametrize("stream", ["detection", "detect"])
    def test_execute_sends_detection(self, server, stream):
        org = Organization(make_client())
        results = list(Search(org).execute("-1h | * | *", 1_700_000_000, 1_700_003_600, stream=stream))
        assert results and results[0]["rows"] == [{"ts": 1}]
        assert _sent_streams(server) == ["detection"]

    @pytest.mark.parametrize("stream", ["event", "audit"])
    def test_other_streams_pass_through(self, server, stream):
        org = Organization(make_client())
        list(Search(org).execute("-1h | * | *", 1_700_000_000, 1_700_003_600, stream=stream))
        assert _sent_streams(server) == [stream]

    def test_no_stream_sends_no_field(self, server):
        org = Organization(make_client())
        list(Search(org).execute("-1h | * | *", 1_700_000_000, 1_700_003_600))
        assert _sent_streams(server) == [None]

    @pytest.mark.parametrize("method", ["validate", "estimate"])
    def test_validate_and_estimate_send_detection(self, server, method):
        org = Organization(make_client())
        assert getattr(Search(org), method)("-1h | * | *", 1_700_000_000, 1_700_003_600, stream="detect") == {"ok": True}
        assert _sent_streams(server) == ["detection"]


class TestCli:
    def _run(self, monkeypatch, *args: str):
        from limacharlie.cli import cli

        monkeypatch.setenv("LC_OID", OID)
        monkeypatch.setenv("LC_API_KEY", "test-api-key")
        return CliRunner().invoke(cli, ["--output", "jsonl", *args], catch_exceptions=False)

    @pytest.mark.parametrize("stream", ["detection", "detect"])
    def test_search_run_sends_detection(self, server, monkeypatch, stream):
        result = self._run(monkeypatch, "search", "run", "--query", "-1h | * | *",
                           "--start", "1700000000", "--end", "1700003600", "--stream", stream)
        assert result.exit_code == 0, result.output
        assert _sent_streams(server) == ["detection"]

    def test_help_names_detection(self):
        from limacharlie.cli import cli

        for cmd in (["search", "run", "--help"], ["search", "estimate", "--help"], ["search", "saved-create", "--help"]):
            out = CliRunner().invoke(cli, cmd).output
            assert "event, detection, audit" in out, cmd
            assert "detect," not in out, cmd

    def test_saved_create_stores_detection(self, server, monkeypatch):
        result = self._run(monkeypatch, "search", "saved-create", "--name", "q", "--query", "-1h | * | *",
                           "--stream", "detect")
        assert result.exit_code == 0, result.output
        writes = [s for s in server.seen if s.method == "POST" and "/hive/query/" in s.path]
        assert len(writes) == 1
        from urllib.parse import parse_qs

        data = json.loads(parse_qs(writes[0].body.decode())["data"][0])
        assert data["stream"] == "detection"
