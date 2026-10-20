"""Hive listing through the real SDK HTTP transport against a fake gateway."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen

import pytest
from click.testing import CliRunner

import limacharlie.client as client_mod
from limacharlie.cli import cli
from limacharlie.errors import ApiError
from limacharlie.sdk.hive import Hive, is_listing_too_large
from limacharlie.sdk.organization import Organization

OID = "11111111-2222-3333-4444-555555555555"


def _record(i):
    return {
        "data": {"i": i},
        "sys_mtd": {"etag": f"etag-{i}"},
        "usr_mtd": {"enabled": True, "tags": ["t"]},
    }


class FakeGateway:
    """Emulates the hive listing endpoint of the API gateway.

    ``legacy`` behaves like a gateway that predates paging: it ignores the
    limit, cursor and mtd_only query parameters. ``too_large_at`` makes the
    unpaged full listing answer 413 above that many records.
    """

    def __init__(self, n):
        self.records = {f"rec-{i:03d}": _record(i) for i in range(n)}
        self.legacy = False
        self.too_large_at = None
        self.queries = []

    @staticmethod
    def stripped(records):
        return {k: {"sys_mtd": v["sys_mtd"], "usr_mtd": v["usr_mtd"]} for k, v in records.items()}

    def answer(self, query):
        """Return (status, body) for one listing request."""
        self.queries.append({k: v[0] for k, v in query.items()})
        paged = not self.legacy and ("limit" in query or "cursor" in query)
        mtd_only = not self.legacy and query.get("mtd_only") == ["true"]
        if not paged:
            if not self.legacy and self.too_large_at is not None and not mtd_only \
                    and len(self.records) > self.too_large_at:
                return 413, {"error": "lc_error_code:HIVE_LISTING_TOO_LARGE - page with limit"}
            return 200, self.stripped(self.records) if mtd_only else self.records
        cursor = query.get("cursor", [""])[0]
        if cursor == "bad":
            return 400, {"error": "lc_error_code:INVALID_CURSOR - bad cursor"}
        limit = int(query["limit"][0])
        start = int(cursor) if cursor else 0
        names = sorted(self.records)
        end = start + limit
        next_cursor = str(end) if end < len(names) else ""
        page = {n: self.records[n] for n in names[start:end]}
        if mtd_only:
            page = self.stripped(page)
        return 200, {"records": page, "next_cursor": next_cursor}


@pytest.fixture
def gateway(monkeypatch):
    gw = FakeGateway(0)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            url = urlparse(self.path)
            parts = url.path.split("/")
            if len(parts) > 5 and parts[-1] == "data":
                # GET hive/<hive>/<oid>/<record>/data
                status, body = 200, gw.records[parts[-2]]
            else:
                status, body = gw.answer(parse_qs(url.query))
            raw = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

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
    gw.client = client_mod.Client(oid=OID, jwt="test.jwt.signature", timeout=5)
    gw.hive = Hive(Organization(gw.client), "lookup")
    try:
        yield gw
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def fill(gw, n):
    gw.records = {f"rec-{i:03d}": _record(i) for i in range(n)}


def test_list_page_walks_the_cursor(gateway):
    fill(gateway, 25)
    sizes, seen, cursor = [], {}, None
    while True:
        page, cursor = gateway.hive.list_page(limit=10, cursor=cursor)
        sizes.append(len(page))
        seen.update(page)
        if not cursor:
            break
    assert sizes == [10, 10, 5]
    assert sorted(seen) == sorted(gateway.records)
    assert seen["rec-007"].data == {"i": 7}
    assert gateway.queries[0] == {"limit": "10"}
    assert gateway.queries[1] == {"limit": "10", "cursor": "10"}


def test_list_page_always_sends_limit_and_forwards_options(gateway):
    fill(gateway, 3)
    page, cursor = gateway.hive.list_page(mtd_only=True, tag_prefix="pre", max_bytes=1234)
    assert gateway.queries[0] == {"limit": "50", "mtd_only": "true", "tag_prefix": "pre", "max_bytes": "1234"}
    assert len(page) == 3 and cursor == ""
    assert all(r.data is None for r in page.values())


def test_iter_pages_yields_every_page(gateway):
    fill(gateway, 25)
    pages = list(gateway.hive.iter_pages(limit=10))
    assert [len(p) for p in pages] == [10, 10, 5]


def test_empty_hive(gateway):
    fill(gateway, 0)
    assert gateway.hive.list_page() == ({}, "")
    assert gateway.hive.list() == {}


def test_legacy_gateway_list_page_is_one_final_page(gateway):
    fill(gateway, 25)
    gateway.legacy = True
    page, cursor = gateway.hive.list_page(limit=10)
    assert cursor == ""
    assert len(page) == 25
    assert len(list(gateway.hive.iter_pages(limit=10))) == 1
    assert len(gateway.queries) == 2, "a legacy answer is one request, not a loop"


def test_legacy_gateway_mtd_only_strips_data(gateway):
    fill(gateway, 5)
    gateway.legacy = True
    for records in (gateway.hive.list_mtd(), gateway.hive.list_page(mtd_only=True)[0]):
        assert len(records) == 5
        assert all(r.data is None and r.etag for r in records.values())


def test_records_named_like_the_envelope_are_not_an_envelope(gateway):
    gateway.legacy = True
    gateway.records = {"records": _record(1), "next_cursor": _record(2)}
    page, cursor = gateway.hive.list_page()
    assert cursor == ""
    assert sorted(page) == ["next_cursor", "records"]


def test_list_mtd_uses_mtd_only(gateway):
    fill(gateway, 5)
    records = gateway.hive.list_mtd()
    assert gateway.queries == [{"mtd_only": "true"}]
    assert len(records) == 5
    assert all(r.data is None and r.etag for r in records.values())


def test_list_unchanged_when_small(gateway):
    fill(gateway, 5)
    gateway.too_large_at = 100
    records = gateway.hive.list()
    assert gateway.queries == [{}]
    assert records["rec-002"].data == {"i": 2}


def test_list_falls_back_to_pages_on_413(gateway):
    fill(gateway, 1200)
    gateway.too_large_at = 100
    records = gateway.hive.list()
    assert sorted(records) == sorted(gateway.records)
    assert records["rec-777"].data == {"i": 777}
    # One refused full listing (413 is not retried), then 3 pages of 500.
    assert gateway.queries[0] == {}
    assert [q["limit"] for q in gateway.queries[1:]] == ["500"] * 3


def test_list_mtd_falls_back_to_pages_on_413(gateway):
    fill(gateway, 700)
    original = gateway.answer

    def refuse_unpaged(query):
        if "limit" not in query:
            gateway.queries.append({k: v[0] for k, v in query.items()})
            return 413, {"error": "HIVE_LISTING_TOO_LARGE"}
        return original(query)

    gateway.answer = refuse_unpaged
    records = gateway.hive.list_mtd()
    assert len(records) == 700
    assert all(r.data is None for r in records.values())
    assert gateway.queries[1]["mtd_only"] == "true"


def test_invalid_cursor_is_an_error_and_not_retried(gateway):
    fill(gateway, 5)
    with pytest.raises(ApiError) as exc:
        gateway.hive.list_page(cursor="bad")
    assert "INVALID_CURSOR" in str(exc.value)
    assert not is_listing_too_large(exc.value)
    assert len(gateway.queries) == 1


def test_listing_too_large_is_not_retried(gateway):
    fill(gateway, 10)
    gateway.too_large_at = 1
    with pytest.raises(ApiError) as exc:
        gateway.client.request("GET", f"hive/lookup/{OID}")
    assert is_listing_too_large(exc.value)
    assert len(gateway.queries) == 1


def test_other_errors_are_not_swallowed_by_the_fallback(gateway):
    def forbidden(query):
        gateway.queries.append({})
        return 400, {"error": "lc_error_code:UNAUTHORIZED - nope"}

    gateway.answer = forbidden
    for call in (gateway.hive.list, gateway.hive.list_mtd):
        with pytest.raises(ApiError):
            call()


def test_stuck_cursor_is_refused(gateway):
    gateway.answer = lambda query: (200, {"records": {}, "next_cursor": "same"})
    with pytest.raises(ApiError, match="did not advance"):
        list(gateway.hive.iter_pages())


def test_unexpected_listing_shape_is_an_error(gateway):
    gateway.answer = lambda query: (200, [1, 2])
    with pytest.raises(ApiError, match="Unexpected hive listing"):
        gateway.hive.list_page()


def test_cli_list_metadata_only_and_export_use_mtd_listing(gateway, monkeypatch):
    fill(gateway, 3)
    monkeypatch.setattr("limacharlie.commands.hive._get_org", lambda ctx: Organization(gateway.client))
    runner = CliRunner()

    result = runner.invoke(cli, ["--output", "json", "hive", "list", "--hive-name", "lookup", "--metadata-only"])
    assert result.exit_code == 0, result.output
    assert gateway.queries == [{"mtd_only": "true"}]
    assert sorted(json.loads(result.output)) == ["rec-000", "rec-001", "rec-002"]


@pytest.mark.parametrize("body", [
    {"records": {"a": _record(1)}},
    {"records": {"a": _record(1)}, "next_cursor": None},
])
def test_envelope_without_a_cursor_is_still_an_envelope(gateway, body):
    gateway.answer = lambda query: (200, body)
    page, cursor = gateway.hive.list_page()
    assert cursor == ""
    assert list(page) == ["a"]


def test_lone_legacy_record_named_records_is_a_plain_map(gateway):
    gateway.legacy = True
    gateway.records = {"records": _record(1)}
    page, cursor = gateway.hive.list_page()
    assert cursor == ""
    assert list(page) == ["records"] and page["records"].etag == "etag-1"


def test_cli_export_lists_names_without_data_then_fetches_each_record(gateway, monkeypatch):
    fill(gateway, 3)
    monkeypatch.setattr("limacharlie.commands.hive._get_org", lambda ctx: Organization(gateway.client))

    result = CliRunner().invoke(cli, ["--output", "json", "hive", "export", "--hive-name", "lookup"])
    assert result.exit_code == 0, result.output
    assert gateway.queries == [{"mtd_only": "true"}]
    exported = json.loads(result.output)
    assert exported["rec-001"]["data"] == {"i": 1}


def test_page_with_a_cursor_but_no_visible_records_is_an_envelope(gateway):
    gateway.answer = lambda query: (200, {"next_cursor": "opaque"})
    page, cursor = gateway.hive.list_page()
    assert page == {} and cursor == "opaque"


def test_records_that_is_not_an_object_is_an_error(gateway):
    gateway.answer = lambda query: (200, {"records": [1], "next_cursor": ""})
    with pytest.raises(ApiError, match="not an object"):
        gateway.hive.list_page()


def test_legacy_gateway_tag_prefix_is_applied_client_side(gateway):
    fill(gateway, 4)
    gateway.records["rec-001"]["usr_mtd"]["tags"] = ["env:prod", "x"]
    gateway.records["rec-003"]["usr_mtd"]["tags"] = ["env:dev"]
    gateway.legacy = True
    page, cursor = gateway.hive.list_page(tag_prefix="env:")
    assert sorted(page) == ["rec-001", "rec-003"] and cursor == ""
    assert list(gateway.hive.list_page(tag_prefix="nope")[0]) == []


def test_gateway_timeout_on_a_whole_hive_listing_is_not_replayed(gateway):
    def timeout(query):
        gateway.queries.append({k: v[0] for k, v in query.items()})
        return 504, {"error": "timeout"}

    gateway.answer = timeout
    for call in (gateway.hive.list, gateway.hive.list_mtd):
        with pytest.raises(ApiError):
            call()
    assert len(gateway.queries) == 2


def test_cli_shortcut_and_dr_list_metadata_only(gateway, monkeypatch):
    fill(gateway, 2)
    for module in ("limacharlie.commands._hive_shortcut", "limacharlie.commands.dr"):
        monkeypatch.setattr(f"{module}._get_org", lambda ctx: Organization(gateway.client))
    for argv in (["lookup", "list", "--metadata-only"], ["dr", "list", "--metadata-only"]):
        gateway.queries.clear()
        result = CliRunner().invoke(cli, ["--output", "json", *argv])
        assert result.exit_code == 0, result.output
        assert gateway.queries == [{"mtd_only": "true"}]
        assert all(rec["data"] is None for rec in json.loads(result.output).values())
