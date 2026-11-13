"""Compressed HTTP responses, exercised end to end against a real local server.

Every test drives the real request code (Client, Search, the CLI) over a real
socket to an ``http.server`` running in a thread on 127.0.0.1. The server
records each request's headers and answers with a reply the test chose, so
the tests check both what the client asked for and how it read what came back:

- the ``Accept-Encoding`` header on every request path (API calls, the JWT
  endpoint, the search API, the CLI), and the opt-out;
- decoding by the response's actual ``Content-Encoding``: gzip, x-gzip, zstd,
  stacked codings, mixed case, identity, a server that ignores the request,
  empty bodies, chunked transfer, multi-member gzip, multi-frame zstd and
  large bodies;
- error responses whose bodies are compressed, and that the status code still
  drives retries, auth refresh and the raised exception;
- truncated and corrupt streams and unsupported codings raise
  ResponseDecodeError instead of returning a partial body, while transport
  failures (timeouts, short reads) keep their own exception types;
- decoding a large body does not hold more memory than reading it
  uncompressed.

Every test runs once per Zstandard decoder situation the SDK can find itself
in (the ``zstd_backend`` fixture): the standard library's ``compression.zstd``
(Python 3.14+), the optional ``zstandard`` package, and neither. Each is
produced by controlling what the SDK's compression module can import and
re-importing it; the SDK's own code is never replaced.
"""

from __future__ import annotations

import gzip
import importlib
import json
import socket
import sys
import threading
import time
import tracemalloc
import urllib.request
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

import pytest
from click.testing import CliRunner

from limacharlie import client as client_mod
from limacharlie import _http_compression as hc
from limacharlie.client import Client
from limacharlie.errors import (
    ApiError,
    AuthenticationError,
    NotFoundError,
    RateLimitError,
    ResponseDecodeError,
    SearchError,
)
from limacharlie.sdk.organization import Organization
from limacharlie.sdk.search import Search

# Test-side zstd compressors, for the server's half of the exchange. Bound at
# import, before any test hides either module from the SDK.
try:
    from compression import zstd as _stdlib_zstd  # Python 3.14+
except ImportError:
    _stdlib_zstd = None
try:
    import zstandard as _zstandard
except ImportError:
    _zstandard = None

CAN_COMPRESS_ZSTD = _stdlib_zstd is not None or _zstandard is not None


def zstd_compress(data: bytes, checksum: bool = True) -> bytes:
    """One zstd frame, with a content checksum as the API server writes them."""
    if _stdlib_zstd is not None:
        opts = {_stdlib_zstd.CompressionParameter.checksum_flag: int(checksum)}
        return _stdlib_zstd.compress(data, options=opts)
    return _zstandard.ZstdCompressor(write_checksum=checksum).compress(data)


# Which modules each decoder situation hides from the SDK.
_BACKEND_BLOCKS = {
    "compression.zstd": ("zstandard",),
    "zstandard": ("compression", "compression.zstd"),
    "none": ("zstandard", "compression", "compression.zstd"),
}


def _importable(name: str) -> bool:
    try:
        importlib.import_module(name)
    except ImportError:
        return False
    return True


@pytest.fixture(autouse=True, params=list(_BACKEND_BLOCKS))
def zstd_backend(request):
    """Re-import the SDK's compression module with only one zstd decoder visible.

    A module is hidden the way Python itself reports a missing one: a None
    entry in sys.modules makes importing it raise ImportError. The module is
    re-imported afterwards with nothing hidden.
    """
    backend = request.param
    if backend != "none" and not _importable(backend):
        pytest.skip(f"{backend} is not installed")
    with pytest.MonkeyPatch.context() as mp:
        for name in _BACKEND_BLOCKS[backend]:
            mp.setitem(sys.modules, name, None)
        importlib.reload(hc)
        assert hc.ZSTD_BACKEND == (None if backend == "none" else backend)
        yield backend
    importlib.reload(hc)


def zstd_decodable() -> bool:
    return hc.ZSTD_BACKEND is not None

# What urllib sends when the caller sets no Accept-Encoding: http.client adds
# "Accept-Encoding: identity" to every request on its own.
URLLIB_DEFAULT_ACCEPT_ENCODING = "identity"
OID = "00000000-0000-4000-8000-000000000001"


def _make_jwt(exp: float) -> str:
    import base64

    def b64(obj: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()

    return f"{b64({'alg': 'HS256'})}.{b64({'exp': exp, 'oid': OID})}.c2ln"


# ---------------------------------------------------------------------------
# Local server
# ---------------------------------------------------------------------------


@dataclass
class Reply:
    """What the server sends back for one request."""

    status: int = 200
    body: bytes = b""
    headers: list[tuple[str, str]] = field(default_factory=list)
    # Send the body in these pieces with Transfer-Encoding: chunked.
    chunks: list[bytes] | None = None
    # Advertise this Content-Length instead of len(body) (to cut a body short).
    content_length: int | None = None
    # Sleep this long after sending the headers and the first body byte.
    stall: float = 0.0
    # After the chunks, announce a chunk of 2 * len(cut_chunk) bytes, send
    # cut_chunk and close: a chunked body cut off mid-chunk.
    cut_chunk: bytes | None = None


@dataclass
class Seen:
    """One request as the server received it."""

    method: str
    path: str
    headers: dict[str, str]
    body: bytes

    @property
    def accept_encoding(self) -> str | None:
        return self.headers.get("accept-encoding")


def accepted_codings(seen: Seen) -> list[str]:
    value = seen.accept_encoding or ""
    return [p.split(";")[0].strip().lower() for p in value.split(",") if p.strip()]


def negotiate(seen: Seen, body: bytes, status: int = 200,
              headers: list[tuple[str, str]] | None = None) -> Reply:
    """Answer like the API server: zstd when offered, else gzip, else identity."""
    hdrs = list(headers or [("Content-Type", "application/json")])
    offered = accepted_codings(seen)
    if "zstd" in offered:
        return Reply(status, zstd_compress(body), hdrs + [("Content-Encoding", "zstd")])
    if "gzip" in offered:
        return Reply(status, gzip.compress(body), hdrs + [("Content-Encoding", "gzip")])
    return Reply(status, body, hdrs)


class LocalServer:
    """An HTTP/1.1 server on 127.0.0.1 that records requests and replies via ``route``."""

    def __init__(self) -> None:
        self.seen: list[Seen] = []
        self.route: Callable[[Seen], Reply] = lambda seen: Reply(404, b"no route")
        self.wire_bytes = 0
        server = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args: object) -> None:  # keep test output clean
                pass

            def _handle(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                seen = Seen(self.command, self.path,
                            {k.lower(): v for k, v in self.headers.items()}, body)
                server.seen.append(seen)
                reply = server.route(seen)
                self.send_response(reply.status)
                for name, value in reply.headers:
                    self.send_header(name, value)
                self.send_header("Connection", "close")
                if reply.chunks is not None:
                    self.send_header("Transfer-Encoding", "chunked")
                    self.end_headers()
                    for chunk in reply.chunks:
                        self.wfile.write(b"%x\r\n%s\r\n" % (len(chunk), chunk))
                        server.wire_bytes += len(chunk)
                    if reply.cut_chunk is not None:
                        self.wfile.write(b"%x\r\n%s" % (2 * len(reply.cut_chunk), reply.cut_chunk))
                        self.close_connection = True
                        return
                    self.wfile.write(b"0\r\n\r\n")
                    return
                length = reply.content_length if reply.content_length is not None else len(reply.body)
                self.send_header("Content-Length", str(length))
                self.end_headers()
                if reply.stall:
                    self.wfile.write(reply.body[:1])
                    self.wfile.flush()
                    time.sleep(reply.stall)
                    return
                self.wfile.write(reply.body)
                server.wire_bytes += len(reply.body)
                self.close_connection = True

            do_GET = do_POST = do_DELETE = do_PUT = _handle

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._httpd.daemon_threads = True
        self.url = f"http://127.0.0.1:{self._httpd.server_address[1]}"
        self._thread = threading.Thread(target=self._httpd.serve_forever, kwargs={"poll_interval": 0.01},
                                        daemon=True)

    def __enter__(self) -> "LocalServer":
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    """Isolated config and JWT cache, and no compression env override."""
    from limacharlie.config import _reset_config_cache
    from limacharlie.jwt_cache import _reset_cache_disabled
    from limacharlie.paths import _reset_path_cache

    config_dir = tmp_path / "lc_config"
    config_dir.mkdir()
    monkeypatch.setenv("LC_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("LC_NO_JWT_CACHE", "1")
    for name in ("LC_CREDS_FILE", "LC_LEGACY_CONFIG", "LC_EPHEMERAL_CREDS",
                 "LC_NO_RESPONSE_COMPRESSION", "LC_OID", "LC_API_KEY", "LC_UID"):
        monkeypatch.delenv(name, raising=False)
    _reset_path_cache()
    _reset_config_cache()
    _reset_cache_disabled()
    yield
    _reset_path_cache()
    _reset_config_cache()
    _reset_cache_disabled()


@pytest.fixture
def server(monkeypatch):
    """A running LocalServer that the SDK's API and JWT roots point at.

    The unit-test conftest blocks ``limacharlie.client.urlopen`` so no test
    reaches the network by accident; this restores the real one, which is
    safe because every root now points at 127.0.0.1.
    """
    with LocalServer() as srv:
        monkeypatch.setattr(client_mod, "urlopen", urllib.request.urlopen)
        monkeypatch.setattr(client_mod, "ROOT_URL", srv.url)
        monkeypatch.setattr(client_mod, "JWT_URL", srv.url + "/jwt")
        yield srv


def make_client(**kwargs) -> Client:
    kwargs.setdefault("jwt", _make_jwt(time.time() + 3600))
    return Client(oid=OID, api_key="test-api-key", **kwargs)


def json_reply(obj: object, status: int = 200) -> Callable[[Seen], Reply]:
    body = json.dumps(obj).encode()
    return lambda seen: negotiate(seen, body, status)


def fixed(body: bytes, *, status: int = 200, encoding: str | list[str] | None = None,
          **kwargs) -> Callable[[Seen], Reply]:
    """Always send *body* as given, labelled with *encoding*, whatever was asked."""
    headers = [("Content-Type", "application/json")]
    for value in ([encoding] if isinstance(encoding, str) else encoding or []):
        headers.append(("Content-Encoding", value))
    return lambda seen: Reply(status, body, headers, **kwargs)


# A realistic search-result page: rows shaped like endpoint telemetry with
# repeated hosts, paths and command lines plus per-row random identifiers.
def search_rows(n: int, seed: int = 7) -> list[dict]:
    import random

    rnd = random.Random(seed)
    paths = [f"C:\\Program Files\\Vendor{i}\\bin\\tool{i % 13}.exe" for i in range(80)]
    rows = []
    for i in range(n):
        p = rnd.choice(paths)
        rows.append({
            "data": {
                "event": {
                    "FILE_PATH": p,
                    "COMMAND_LINE": f"\"{p}\" --mode {i % 5} --config C:\\ProgramData\\app\\{i % 31}.json",
                    "HASH": "%064x" % rnd.getrandbits(256),
                    "PROCESS_ID": rnd.randrange(100, 65000),
                    "PARENT": {"FILE_PATH": rnd.choice(paths), "PROCESS_ID": rnd.randrange(100, 65000)},
                },
                "routing": {
                    "oid": OID,
                    "sid": "%032x" % rnd.getrandbits(128),
                    "hostname": f"host-{rnd.randrange(200):04d}.corp.example",
                    "event_type": rnd.choice(["NEW_PROCESS", "DNS_REQUEST", "NETWORK_CONNECTIONS"]),
                    "event_time": 1_700_000_000_000 + i,
                    "event_id": "%032x" % rnd.getrandbits(128),
                },
            },
            "ts": 1_700_000_000_000 + i,
        })
    return rows


# ---------------------------------------------------------------------------
# What the client asks for
# ---------------------------------------------------------------------------


class TestAcceptEncodingRequestHeader:
    def test_default_value_names_only_codings_the_client_decodes(self):
        assert hc.ACCEPT_ENCODING == ("zstd, gzip" if zstd_decodable() else "gzip")

    def test_api_request_sends_accept_encoding(self, server):
        server.route = json_reply({"ok": True})
        assert make_client().request("GET", "orgs/x/info") == {"ok": True}
        assert server.seen[0].accept_encoding == hc.ACCEPT_ENCODING
        assert server.seen[0].headers["user-agent"].startswith("lc-cli/")

    @pytest.mark.parametrize("verb", ["GET", "POST", "PUT", "DELETE"])
    def test_every_verb_sends_accept_encoding(self, server, verb):
        server.route = json_reply({"verb": verb})
        assert make_client().request(verb, "thing", params={"a": "1"}) == {"verb": verb}
        assert server.seen[0].method == verb
        assert server.seen[0].accept_encoding == hc.ACCEPT_ENCODING

    def test_raw_request_sends_and_decodes(self, server):
        server.route = json_reply({"raw": True}, status=409)
        code, data = make_client().raw_request("POST", "thing")
        assert (code, data) == (409, {"raw": True})
        assert server.seen[0].accept_encoding == hc.ACCEPT_ENCODING

    def test_jwt_endpoint_sends_and_decodes(self, server):
        token = _make_jwt(time.time() + 3600)

        def route(seen: Seen) -> Reply:
            if seen.path == "/jwt":
                return negotiate(seen, json.dumps({"jwt": token}).encode())
            return negotiate(seen, b'{"ok": true}')

        server.route = route
        client = make_client(jwt=None)
        assert client.request("GET", "orgs/x/info") == {"ok": True}
        assert client._jwt == token
        assert [s.path for s in server.seen] == ["/jwt", "/v1/orgs/x/info"]
        assert all(s.accept_encoding == hc.ACCEPT_ENCODING for s in server.seen)
        assert server.seen[1].headers["authorization"] == f"Bearer {token}"

    def test_caller_supplied_accept_encoding_is_kept(self, server):
        server.route = json_reply({"ok": True})
        make_client().request("GET", "x", extra_headers={"Accept-Encoding": "identity"})
        assert server.seen[0].accept_encoding == "identity"


class TestOptOut:
    def test_constructor_false_sends_no_accept_encoding(self, server):
        server.route = json_reply({"ok": True})
        assert make_client(compressed_responses=False).request("GET", "x") == {"ok": True}
        assert server.seen[0].accept_encoding == URLLIB_DEFAULT_ACCEPT_ENCODING

    @pytest.mark.parametrize("value", ["1", "true", "YES", "on", "anything"])
    def test_env_var_turns_it_off(self, server, monkeypatch, value):
        monkeypatch.setenv("LC_NO_RESPONSE_COMPRESSION", value)
        server.route = json_reply({"ok": True})
        make_client().request("GET", "x")
        assert server.seen[0].accept_encoding == URLLIB_DEFAULT_ACCEPT_ENCODING

    @pytest.mark.parametrize("value", ["", "0", "false", "No", " off "])
    def test_env_var_falsy_values_keep_it_on(self, server, monkeypatch, value):
        monkeypatch.setenv("LC_NO_RESPONSE_COMPRESSION", value)
        server.route = json_reply({"ok": True})
        make_client().request("GET", "x")
        assert server.seen[0].accept_encoding == hc.ACCEPT_ENCODING

    def test_constructor_true_overrides_env(self, server, monkeypatch):
        monkeypatch.setenv("LC_NO_RESPONSE_COMPRESSION", "1")
        server.route = json_reply({"ok": True})
        make_client(compressed_responses=True).request("GET", "x")
        assert server.seen[0].accept_encoding == hc.ACCEPT_ENCODING

    def test_opted_out_client_still_decodes_a_compressed_reply(self, server):
        server.route = fixed(gzip.compress(b'{"forced": 1}'), encoding="gzip")
        assert make_client(compressed_responses=False).request("GET", "x") == {"forced": 1}
        assert server.seen[0].accept_encoding == URLLIB_DEFAULT_ACCEPT_ENCODING


# ---------------------------------------------------------------------------
# How the client reads what comes back
# ---------------------------------------------------------------------------


PAYLOAD = {"rows": [{"i": i, "s": "value-%d" % i} for i in range(500)]}
PAYLOAD_BYTES = json.dumps(PAYLOAD).encode()


class TestDecoding:
    def test_gzip_reply_is_decoded_and_smaller_on_the_wire(self, server):
        server.route = fixed(gzip.compress(PAYLOAD_BYTES), encoding="gzip")
        assert make_client().request("GET", "x") == PAYLOAD
        assert server.wire_bytes < len(PAYLOAD_BYTES) / 4

    def test_server_ignoring_accept_encoding_is_read_as_identity(self, server):
        server.route = fixed(PAYLOAD_BYTES)
        assert make_client().request("GET", "x") == PAYLOAD
        assert server.seen[0].accept_encoding == hc.ACCEPT_ENCODING

    @pytest.mark.parametrize("label", ["GZIP", "Gzip", " gzip ", "x-gzip", "X-GZip"])
    def test_coding_names_are_case_and_space_insensitive(self, server, label):
        server.route = fixed(gzip.compress(PAYLOAD_BYTES), encoding=label)
        assert make_client().request("GET", "x") == PAYLOAD

    @pytest.mark.parametrize("label", ["identity", "IDENTITY", "", " , identity"])
    def test_identity_labels_pass_through(self, server, label):
        server.route = fixed(PAYLOAD_BYTES, encoding=label)
        assert make_client().request("GET", "x") == PAYLOAD

    def test_stacked_codings_in_one_header_are_removed_in_reverse(self, server):
        twice = gzip.compress(gzip.compress(PAYLOAD_BYTES))
        server.route = fixed(twice, encoding="gzip, x-gzip")
        assert make_client().request("GET", "x") == PAYLOAD

    def test_stacked_codings_across_header_lines(self, server):
        twice = gzip.compress(gzip.compress(PAYLOAD_BYTES))
        server.route = fixed(twice, encoding=["gzip", "identity", "gzip"])
        assert make_client().request("GET", "x") == PAYLOAD

    def test_multi_member_gzip(self, server):
        half = len(PAYLOAD_BYTES) // 2
        body = gzip.compress(PAYLOAD_BYTES[:half]) + gzip.compress(PAYLOAD_BYTES[half:])
        server.route = fixed(body, encoding="gzip")
        assert make_client().request("GET", "x") == PAYLOAD

    def test_empty_body_labelled_gzip(self, server):
        server.route = fixed(b"", encoding="gzip")
        assert make_client().request("DELETE", "x") == {}

    def test_gzip_of_empty_body(self, server):
        server.route = fixed(gzip.compress(b""), encoding="gzip")
        assert make_client().request("DELETE", "x") == {}

    def test_chunked_transfer(self, server):
        compressed = gzip.compress(PAYLOAD_BYTES)
        pieces = [compressed[i:i + 7] for i in range(0, len(compressed), 7)]
        server.route = lambda seen: Reply(200, b"", [("Content-Encoding", "gzip")], chunks=pieces)
        assert make_client().request("GET", "x") == PAYLOAD

    def test_raw_response_text_is_decoded(self, server):
        csv = "".join(f"{i},name-{i},ok\n" for i in range(2000)).encode()
        server.route = fixed(gzip.compress(csv), encoding="gzip")
        assert make_client().request("GET", "export", raw_response=True) == csv.decode()

    def test_unicode_body(self, server):
        body = json.dumps({"s": "\u00e9\u4e2d\U0001f600" * 200}, ensure_ascii=False).encode()
        server.route = fixed(gzip.compress(body), encoding="gzip")
        assert make_client().request("GET", "x") == json.loads(body)

    def test_debug_output_reports_wire_and_decoded_size(self, server):
        lines: list[str] = []
        server.route = fixed(gzip.compress(PAYLOAD_BYTES), encoding="gzip")
        make_client(print_debug_fn=lines.append).request("GET", "x")
        wire = len(gzip.compress(PAYLOAD_BYTES))
        assert any(f"{wire} bytes gzip on the wire, {len(PAYLOAD_BYTES)} bytes decoded" in ln
                   for ln in lines)
        request_dump = next(ln for ln in lines if "--- request GET" in ln)
        assert f"Accept-encoding: {hc.ACCEPT_ENCODING}" in request_dump


# ---------------------------------------------------------------------------
# zstd
# ---------------------------------------------------------------------------


SKIPPABLE_FRAME = b"\x50\x2a\x4d\x18" + (5).to_bytes(4, "little") + b"jttr!"


def _zstd_frames(n: int = 3) -> bytes:
    step = len(PAYLOAD_BYTES) // n + 1
    return b"".join(zstd_compress(PAYLOAD_BYTES[i:i + step]) for i in range(0, len(PAYLOAD_BYTES), step))


def _flip(data: bytes, index: int) -> bytes:
    out = bytearray(data)
    out[index] ^= 0xFF
    return bytes(out)


@pytest.mark.skipif(not CAN_COMPRESS_ZSTD, reason="no zstd compressor for the test server")
class TestZstd:
    @pytest.fixture(autouse=True)
    def _needs_decoder(self):
        if not zstd_decodable():
            pytest.skip("no zstd decoder in this situation")

    def test_zstd_is_offered_first_and_chosen(self, server):
        server.route = json_reply(PAYLOAD)
        assert make_client().request("GET", "x") == PAYLOAD
        assert accepted_codings(server.seen[0]) == ["zstd", "gzip"]

    def test_single_frame(self, server):
        server.route = fixed(zstd_compress(PAYLOAD_BYTES), encoding="zstd")
        assert make_client().request("GET", "x") == PAYLOAD

    def test_frame_without_checksum(self, server):
        server.route = fixed(zstd_compress(PAYLOAD_BYTES, checksum=False), encoding="zstd")
        assert make_client().request("GET", "x") == PAYLOAD

    @pytest.mark.parametrize("trailer", [b"", SKIPPABLE_FRAME], ids=["frames", "frames-then-skippable"])
    def test_multi_frame_stream(self, server, trailer):
        server.route = fixed(_zstd_frames() + trailer, encoding="zstd")
        assert make_client().request("GET", "x") == PAYLOAD

    def test_skippable_frame_first(self, server):
        server.route = fixed(SKIPPABLE_FRAME + zstd_compress(PAYLOAD_BYTES), encoding="zstd")
        assert make_client().request("GET", "x") == PAYLOAD

    def test_multi_frame_in_tiny_chunks(self, server):
        body = _zstd_frames(5)
        pieces = [body[i:i + 3] for i in range(0, len(body), 3)]
        server.route = lambda seen: Reply(200, b"", [("Content-Encoding", "ZSTD")], chunks=pieces)
        assert make_client().request("GET", "x") == PAYLOAD

    def test_empty_body_labelled_zstd(self, server):
        server.route = fixed(b"", encoding="zstd")
        assert make_client().request("DELETE", "x") == {}

    def test_zstd_of_empty_body(self, server):
        server.route = fixed(zstd_compress(b""), encoding="zstd")
        assert make_client().request("DELETE", "x") == {}

    def test_zstd_over_gzip(self, server):
        server.route = fixed(zstd_compress(gzip.compress(PAYLOAD_BYTES)), encoding="gzip, zstd")
        assert make_client().request("GET", "x") == PAYLOAD

    def test_compressed_error_body(self, server):
        server.route = fixed(zstd_compress(b'{"error": "bad zstd query"}'), status=400, encoding="zstd")
        with pytest.raises(ApiError) as exc:
            make_client().request("GET", "x")
        assert "bad zstd query" in str(exc.value)

    @pytest.mark.parametrize("make_body", [
        pytest.param(lambda: zstd_compress(PAYLOAD_BYTES)[:-60], id="truncated"),
        pytest.param(lambda: zstd_compress(PAYLOAD_BYTES)[:-1], id="missing-checksum-byte"),
        pytest.param(lambda: zstd_compress(PAYLOAD_BYTES)[:6], id="header-only"),
        pytest.param(lambda: _zstd_frames()[:-20], id="truncated-last-frame"),
        pytest.param(lambda: _zstd_frames() + SKIPPABLE_FRAME[:6], id="truncated-skippable-frame"),
        pytest.param(lambda: _flip(zstd_compress(PAYLOAD_BYTES), -1), id="bad-checksum"),
        pytest.param(lambda: _flip(zstd_compress(PAYLOAD_BYTES), 40), id="corrupt-block"),
        pytest.param(lambda: zstd_compress(PAYLOAD_BYTES) + b"junk", id="trailing-garbage"),
        pytest.param(lambda: b"not zstd at all", id="not-zstd"),
    ])
    def test_broken_stream_raises(self, server, make_body):
        server.route = fixed(make_body(), encoding="zstd")
        with pytest.raises(ResponseDecodeError) as exc:
            make_client().request("GET", "x")
        assert exc.value.encoding == "zstd"

    def test_connection_closed_mid_frame_is_reported_as_truncated(self, server):
        body = zstd_compress(PAYLOAD_BYTES)[:-30]
        server.route = fixed(body, encoding="zstd", content_length=len(body) * 2)
        with pytest.raises(ResponseDecodeError) as exc:
            make_client().request("GET", "x")
        assert "ended before" in exc.value.raw_message


class TestWithoutZstdDecoder:
    @pytest.fixture(autouse=True)
    def _needs_no_decoder(self):
        if zstd_decodable():
            pytest.skip("a zstd decoder is available in this situation")

    def test_only_gzip_is_offered_and_chosen(self, server):
        server.route = json_reply(PAYLOAD)
        assert make_client().request("GET", "x") == PAYLOAD
        assert server.seen[0].accept_encoding == "gzip"
        assert server.wire_bytes < len(PAYLOAD_BYTES) / 4

    def test_zstd_reply_is_an_error(self, server):
        server.route = fixed(b"\x28\xb5\x2f\xfd" + b"\x00" * 20, encoding="zstd")
        with pytest.raises(ResponseDecodeError) as exc:
            make_client().request("GET", "x")
        assert exc.value.encoding == "zstd"
        assert "decodes only gzip, x-gzip" in exc.value.raw_message


# ---------------------------------------------------------------------------
# Broken streams and unsupported codings
# ---------------------------------------------------------------------------


def _truncated_gzip() -> bytes:
    full = gzip.compress(PAYLOAD_BYTES)
    return full[: len(full) // 2]


def _bad_crc_gzip() -> bytes:
    full = bytearray(gzip.compress(PAYLOAD_BYTES))
    full[-8] ^= 0xFF  # first byte of the CRC-32 trailer
    return bytes(full)


def _bad_length_gzip() -> bytes:
    full = bytearray(gzip.compress(PAYLOAD_BYTES))
    full[-1] ^= 0x01  # ISIZE trailer
    return bytes(full)


class TestBrokenStreams:
    @pytest.mark.parametrize("body,needle", [
        pytest.param(_truncated_gzip(), "ended before", id="truncated"),
        pytest.param(gzip.compress(PAYLOAD_BYTES)[:-4], "ended before", id="missing-trailer"),
        pytest.param(_bad_crc_gzip(), "crc", id="bad-crc"),
        pytest.param(_bad_length_gzip(), "length", id="bad-length"),
        pytest.param(gzip.compress(PAYLOAD_BYTES) + b"trailing junk", "not a gzipped file", id="trailing-garbage"),
        pytest.param(b"this is not gzip at all", "not a gzipped file", id="not-gzip"),
        pytest.param(b"\x1f\x8b\x08\x00" + b"\x00" * 6 + b"\xff" * 64, "", id="corrupt-deflate"),
    ])
    def test_success_body_that_fails_to_decode_raises(self, server, body, needle):
        server.route = fixed(body, encoding="gzip")
        with pytest.raises(ResponseDecodeError) as exc:
            make_client().request("GET", "x")
        assert exc.value.encoding == "gzip"
        assert needle in exc.value.raw_message.lower()
        assert isinstance(exc.value, ApiError)
        assert "LC_NO_RESPONSE_COMPRESSION" in exc.value.suggestion

    def test_truncated_chunked_gzip_raises(self, server):
        compressed = _truncated_gzip()
        server.route = lambda seen: Reply(200, b"", [("Content-Encoding", "gzip")],
                                          chunks=[compressed[:100], compressed[100:]])
        with pytest.raises(ResponseDecodeError):
            make_client().request("GET", "x")

    @pytest.mark.parametrize("label", ["br", "deflate", "compress", "gzip, br", "snappy"])
    def test_unsupported_coding_raises_naming_it(self, server, label):
        server.route = fixed(b"\x00\x01\x02", encoding=label)
        with pytest.raises(ResponseDecodeError) as exc:
            make_client().request("GET", "x")
        assert exc.value.encoding == label
        assert repr(label) in exc.value.raw_message

    def test_decode_error_is_not_retried(self, server):
        server.route = fixed(_truncated_gzip(), encoding="gzip")
        with pytest.raises(ResponseDecodeError):
            make_client().request("GET", "x", max_retries=3)
        assert len(server.seen) == 1

    def test_connection_closed_mid_stream_is_reported_as_truncated(self, server):
        """The server promises more bytes than it sends, then closes.

        urllib's sized reads return a short body silently on an early close;
        the gzip end-of-stream marker is what catches it.
        """
        body = _truncated_gzip()
        server.route = fixed(body, encoding="gzip", content_length=len(body) * 2)
        with pytest.raises(ResponseDecodeError) as exc:
            make_client().request("GET", "x")
        assert "ended before" in exc.value.raw_message

    def test_connection_closed_mid_chunk_keeps_its_transport_error(self, server):
        import http.client

        compressed = gzip.compress(PAYLOAD_BYTES)

        def route(seen: Seen) -> Reply:
            # A chunk header announcing more bytes than follow, then close.
            return Reply(200, b"", [("Content-Encoding", "gzip")], chunks=[compressed[:50]],
                         cut_chunk=compressed[50:])

        server.route = route
        with pytest.raises(http.client.IncompleteRead):
            make_client().request("GET", "x")

    def test_timeout_mid_body_keeps_its_transport_error(self, server):
        server.route = fixed(gzip.compress(PAYLOAD_BYTES), encoding="gzip", stall=3)
        with pytest.raises((TimeoutError, socket.timeout)):
            make_client().request("GET", "x", timeout=1)


# ---------------------------------------------------------------------------
# Error responses with compressed bodies
# ---------------------------------------------------------------------------


class TestCompressedErrorResponses:
    def test_404_message_comes_from_decoded_body(self, server):
        server.route = json_reply({"error": "sensor not found here"}, status=404)
        with pytest.raises(NotFoundError) as exc:
            make_client().request("GET", "sensors/x")
        assert "sensor not found here" in str(exc.value)

    def test_400_body_is_parsed_json(self, server):
        server.route = json_reply({"error": "bad query", "code": "LCQL_SYNTAX"}, status=400)
        with pytest.raises(ApiError) as exc:
            make_client().request("POST", "x")
        assert "bad query" in str(exc.value)
        assert exc.value.status_code == 400

    def test_429_with_retry_after_and_compressed_body(self, server):
        body = gzip.compress(b'{"error": "quota exceeded"}')
        server.route = lambda seen: Reply(429, body, [("Content-Encoding", "gzip"), ("Retry-After", "17")])
        with pytest.raises(RateLimitError) as exc:
            make_client().request("GET", "x")
        assert exc.value.retry_after == 17
        assert "quota exceeded" in str(exc.value)

    def test_401_compressed_body_still_refreshes_the_jwt(self, server):
        token = _make_jwt(time.time() + 7200)
        calls = {"api": 0}

        def route(seen: Seen) -> Reply:
            if seen.path == "/jwt":
                return negotiate(seen, json.dumps({"jwt": token}).encode())
            calls["api"] += 1
            if calls["api"] == 1:
                return negotiate(seen, b'{"error": "token expired"}', status=401)
            return negotiate(seen, b'{"after": "refresh"}')

        server.route = route
        assert make_client().request("GET", "x") == {"after": "refresh"}
        assert [s.path for s in server.seen] == ["/v1/x", "/jwt", "/v1/x"]
        assert server.seen[2].headers["authorization"] == f"Bearer {token}"

    def test_504_compressed_body_is_retried(self, server, monkeypatch):
        monkeypatch.setattr(client_mod.time, "sleep", lambda s: None)
        replies = iter([(504, b'{"error": "timeout"}'), (200, b'{"ok": true}')])

        def route(seen: Seen) -> Reply:
            status, body = next(replies)
            return negotiate(seen, body, status)

        server.route = route
        assert make_client().request("GET", "x") == {"ok": True}
        assert len(server.seen) == 2

    def test_undecodable_error_body_keeps_the_status(self, server):
        server.route = fixed(_truncated_gzip(), status=500, encoding="gzip")
        with pytest.raises(ApiError) as exc:
            make_client().request("GET", "x")
        assert not isinstance(exc.value, ResponseDecodeError)
        assert exc.value.status_code == 500
        assert "undecodable gzip error response body" in str(exc.value)

    def test_jwt_endpoint_compressed_error(self, server):
        server.route = lambda seen: negotiate(seen, b'{"error": "unknown api key"}', status=401)
        with pytest.raises(AuthenticationError) as exc:
            make_client(jwt=None).request("GET", "x")
        assert "unknown api key" in str(exc.value)


# ---------------------------------------------------------------------------
# Large bodies
# ---------------------------------------------------------------------------


class TestLargeBodies:
    def test_large_body_round_trips(self, server):
        body = json.dumps({"rows": search_rows(20_000)}).encode()  # ~10 MB
        server.route = lambda seen: negotiate(seen, body)
        assert make_client().request("GET", "x", raw_response=True) == body.decode()
        assert server.wire_bytes < len(body) / 2

    def test_decoding_holds_no_more_memory_than_an_uncompressed_read(self, server):
        """Peak traced memory decoding a large body is bounded by the identity read.

        Both reads end holding the body as bytes and as text, so they share
        the same floor; decoding may add only its stream state and one chunk.
        """
        body = json.dumps({"rows": search_rows(40_000)}).encode()  # ~25 MB
        # tracemalloc traces every thread, the server's included, so both
        # replies are built before tracing starts: inside the traced window
        # the server thread only sends bytes that already exist.
        compressed_reply = negotiate(Seen("GET", "/", {"accept-encoding": hc.ACCEPT_ENCODING}, b""), body)
        identity_reply = negotiate(Seen("GET", "/", {}, b""), body)
        assert compressed_reply.headers[-1][0] == "Content-Encoding"
        server.route = lambda seen: (compressed_reply if seen.accept_encoding == hc.ACCEPT_ENCODING
                                     else identity_reply)

        def peak(compressed: bool) -> int:
            c = make_client(compressed_responses=compressed)
            tracemalloc.start()
            try:
                text = c.request("GET", "x", raw_response=True)
                return tracemalloc.get_traced_memory()[1]
            finally:
                tracemalloc.stop()
                assert len(text) == len(body)

        identity_peak = peak(False)
        compressed_peak = peak(True)
        assert server.seen[0].accept_encoding == URLLIB_DEFAULT_ACCEPT_ENCODING
        assert server.seen[1].accept_encoding == hc.ACCEPT_ENCODING
        # Measured equal to within a few KiB on Python 3.10-3.14 (~50 MiB each).
        assert compressed_peak <= identity_peak + 1024 * 1024, (identity_peak, compressed_peak)


# ---------------------------------------------------------------------------
# Search API and CLI
# ---------------------------------------------------------------------------


def _search_routes(server: LocalServer, pages: list[list[dict]], query_id: str = "q-1") -> None:
    """Route the org URL lookup and the search API's initiate/poll/cancel calls."""
    search_root = server.url + "/search-api"
    state = {"page": 0}

    def route(seen: Seen) -> Reply:
        if seen.path == "/jwt":
            return negotiate(seen, json.dumps({"jwt": _make_jwt(time.time() + 3600)}).encode())
        if seen.path == f"/v1/orgs/{OID}/url":
            return negotiate(seen, json.dumps({"url": {"search": search_root}}).encode())
        if seen.path == "/search-api/v1/search" and seen.method == "POST":
            return negotiate(seen, json.dumps({"queryId": query_id}).encode())
        if seen.path.startswith(f"/search-api/v1/search/{query_id}") and seen.method == "GET":
            i = state["page"]
            state["page"] += 1
            result = {"type": "events", "rows": pages[i]}
            if i + 1 < len(pages):
                result["nextToken"] = f"tok-{i + 1}"
            return negotiate(seen, json.dumps({"completed": True, "results": [result]}).encode())
        if seen.method == "DELETE":
            return negotiate(seen, b"{}")
        return Reply(404, b'{"error": "no route"}')

    server.route = route


class TestSearchApi:
    def test_paginated_search_pages_are_requested_compressed(self, server):
        pages = [search_rows(6_000, seed=1), search_rows(6_000, seed=2)]  # ~3 MB each
        _search_routes(server, pages)
        org = Organization(make_client())
        results = list(Search(org).execute("-1h | * | *", 1_700_000_000, 1_700_003_600))

        assert [r["rows"] for r in results] == pages
        paths = [(s.method, s.path.split("?")[0]) for s in server.seen]
        assert paths == [
            ("GET", f"/v1/orgs/{OID}/url"),
            ("POST", "/search-api/v1/search"),
            ("GET", "/search-api/v1/search/q-1"),
            ("GET", "/search-api/v1/search/q-1"),
            ("DELETE", "/search-api/v1/search/q-1"),
        ]
        assert all(s.accept_encoding == hc.ACCEPT_ENCODING for s in server.seen)
        page_bytes = sum(len(json.dumps(p)) for p in pages)
        assert server.wire_bytes < page_bytes / 2

    def test_corrupt_page_surfaces_as_search_error(self, server):
        _search_routes(server, [search_rows(10)])
        inner = server.route

        def route(seen: Seen) -> Reply:
            if seen.method == "GET" and "/search/q-1" in seen.path:
                return Reply(200, _truncated_gzip(), [("Content-Encoding", "gzip")])
            return inner(seen)

        server.route = route
        org = Organization(make_client())
        with pytest.raises(SearchError) as exc:
            list(Search(org).execute("-1h | * | *", 1_700_000_000, 1_700_003_600))
        assert isinstance(exc.value.__cause__, ResponseDecodeError)
        polls = [s for s in server.seen if s.method == "GET" and "/search/q-1" in s.path]
        assert len(polls) == 1  # a decode error is not a transient poll error


class TestCli:
    def _run(self, server, monkeypatch, *args: str):
        from limacharlie.cli import cli

        monkeypatch.setenv("LC_OID", OID)
        monkeypatch.setenv("LC_API_KEY", "test-api-key")
        return CliRunner().invoke(cli, ["--output", "jsonl", *args], catch_exceptions=False)

    def test_search_run_requests_compression_on_every_call(self, server, monkeypatch):
        pages = [search_rows(500, seed=3)]
        _search_routes(server, pages)
        result = self._run(server, monkeypatch, "search", "run", "--query", "-1h | * | *",
                           "--start", "1700000000", "--end", "1700003600")
        assert result.exit_code == 0, result.output
        assert server.seen[0].path == "/jwt"
        assert all(s.accept_encoding == hc.ACCEPT_ENCODING for s in server.seen)
        assert all(s.headers["user-agent"].startswith("lc-cli/") for s in server.seen[1:])
        out_lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
        assert [json.loads(ln)["rows"] for ln in out_lines] == pages

    def test_search_run_opt_out_by_env(self, server, monkeypatch):
        monkeypatch.setenv("LC_NO_RESPONSE_COMPRESSION", "1")
        _search_routes(server, [search_rows(50, seed=4)])
        result = self._run(server, monkeypatch, "search", "run", "--query", "-1h | * | *",
                           "--start", "1700000000", "--end", "1700003600")
        assert result.exit_code == 0, result.output
        assert server.seen and all(s.accept_encoding == URLLIB_DEFAULT_ACCEPT_ENCODING for s in server.seen)
