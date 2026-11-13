"""Automatic action SDK/CLI regressions through the real loopback HTTP client."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen

import pytest
from click.testing import CliRunner


@pytest.fixture
def automatic_api(monkeypatch):
    import limacharlie.client as client_mod
    import limacharlie.commands.investigate as command_mod
    from limacharlie.sdk.investigation import Investigation

    state = SimpleNamespace(calls=[], revealed=False, error=None, fail_active=True)
    metadata = {"id": "a1", "run_id": "r1", "product": "mailsec", "route_id": "a" * 64, "class": "close",
                "state": "confirmed", "created": "2026-11-13T00:00:00Z", "automatic": True,
                "held_for_spot_check": False, "targets_count": 1, "explanation": "automatic benign close"}

    class Handler(BaseHTTPRequestHandler):
        def handle_action(self):
            url = urlparse(self.path)
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}")
            query = parse_qs(url.query)
            state.calls.append((self.command, url.path, query, body))
            status = state.error or 200
            if status != 200:
                answer = {"error": "native guard", "error_code": "guarded"}
            elif url.path.endswith("/reveal") or url.path.endswith("/decision"):
                if self.command == "POST":
                    assert body == {}
                    state.revealed = True
                answer = {"visible": state.revealed, "visible_reason": "revealed" if state.revealed else "hidden",
                          "counted": not state.revealed, "run": {"run_id": "r1", "state": "completed"}}
            elif self.command == "POST":
                # This fixture models the engine response contract, not engine
                # permission/label behavior; those are covered by its owner.
                assert not set(body) & {"allowed_revert_classes", "actor", "identity", "jwt", "opinion_auditor"}
                if url.path.endswith("/a1/undo"):
                    rows = [{"id": "a1", **body}]
                elif "selector" in body:
                    rows = [{"id": "a1", "was_engine_wrong": body["was_engine_wrong"]}]
                else:
                    rows = body.get("items") or [{"id": value, "was_engine_wrong": body["was_engine_wrong"]} for value in body["ids"]]
                results = []
                for row in rows:
                    failed = row["id"] == "fail" and state.fail_active
                    noop = row["id"] == "noop"
                    results.append({"id": row["id"], "run_id": row.get("run_id", "r1"),
                                    "state": "failed" if failed else "confirmed" if noop else "reverted",
                                    "status": "failed" if failed else "skipped" if noop else "undone",
                                    "retryable": failed,
                                    "label_recorded": row["was_engine_wrong"] and not (failed or noop)})
                answer = {"results": results, "next_cursor": "opaque+next" if "selector" in body and not body.get("cursor") else "",
                          "truncated": "selector" in body and not body.get("cursor"), "selected": len(results), "as_of": "2026-11-13T12:00:00Z"}
            elif url.path.endswith("/actions"):
                answer = {"actions": [metadata], "next_cursor": "signed+next", "truncated": True, "total": 9007199254740993,
                          "totals": {"confirmed": 9007199254740993}, "as_of": "2026-11-13T12:00:00Z"}
            else:
                answer = {"action": metadata, "class": "close", "close_product": "mailsec"}
            raw = json.dumps(answer).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        do_GET = do_POST = handle_action

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    root = f"http://127.0.0.1:{server.server_port}"
    monkeypatch.setattr(client_mod, "ROOT_URL", root)

    def loopback_only(request, **kwargs):
        assert request.full_url.startswith(root + "/v1/")
        return urlopen(request, **kwargs)

    monkeypatch.setattr(client_mod, "urlopen", loopback_only)
    state.inv = Investigation(SimpleNamespace(oid="oid-1", client=client_mod.Client(oid="oid-1", jwt="test.jwt.signature", timeout=2)))
    monkeypatch.setattr(command_mod, "_get_investigation", lambda ctx: state.inv)
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_metadata_filters_and_counts_use_real_http(automatic_api):
    page = automatic_api.inv.list_automatic_actions(state=["active", "confirmed"], held_for_spot_check=False,
        from_="2026-11-01T00:00:00Z", to="2026-11-02T00:00:00Z", limit=200, cursor="opaque+cursor")
    assert page["total"] == 9007199254740993 and page["totals"]["confirmed"] == 9007199254740993
    assert automatic_api.calls[-1][2] == {"state": ["active,confirmed"], "held_for_spot_check": ["false"], "limit": ["200"],
        "cursor": ["opaque+cursor"], "from": ["2026-11-01T00:00:00Z"], "to": ["2026-11-02T00:00:00Z"]}
    detail = automatic_api.inv.get_automatic_action("a1", run_id="r1")
    assert detail["close_product"] == "mailsec" and "targets" not in detail["action"]


@pytest.mark.parametrize("mode", ["ids", "items", "selector", "single"])
def test_each_undo_mode_preserves_real_json_and_no_auto_paging(automatic_api, mode):
    inv = automatic_api.inv
    if mode == "ids":
        page = inv.undo_automatic_actions(["a1", "fail"], was_engine_wrong=True)
        assert page["results"][1]["status"] == "failed" and page["results"][1]["label_recorded"] is False
        assert page["results"][0]["status"] == "undone" and page["results"][0]["label_recorded"] is True
    elif mode == "items":
        page = inv.undo_automatic_actions(items=[{"id": "a1", "run_id": "r1", "was_engine_wrong": False}])
        assert automatic_api.calls[-1][3] == {"items": [{"id": "a1", "run_id": "r1", "was_engine_wrong": False}]}
    elif mode == "selector":
        selector = {"route_id": "a" * 64, "from": "2026-11-01T00:00:00Z"}
        page = inv.undo_automatic_actions(selector=selector, was_engine_wrong=False, limit=100)
        assert page["next_cursor"] == "opaque+next" and len(automatic_api.calls) == 1
        page = inv.undo_automatic_actions(selector=selector, was_engine_wrong=False, limit=100, cursor=page["next_cursor"])
        assert "to" not in automatic_api.calls[-1][3]["selector"]
        assert automatic_api.calls[-1][3]["cursor"] == "opaque+next"
    else:
        page = inv.undo_automatic_action("a1", run_id="r1", was_engine_wrong=False)
        assert automatic_api.calls[-1][1].endswith("/actions/a1/undo")
        assert automatic_api.calls[-1][3] == {"run_id": "r1", "was_engine_wrong": False}
    assert page["selected"] >= 1
    assert len(automatic_api.calls) == (2 if mode == "selector" else 1)


@pytest.mark.parametrize("status", [403, 409, 504])
def test_native_errors_are_not_retried_over_http(automatic_api, status):
    from limacharlie.sdk.investigation import InvestigationError
    automatic_api.error = status
    with pytest.raises(InvestigationError) as caught:
        automatic_api.inv.undo_automatic_actions(["a1"], was_engine_wrong=False)
    assert caught.value.status_code == status and len(automatic_api.calls) == 1


def test_cli_partial_result_and_explicit_reveal_over_http(automatic_api):
    from limacharlie.cli import cli
    runner = CliRunner(mix_stderr=False)
    result = runner.invoke(cli, ["--output", "json", "investigate", "autopilot", "actions", "undo", "a1", "fail", "--was-engine-wrong"])
    assert result.exit_code != 0 and json.loads(result.stdout)["results"][1]["label_recorded"] is False
    assert json.loads(result.stdout)["results"][0]["status"] == "undone" and json.loads(result.stdout)["results"][0]["label_recorded"] is True
    assert len(automatic_api.calls) == 1
    result = runner.invoke(cli, ["--output", "json", "investigate", "runs", "decision", "r1"])
    assert json.loads(result.stdout)["visible_reason"] == "hidden" and not automatic_api.revealed
    result = runner.invoke(cli, ["--output", "json", "investigate", "runs", "reveal", "r1"])
    assert result.exit_code == 0, result.stderr
    assert json.loads(result.stdout)["visible_reason"] == "revealed" and json.loads(result.stdout)["counted"] is False
    assert automatic_api.calls[-1][3] == {}


def test_failed_and_noop_answers_have_no_strong_label_until_actual_retry(automatic_api):
    page = automatic_api.inv.undo_automatic_actions(["fail", "noop"], was_engine_wrong=True)
    assert [(row["status"], row["retryable"], row["label_recorded"]) for row in page["results"]] == [
        ("failed", True, False), ("skipped", False, False),
    ]
    assert len(automatic_api.calls) == 1
    # An explicit retry now reports an actual owned undo from the native side.
    automatic_api.fail_active = False
    page = automatic_api.inv.undo_automatic_actions(["fail"], was_engine_wrong=True)
    assert page["results"][0]["state"] == "reverted" and page["results"][0]["status"] == "undone"
    assert page["results"][0]["label_recorded"] is True and len(automatic_api.calls) == 2
