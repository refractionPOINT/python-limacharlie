"""Policy etags through SDK/CLI and the real HTTP client, without network dependencies."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen

import pytest
from click.testing import CliRunner


@pytest.fixture
def policy_api(monkeypatch):
    # Import after CLI lazy-loading tests have finished reloading command modules.
    import limacharlie.client as client_mod
    import limacharlie.commands.investigate as command_mod
    from limacharlie.sdk.investigation import Investigation

    state = SimpleNamespace(etag="", calls=[], native_conflict=False)

    class Handler(BaseHTTPRequestHandler):
        def handle_policy(self):
            url = urlparse(self.path)
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}")
            etag = self.headers.get("If-Match")
            force = parse_qs(url.query).get("force") == ["true"]
            state.calls.append((self.command, url.path, etag, force, body))
            status = 200
            if self.command != "GET":
                view = etag[1:-1] if etag and etag.startswith('"') and etag.endswith('"') else etag
                if state.native_conflict or not force and view != state.etag:
                    status = 409
                else:
                    state.etag = "native-next"
            answer = {"etag": state.etag, "config": {}, "routes": [], "truncated": False}
            if status == 409:
                answer = {"error": "policy changed: read etag or explicitly use force=true", "error_code": "policy_conflict"}
            raw = json.dumps(answer).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("ETag", '"' + state.etag + '"')
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        do_GET = do_PUT = do_POST = handle_policy

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


def write(inv, operation, **conditions):
    if operation == "autopilot":
        return inv.set_autopilot({"sources": {}, "daily_cap_micro_usd": 10000000}, **conditions)
    return inv.decide_route("a" * 64, "mailsec", operation, **conditions)


@pytest.mark.parametrize("operation", ["autopilot", "enable", "disable", "configure"])
@pytest.mark.parametrize("quoted", [False, True])
def test_sdk_actual_http_absence_stale_and_explicit_force(policy_api, operation, quoted):
    from limacharlie.sdk.investigation import InvestigationError

    inv = policy_api.inv
    read = inv.get_autopilot if operation == "autopilot" else inv.get_scoreboard
    etag = read()["etag"]
    assert etag == ""
    assert write(inv, operation, etag='"' + etag + '"' if quoted else etag)["etag"] == "native-next"
    assert policy_api.calls[-1][2] == ('""' if quoted else "")
    assert "etag" not in policy_api.calls[-1][4] and "force" not in policy_api.calls[-1][4]
    with pytest.raises(InvestigationError) as caught:
        write(inv, operation, etag="")
    assert caught.value.status_code == 409
    assert len(policy_api.calls) == 3  # No SDK refresh, force or retry after the stale write.
    assert write(inv, operation, force=True)["etag"] == "native-next"
    assert policy_api.calls[-1][2:4] == (None, True)
    policy_api.native_conflict = True
    with pytest.raises(InvestigationError) as caught:
        write(inv, operation, force=True)
    assert caught.value.status_code == 409
    assert len(policy_api.calls) == 5


@pytest.mark.parametrize("operation", ["autopilot", "enable", "disable", "configure"])
def test_cli_actual_http_preserves_quoted_empty_and_conflict(policy_api, operation):
    from limacharlie.cli import cli

    command = ["investigate", "autopilot", "configure", "--settings", "{}"] if operation == "autopilot" else [
        "investigate", "routes", operation, "a" * 64, "--product", "mailsec",
        *({"enable": ["--confirm"], "disable": [], "configure": ["--min-agreeing", "250"]}[operation]),
    ]
    runner = CliRunner(mix_stderr=False)
    result = runner.invoke(cli, ["--output", "json", *command])
    assert result.exit_code != 0 and not policy_api.calls
    result = runner.invoke(cli, ["--output", "json", *command, "--etag", '""'])
    assert result.exit_code == 0, result.stderr
    assert policy_api.calls[-1][2] == '""'
    result = runner.invoke(cli, ["--output", "json", *command, "--etag", '""'])
    assert result.exit_code != 0 and json.loads(result.stderr)["status"] == 409
    assert len(policy_api.calls) == 2
    result = runner.invoke(cli, ["--output", "json", *command, "--force"])
    assert result.exit_code == 0, result.stderr
    assert len(policy_api.calls) == 3 and policy_api.calls[-1][2:4] == (None, True)
