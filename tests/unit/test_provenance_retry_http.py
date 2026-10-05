"""Exercise provenance retries through the real SDK HTTP transport."""

import hashlib
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.request import urlopen

import pytest

import limacharlie.client as client_mod
from limacharlie.errors import LimaCharlieError
from limacharlie.sdk.cloudsec import CloudSec
from limacharlie.sdk.organization import Organization


OID = "11111111-2222-3333-4444-555555555555"
RAW = b'{ "schema": "lc-build-provenance/v1", "signature": "test-only" }\n'


@pytest.fixture
def endpoint(monkeypatch):
    """A local endpoint can commit an upsert before losing its response."""
    statuses = []
    seen = []
    stored = set()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            seen.append((self.path, body, self.headers["Content-Type"],
                         self.headers["Authorization"], time.monotonic()))
            identity = hashlib.sha256(body).hexdigest()
            stored.add(identity)
            status = statuses.pop(0) if statuses else 200
            payload = ({"attestation_id": identity} if status == 200 else
                       {"error": "provenance_unavailable", "attempt": len(seen)})
            raw = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    root = f"http://127.0.0.1:{server.server_port}"
    monkeypatch.setattr(client_mod, "ROOT_URL", root)

    def loopback_only(request, **kwargs):
        assert request.full_url.startswith(root + "/v1/")
        return urlopen(request, **kwargs)

    monkeypatch.setattr(client_mod, "urlopen", loopback_only)
    client = client_mod.Client(oid=OID, jwt="test.jwt.signature", timeout=5)
    try:
        yield client, statuses, seen, stored
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


@pytest.mark.parametrize("document", [RAW, RAW.decode(), {"schema": "lc-build-provenance/v1"}])
def test_provenance_503_recovers_with_identical_upsert(endpoint, document):
    client, statuses, seen, stored = endpoint
    statuses.extend([503, 200])
    result = CloudSec(Organization(client)).push_code_provenance(document)
    expected = (json.dumps(document, separators=(",", ":")).encode()
                if isinstance(document, dict) else RAW)
    assert len(seen) == 2
    assert all(row[:4] == (f"/v1/cloudsec/{OID}/code/provenance", expected,
                           "application/json", "Bearer test.jwt.signature") for row in seen)
    assert seen[1][4] - seen[0][4] >= 1
    assert stored == {result["attestation_id"]}


def test_repeated_503_stops_after_one_retry_and_preserves_error(endpoint):
    client, statuses, seen, _ = endpoint
    statuses.extend([503, 503, 200])
    with pytest.raises(LimaCharlieError) as exc:
        CloudSec(Organization(client)).push_code_provenance(RAW)
    assert exc.value.status_code == 503
    assert exc.value.response_body == {"error": "provenance_unavailable", "attempt": 2}
    assert len(seen) == 2
    assert statuses == [200]


@pytest.mark.parametrize("path", [f"cloudsec/{OID}/code/provenance",
                                  f"cloudsec/{OID}/code/ingest"])
def test_shared_client_does_not_retry_503_without_opt_in(endpoint, path):
    client, statuses, seen, _ = endpoint
    statuses.extend([503, 200])
    with pytest.raises(LimaCharlieError) as exc:
        client.request("POST", path, raw_body=RAW, content_type="application/json")
    assert exc.value.status_code == 503
    assert len(seen) == 1


@pytest.mark.parametrize("status", [400, 403, 429, 502])
def test_provenance_errors_retry_only_rate_limits(endpoint, status, monkeypatch):
    client, statuses, seen, _ = endpoint
    statuses.extend([status, 200])
    if status == 429:
        waits = []
        monkeypatch.setattr("limacharlie.sdk.cloudsec.time.sleep", waits.append)
        result = CloudSec(Organization(client)).push_code_provenance(RAW)
        assert result["attestation_id"] == hashlib.sha256(RAW).hexdigest()
        assert len(seen) == 2 and seen[0][1] == seen[1][1] == RAW
        assert len(waits) == 1 and 5 <= waits[0] <= 7.5
    else:
        with pytest.raises(LimaCharlieError) as exc:
            CloudSec(Organization(client)).push_code_provenance(RAW)
        assert exc.value.status_code == status
        assert len(seen) == 1


def test_unavailable_retry_respects_total_attempt_budget(endpoint):
    client, statuses, seen, _ = endpoint
    statuses.extend([503, 200])
    with pytest.raises(LimaCharlieError):
        client.request("POST", "replay-safe", raw_body=RAW, max_retries=1,
                       retry_service_unavailable=True)
    assert len(seen) == 1


def test_503_retry_allowance_does_not_reset_after_504(endpoint):
    client, statuses, seen, _ = endpoint
    statuses.extend([503, 504, 503, 200])
    with pytest.raises(LimaCharlieError) as exc:
        client.request("POST", "replay-safe", raw_body=RAW, max_retries=5,
                       retry_service_unavailable=True)
    assert exc.value.status_code == 503
    assert len(seen) == 3
    assert statuses == [200]


def test_jwt_refresh_and_unavailable_retry_share_attempt_budget(endpoint):
    client, statuses, seen, _ = endpoint
    statuses.extend([401, 503, 200])
    refreshed = []

    def refresh(c):
        refreshed.append(True)
        c._jwt = "refreshed.jwt.signature"

    client._on_refresh_auth = refresh
    result = CloudSec(Organization(client)).push_code_provenance(RAW)
    assert len(seen) == 3
    assert len(refreshed) == 1
    assert [r[3] for r in seen] == ["Bearer test.jwt.signature",
                                   "Bearer refreshed.jwt.signature",
                                   "Bearer refreshed.jwt.signature"]
    assert all(r[1] == RAW for r in seen)
    assert result["attestation_id"] == hashlib.sha256(RAW).hexdigest()
