"""LC_API_URL / LC_JWT_URL point the SDK and CLI at another deployment."""

import importlib

import pytest

import limacharlie.client as client_mod


@pytest.fixture
def reload_client(monkeypatch):
    """Reload limacharlie.client under a patched environment, then restore it."""

    def _reload(**env):
        for name in ("LC_API_URL", "LC_JWT_URL"):
            monkeypatch.delenv(name, raising=False)
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        return importlib.reload(client_mod)

    yield _reload
    monkeypatch.delenv("LC_API_URL", raising=False)
    monkeypatch.delenv("LC_JWT_URL", raising=False)
    importlib.reload(client_mod)


def test_unset_keeps_the_public_roots(reload_client):
    mod = reload_client()
    assert mod.ROOT_URL == "https://api.limacharlie.io"
    assert mod.JWT_URL == "https://jwt.limacharlie.io"


def test_empty_keeps_the_public_roots(reload_client):
    mod = reload_client(LC_API_URL="  ", LC_JWT_URL="")
    assert mod.ROOT_URL == "https://api.limacharlie.io"
    assert mod.JWT_URL == "https://jwt.limacharlie.io"


def test_override_is_used_and_normalized(reload_client):
    mod = reload_client(LC_API_URL="http://127.0.0.1:9090/", LC_JWT_URL="http://127.0.0.1:8135")
    assert mod.ROOT_URL == "http://127.0.0.1:9090"
    assert mod.JWT_URL == "http://127.0.0.1:8135"


@pytest.mark.parametrize("value", ["127.0.0.1:9090", "ftp://example.com", "api.example.com"])
def test_a_malformed_override_is_refused(reload_client, value):
    with pytest.raises(ValueError, match="LC_API_URL"):
        reload_client(LC_API_URL=value)


def test_the_token_exchange_and_api_calls_go_to_the_override(reload_client, monkeypatch):
    """A client built under the overrides exchanges its key at LC_JWT_URL and
    calls the API under LC_API_URL/v1, against a real local HTTP server."""
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    seen = []

    class Handler(BaseHTTPRequestHandler):
        def _answer(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n:
                self.rfile.read(n)
            seen.append((self.server.name, self.command, self.path))
            body = {"jwt": "h.p.s"} if self.server.name == "jwt" else {"ok": True}
            raw = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        do_GET = do_POST = _answer

        def log_message(self, *args):
            pass

    servers = {}
    for name in ("api", "jwt"):
        srv = HTTPServer(("127.0.0.1", 0), Handler)
        srv.name = name
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        servers[name] = srv
    try:
        mod = reload_client(
            LC_API_URL=f"http://127.0.0.1:{servers['api'].server_port}",
            LC_JWT_URL=f"http://127.0.0.1:{servers['jwt'].server_port}/",
        )
        monkeypatch.setattr(mod, "resolve_credentials", lambda *a, **k: {
            "oid": "11111111-1111-1111-1111-111111111111", "uid": None,
            "api_key": "test-api-key-12345678", "oauth": None,
        })
        c = mod.Client(oid="11111111-1111-1111-1111-111111111111")
        c.request("GET", "orgs/11111111-1111-1111-1111-111111111111/url")
    finally:
        for srv in servers.values():
            srv.shutdown()
    assert ("jwt", "POST", "/") in seen, seen
    assert ("api", "GET", "/v1/orgs/11111111-1111-1111-1111-111111111111/url") in seen, seen
