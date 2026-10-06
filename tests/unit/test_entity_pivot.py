"""Entity Pivot SDK and CLI boundaries and public HTTP contract."""

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from limacharlie.cli import cli
from limacharlie.sdk.cloudsec import CloudSec

OID = "11111111-1111-4111-8111-111111111111"
ENTITY = "eh_aaaaaaaaaaaaaaaaaaaaaaaaaa"


@pytest.fixture
def sdk():
    org = MagicMock()
    org.oid = OID
    return CloudSec(org), org


def test_resolve_uses_json_and_preserves_candidates(sdk):
    cs, org = sdk
    response = {"index_ready": True, "results": [
        {"ambiguous": True, "matches": [{"entity_id": ENTITY}],
         "possible": [{"entity_id": "eu_aaaa", "confidence": "possible"}]}]}
    org.client.request.return_value = response
    identifiers = [{"value": "CORP\\fixture", "type": "ad_account"}, {"value": "fixture@example.com"}]
    assert cs.resolve_entities(identifiers, at=123) == response
    args, kwargs = org.client.request.call_args
    assert args == ("POST", f"cloudsec/{OID}/entities/resolve")
    assert kwargs["content_type"] == "application/json"
    assert json.loads(kwargs["raw_body"]) == {"identifiers": identifiers, "at": 123}
    assert org.client.request.call_count == 1  # No candidate is automatically followed.


@pytest.mark.parametrize("call,path,query", [
    (lambda cs: cs.get_entity(ENTITY, sightings_days=365), f"entities/{ENTITY}", [("sightings_days", "365")]),
    (lambda cs: cs.search_entities("host", kind="host", limit=100, cursor="page"),
     "entities/search", [("q", "host"), ("kind", "host"), ("limit", "100"), ("cursor", "page")]),
    (lambda cs: cs.list_entity_sightings(ENTITY, kind="user", since=0, until=20, limit=500, cursor="page"),
     f"entities/{ENTITY}/sightings", [("kind", "user"), ("since", "0"), ("until", "20"), ("limit", "500"), ("cursor", "page")]),
    (lambda cs: cs.get_entity_activity(ENTITY, since=10, until=20, sources=["email", "cloud"]),
     f"entities/{ENTITY}/activity", [("since", "10"), ("until", "20"), ("sources", "email,cloud")]),
])
def test_get_paths_and_typed_selectors(sdk, call, path, query):
    cs, org = sdk
    payload = {"card": None, "next_cursor": "opaque", "best_effort": True,
               "sources": [{"source": "email", "status": "forbidden", "truncated": True}]}
    org.client.request.return_value = payload
    assert call(cs) == payload
    args, kwargs = org.client.request.call_args
    assert args == ("GET", f"cloudsec/{OID}/{path}")
    assert kwargs["query_params"] == query


@pytest.mark.parametrize("call", [
    lambda cs: cs.resolve_entities([]),
    lambda cs: cs.resolve_entities([{"value": "host"}] * 101),
    lambda cs: cs.resolve_entities([{"value": "host", "oid": "foreign"}]),
    lambda cs: cs.resolve_entities([{"value": ""}]),
    lambda cs: cs.resolve_entities([{"value": "x" * 1025}]),
    lambda cs: cs.resolve_entities([{"value": "中" * 400}]),
    lambda cs: cs.resolve_entities([{"value": "host", "type": []}]),
    lambda cs: cs.resolve_entities([{"value": "host", "type": ""}]),
    lambda cs: cs.resolve_entities([{"value": "host", "type": "t" * 65}]),
    lambda cs: cs.resolve_entities([{"value": "host", "type": "中" * 22}]),
    lambda cs: cs.pivot_entity("host", type=""),
    lambda cs: cs.pivot_entity(""),
    lambda cs: cs.resolve_entities([{"value": "host"}], at=1.1),
    lambda cs: cs.resolve_entities([{"value": "host"}], at=True),
    lambda cs: cs.resolve_entities([{"value": "\x00" * 1024}] * 100),
    lambda cs: cs.get_entity(ENTITY + "/../../other"),
    lambda cs: cs.get_entity(ENTITY + "\n"),
    lambda cs: cs.get_entity(ENTITY, sightings_days=366),
    lambda cs: cs.search_entities("x"),
    lambda cs: cs.search_entities("中"),
    lambda cs: cs.search_entities("host", limit=101),
    lambda cs: cs.search_entities("host", kind="unknown"),
    lambda cs: cs.search_entities("host", cursor="x" * 8193),
    lambda cs: cs.list_entity_sightings(ENTITY, kind="unknown"),
    lambda cs: cs.list_entity_sightings(ENTITY, since=20, until=10),
    lambda cs: cs.list_entity_sightings(ENTITY, limit=501),
    lambda cs: cs.get_entity_activity(ENTITY, sources=[]),
    lambda cs: cs.get_entity_activity(ENTITY, sources="cloud"),
    lambda cs: cs.get_entity_activity(ENTITY, sources=["cloud", "cloud"]),
    lambda cs: cs.get_entity_activity(ENTITY, sources=["unknown"]),
    lambda cs: cs.get_entity_activity(ENTITY, since=0, until=30 * 86400 + 1),
])
def test_invalid_inputs_never_send_http(sdk, call):
    cs, org = sdk
    with pytest.raises(ValueError):
        call(cs)
    org.client.request.assert_not_called()


def test_unicode_batch_and_disabled_index_preserved(sdk):
    cs, org = sdk
    org.client.request.return_value = {"feature_disabled": True}
    assert cs.resolve_entities([{"value": "中" * 300}] * 100) == {"feature_disabled": True}
    assert len(org.client.request.call_args.kwargs["raw_body"]) < 128 * 1024
    cs.get_entity_activity(ENTITY)
    assert org.client.request.call_args.kwargs["query_params"] is None


@pytest.mark.parametrize("args,method,positional,kwargs", [
    (["resolve", "--identifier", "host", "--identifier", "other", "--type", "hostname", "--at", "123"],
     "resolve_entities", ([{"value": "host", "type": "hostname"}, {"value": "other", "type": "hostname"}],), {"at": 123, "observation_selectors": None}),
    (["pivot", "--identifier", "host", "--type", "hostname", "--at", "123"],
     "pivot_entity", ("host",), {"type": "hostname", "at": 123, "observation_selectors": None}),
    (["pivot", "--identifier", "host"], "pivot_entity", ("host",), {"type": None, "at": None, "observation_selectors": None}),
    (["get", "--entity-id", ENTITY, "--sightings-days", "365"], "get_entity", (ENTITY,), {"sightings_days": 365}),
    (["search", "--q", "host", "--kind", "host", "--limit", "100", "--cursor", "page"],
     "search_entities", ("host",), {"kind": "host", "limit": 100, "cursor": "page"}),
    (["sightings", "--entity-id", ENTITY, "--kind", "logon", "--since", "10", "--until", "20", "--limit", "500", "--cursor", "page"],
     "list_entity_sightings", (ENTITY,), {"kind": "logon", "since": 10, "until": 20, "limit": 500, "cursor": "page"}),
    (["activity", "--entity-id", ENTITY, "--source", "email", "--source", "cloud", "--since", "10", "--until", "20"],
     "get_entity_activity", (ENTITY,), {"sources": ["email", "cloud"], "since": 10, "until": 20}),
])
def test_cli_forwards_every_verb_and_preserves_json(args, method, positional, kwargs):
    payload = {"index_ready": False, "sources": [{"source": "email", "status": "forbidden", "truncated": True}]}
    with patch("limacharlie.commands.cloudsec._get_cloudsec") as get_cs:
        getattr(get_cs.return_value, method).return_value = payload
        result = CliRunner().invoke(cli, ["--output", "json", "cloudsec", "entity"] + args)
    assert result.exit_code == 0, result.output
    getattr(get_cs.return_value, method).assert_called_once_with(*positional, **kwargs)
    assert json.loads(result.output) == payload


@pytest.mark.parametrize("args", [["search", "--q", "host", "--limit", "101"],
                                  ["get", "--entity-id", ENTITY, "--sightings-days", "366"],
                                  ["activity", "--entity-id", ENTITY, "--source", "unknown"]])
def test_cli_rejects_invalid_option_bounds(args):
    with patch("limacharlie.commands.cloudsec._get_cloudsec") as get_cs:
        result = CliRunner().invoke(cli, ["cloudsec", "entity"] + args)
    assert result.exit_code != 0
    get_cs.assert_not_called()


def test_cli_entity_help_lists_all_contract_verbs():
    result = CliRunner().invoke(cli, ["cloudsec", "entity", "--help"])
    assert result.exit_code == 0
    for verb in ("pivot", "resolve", "get", "search", "sightings", "activity"):
        assert verb in result.output


@pytest.mark.parametrize("q", ["a" * 512, "a" * 513, "中" * 170 + "ab", "中" * 171])
def test_search_utf8_byte_boundary(sdk, q):
    cs, org = sdk
    if len(q.encode()) > 512:
        with pytest.raises(ValueError, match="512"):
            cs.search_entities(q)
        org.client.request.assert_not_called()
    else:
        cs.search_entities(q)
        assert org.client.request.call_args.kwargs["query_params"] == [("q", q)]
    with patch("limacharlie.commands.cloudsec._get_cloudsec") as get_cs:
        get_cs.return_value.search_entities.return_value = {}
        result = CliRunner().invoke(cli, ["cloudsec", "entity", "search", "--q", q])
    if len(q.encode()) > 512:
        assert result.exit_code != 0
        assert "512" in result.output
        get_cs.assert_not_called()
    else:
        assert result.exit_code == 0, result.output
        get_cs.return_value.search_entities.assert_called_once_with(q, kind=None, limit=None, cursor=None)


def test_search_help_documents_byte_limit():
    result = CliRunner().invoke(cli, ["cloudsec", "entity", "search", "--help"])
    assert result.exit_code == 0
    assert "512 UTF-8 bytes" in result.output


def test_github_login_lookup_and_external_adapter_card(sdk):
    cs, org = sdk
    identifiers = [{"type": "github_login", "value": "octo-fixture"}]
    org.client.request.return_value = {"index_ready": True, "results": []}
    assert cs.resolve_entities(identifiers)["index_ready"] is True
    assert json.loads(org.client.request.call_args.kwargs["raw_body"]) == {"identifiers": identifiers}
    card = {"entity": {"id": "eu_aaaa", "kind": "user", "attrs": {"external": True}},
            "telemetry_sources": [{"sid": OID, "platform": "github", "identity_type": "github_login",
                                   "hostname": "octo-fixture"}],
            "pivots": [{"route": "/sensors/{oid}/{sid}", "permission": "sensor.get",
                        "params": {"oid": OID, "sid": OID}}]}
    org.client.request.return_value = {"index_ready": True, "card": card}
    assert cs.get_entity("eu_aaaa")["card"] == card


def test_cli_resolves_github_login():
    with patch("limacharlie.commands.cloudsec._get_cloudsec") as get_cs:
        get_cs.return_value.resolve_entities.return_value = {"index_ready": True, "results": []}
        result = CliRunner().invoke(cli, ["--output", "json", "cloudsec", "entity", "resolve",
                                         "--identifier", "octo-fixture", "--type", "github_login"])
    assert result.exit_code == 0, result.output
    get_cs.return_value.resolve_entities.assert_called_once_with(
        [{"value": "octo-fixture", "type": "github_login"}], at=None, observation_selectors=None)


def test_github_user_id_lookup_and_external_adapter_card(sdk):
    cs, org = sdk
    identifiers = [{"type": "github_user_id", "value": "12345678901234567890"}]
    org.client.request.return_value = {"index_ready": True, "results": []}
    assert cs.resolve_entities(identifiers)["index_ready"] is True
    assert json.loads(org.client.request.call_args.kwargs["raw_body"]) == {"identifiers": identifiers}
    card = {"entity": {"id": "eu_aaaa", "kind": "user", "attrs": {"external": True}},
            "telemetry_sources": [{"sid": OID, "platform": "github", "identity_type": "github_login",
                                   "hostname": "12345678901234567890"}],
            "pivots": [{"route": "/sensors/{oid}/{sid}", "permission": "sensor.get",
                        "params": {"oid": OID, "sid": OID}}]}
    org.client.request.return_value = {"index_ready": True, "card": card}
    assert cs.get_entity("eu_aaaa")["card"] == card


def test_cli_resolves_github_user_id():
    with patch("limacharlie.commands.cloudsec._get_cloudsec") as get_cs:
        get_cs.return_value.resolve_entities.return_value = {"index_ready": True, "results": []}
        result = CliRunner().invoke(cli, ["--output", "json", "cloudsec", "entity", "resolve",
                                         "--identifier", "12345678901234567890", "--type", "github_user_id"])
    assert result.exit_code == 0, result.output
    get_cs.return_value.resolve_entities.assert_called_once_with(
        [{"value": "12345678901234567890", "type": "github_user_id"}], at=None, observation_selectors=None)


def test_unknown_identifier_type_is_forwarded_to_the_api(sdk):
    cs, org = sdk
    org.client.request.return_value = {"index_ready": True, "results": []}
    cs.resolve_entities([{"value": "host", "type": "future_type"}])
    assert json.loads(org.client.request.call_args.kwargs["raw_body"]) == {
        "identifiers": [{"value": "host", "type": "future_type"}]}
    pivoted = cs.pivot_entity("host", type="t" * 64)
    assert json.loads(org.client.request.call_args.kwargs["raw_body"])["identifiers"][0]["type"] == "t" * 64
    assert pivoted["cards"] == []


def test_cli_forwards_unknown_type_without_client_rejection():
    with patch("limacharlie.commands.cloudsec._get_cloudsec") as get_cs:
        get_cs.return_value.resolve_entities.return_value = {}
        result = CliRunner().invoke(cli, ["cloudsec", "entity", "resolve",
                                         "--identifier", "x", "--type", "future_type"])
    assert result.exit_code == 0, result.output
    get_cs.return_value.resolve_entities.assert_called_once_with(
        [{"value": "x", "type": "future_type"}], at=None, observation_selectors=None)


# ---------------------------------------------------------------------------
# pivot_entity
# ---------------------------------------------------------------------------

def _id(n):
    return "eu_" + "a" * 20 + "abcdefghij"[n // 10] + "abcdefghij"[n % 10]


def _match(entity_id, confidence="authoritative"):
    return {"entity_id": entity_id, "confidence": confidence}


def _pivot_org(resolve_response, cards=None, failing=()):
    """Org whose client answers the resolve POST and per-entity card GETs."""
    org = MagicMock()
    org.oid = OID
    calls = []

    def request(method, path, **kwargs):
        calls.append((method, path))
        if method == "POST":
            return resolve_response
        entity_id = path.rsplit("/", 1)[1]
        if entity_id in failing:
            raise RuntimeError("boom")
        return {"index_ready": True, "card": {"entity": {"id": entity_id}}}

    org.client.request.side_effect = request
    return CloudSec(org), calls


def _card_ids(calls):
    return [path.rsplit("/", 1)[1] for method, path in calls if method == "GET"]


def test_pivot_follows_only_confident_matches_of_unambiguous_results():
    results = [
        {"ambiguous": False, "matches": [_match(_id(1)), _match(_id(2), "corroborated"),
                                          _match(_id(3), "possible")],
         "possible": [_match(_id(4), "possible")]},
        {"ambiguous": True, "matches": [_match(_id(5))], "possible": []},
        {"matches": [_match(_id(6))]},  # ambiguity unknown: never followed
    ]
    cs, calls = _pivot_org({"index_ready": True, "results": results})
    out = cs.pivot_entity("alice@example.com", type="email", at=5)
    assert _card_ids(calls) == [_id(1), _id(2)]
    assert [c["card"]["entity"]["id"] for c in out["cards"]] == [_id(1), _id(2)]
    assert out["candidates"] == results
    assert "truncated" not in out and "card_errors" not in out
    assert calls[0] == ("POST", f"cloudsec/{OID}/entities/resolve")


def test_pivot_dedupes_entities_across_results():
    results = [{"ambiguous": False, "matches": [_match(_id(1))]},
               {"ambiguous": False, "matches": [_match(_id(1)), _match(_id(1), "corroborated")]}]
    cs, calls = _pivot_org({"index_ready": True, "results": results})
    out = cs.pivot_entity("host")
    assert _card_ids(calls) == [_id(1)]
    assert len(out["cards"]) == 1


def test_pivot_caps_cards_at_ten_and_marks_truncated():
    matches = [_match(_id(n)) for n in range(11)]
    cs, calls = _pivot_org({"index_ready": True, "results": [{"ambiguous": False, "matches": matches}]})
    out = cs.pivot_entity("host")
    assert _card_ids(calls) == [_id(n) for n in range(10)]
    assert len(out["cards"]) == 10
    assert out["truncated"] is True


def test_pivot_exactly_ten_cards_is_not_truncated():
    matches = [_match(_id(n)) for n in range(10)]
    cs, calls = _pivot_org({"index_ready": True, "results": [{"ambiguous": False, "matches": matches}]})
    out = cs.pivot_entity("host")
    assert len(out["cards"]) == 10
    assert "truncated" not in out


def test_pivot_records_card_failure_and_keeps_other_cards():
    matches = [_match(_id(1)), _match(_id(2)), _match(_id(3))]
    cs, calls = _pivot_org({"index_ready": True, "results": [{"ambiguous": False, "matches": matches}]},
                           failing={_id(2)})
    out = cs.pivot_entity("host")
    assert [c["card"]["entity"]["id"] for c in out["cards"]] == [_id(1), _id(3)]
    assert out["card_errors"] == [{"entity_id": _id(2), "status": "unavailable"}]
    assert out["truncated"] is True


@pytest.mark.parametrize("flags", [{"index_ready": False}, {},
                                   {"index_ready": True, "feature_disabled": True}])
def test_pivot_reads_no_cards_unless_index_is_ready_and_enabled(flags):
    results = [{"ambiguous": False, "matches": [_match(_id(1))]}]
    cs, calls = _pivot_org({"results": results, **flags})
    out = cs.pivot_entity("host")
    assert _card_ids(calls) == []
    assert out["cards"] == []
    assert out["candidates"] == results
    for key, value in flags.items():
        assert out[key] == value


def test_pivot_passes_through_every_other_resolve_key():
    response = {"index_ready": True, "results": [], "sources": [{"source": "edr", "stale": False}],
                "sightings": "forbidden", "future_field": {"a": 1}}
    cs, calls = _pivot_org(response)
    out = cs.pivot_entity("host")
    assert out == {"cards": [], "candidates": [], "index_ready": True,
                   "sources": response["sources"], "sightings": "forbidden",
                   "future_field": {"a": 1}}
    assert "results" not in out


def test_pivot_sends_single_identifier_with_type_and_at():
    cs, calls = _pivot_org({"index_ready": True, "results": []})
    org = cs._org
    cs.pivot_entity("203.0.113.7", type="ip", at=1791000000)
    body = json.loads(org.client.request.call_args.kwargs["raw_body"])
    assert body == {"identifiers": [{"value": "203.0.113.7", "type": "ip"}], "at": 1791000000}


_ENTITY_COMMANDS = ("pivot", "resolve", "get", "search", "sightings", "activity")


def test_each_entity_command_has_its_own_explain_text():
    from limacharlie.discovery import get_explain
    texts = {verb: get_explain(f"cloudsec.entity.{verb}") for verb in _ENTITY_COMMANDS}
    assert all(texts.values())
    assert len(set(texts.values())) == len(_ENTITY_COMMANDS)
    assert "redirect_to" in texts["get"] and "next_cursor" in texts["search"]
    assert "best_effort" in texts["sightings"] and "not_subscribed" in texts["activity"]
    assert "ambiguous" in texts["pivot"] and "truncated" in texts["pivot"]


def test_entity_ai_help_renders_per_command_text():
    result = CliRunner().invoke(cli, ["cloudsec", "entity", "pivot", "--ai-help"])
    assert result.exit_code == 0, result.output
    assert "card_errors" in result.output


# ---------------------------------------------------------------------------
# Observation selectors and observed pivots
# ---------------------------------------------------------------------------

COLLECTOR = "0a1b2c3d-0000-4000-8000-000000000001"
HOST_ID = "eh_bbbbbbbbbbbbbbbbbbbbbbbbbb"

DEVICE_SELECTOR = {"type": "vendor_device_id", "value": "dev-123", "platform": "sophos",
                   "origin_sid": COLLECTOR}
HOSTNAME_SELECTOR = {"type": "foreign_hostname", "value": "WEB-01"}


def _observed_device(**overrides):
    device = {
        "origin_sid": COLLECTOR, "platform": "sophos", "vendor_device_id": "dev-123",
        "day": "2026-10-05", "names": ["WEB-01"], "local_ips": ["10.0.0.7"],
        "recipes": [{"id": "sophos.device", "version": 1}],
        "first_ts": 1791200000, "last_ts": 1791230000,
        "confidence": "corroborated", "approximate": True,
        "reason": "hostname_internal_ip_same_day",
        "candidates": [{"entity": {"id": HOST_ID, "kind": "host", "display_name": "web-01"},
                        "confidence": "corroborated", "reason": "hostname_internal_ip_same_day",
                        "sids": [COLLECTOR]}],
    }
    device.update(overrides)
    return device


OBSERVED_RESOLVE = {
    "index_ready": True,
    "results": [{"input": {"value": "WEB-01", "type": "hostname"}, "detected_types": ["hostname"],
                 "matches": [], "possible": [], "ambiguous": False}],
    "observed_matches": [{"selector": DEVICE_SELECTOR, "devices": [_observed_device()]}],
    "observations": {"status": "ok", "queries": 4, "rows": 12},
}


def _selector_body(org):
    return json.loads(org.client.request.call_args.kwargs["raw_body"])


def test_resolve_sends_selectors_and_preserves_observed_matches(sdk):
    cs, org = sdk
    org.client.request.return_value = OBSERVED_RESOLVE
    identifiers = [{"value": "WEB-01", "type": "hostname"}]
    out = cs.resolve_entities(
        identifiers, at=1791200000, observation_selectors=[DEVICE_SELECTOR, HOSTNAME_SELECTOR])
    assert _selector_body(org) == {
        "identifiers": identifiers, "at": 1791200000,
        "observation_selectors": [DEVICE_SELECTOR, HOSTNAME_SELECTOR]}
    assert out == OBSERVED_RESOLVE
    # Observed candidates are evidence: nothing is fetched on their behalf.
    assert org.client.request.call_count == 1


@pytest.mark.parametrize("selectors", [None, []])
def test_resolve_omits_selectors_key_when_none_given(sdk, selectors):
    cs, org = sdk
    org.client.request.return_value = {}
    cs.resolve_entities([{"value": "host"}], observation_selectors=selectors)
    assert _selector_body(org) == {"identifiers": [{"value": "host"}]}


def test_resolve_drops_empty_optional_selector_fields(sdk):
    cs, org = sdk
    org.client.request.return_value = {}
    cs.resolve_entities(
        [{"value": "host"}],
        observation_selectors=[{"type": "vendor_device_id", "value": "d", "platform": "okta",
                                "origin_sid": ""},
                               {"type": "foreign_hostname", "value": "h", "platform": None}])
    assert _selector_body(org)["observation_selectors"] == [
        {"type": "vendor_device_id", "value": "d", "platform": "okta"},
        {"type": "foreign_hostname", "value": "h"}]


def _dev(**kw):
    return {"type": "vendor_device_id", "value": "dev", "platform": "sophos", **kw}


def _host(**kw):
    return {"type": "foreign_hostname", "value": "web", **kw}


@pytest.mark.parametrize("selectors", [
    [_host()] * 5,
    "foreign_hostname",
    [["foreign_hostname", "web"]],
    [{"value": "web"}],
    [_host(type="hostname")],
    [_host(type="ip")],
    [_host(extra="x")],
    [_host(value="")],
    [_host(value="   ")],
    [_host(value="\t\n")],
    [_host(value=None)],
    [_host(value=7)],
    [_host(value="bad\udcff")],
    [_host(value="h" * 513)],
    [_host(value="中" * 171)],
    [_host(platform="sophos")],
    [_host(origin_sid=COLLECTOR)],
    [_dev(value="d" * 129)],
    [_dev(value="中" * 43)],
    [_dev(value="   ")],
    [{"type": "vendor_device_id", "value": "dev"}],
    [_dev(platform="")],
    [_dev(platform="SOPHOS")],
    [_dev(platform="defender")],
    [_dev(origin_sid=COLLECTOR.upper())],
    [_dev(origin_sid=COLLECTOR.replace("-", ""))],
    [_dev(origin_sid=COLLECTOR + "\n")],
    [_dev(origin_sid="not-a-uuid")],
    [_dev(origin_sid=7)],
])
def test_invalid_selectors_never_send_http(sdk, selectors):
    cs, org = sdk
    with pytest.raises(ValueError):
        cs.resolve_entities([{"value": "host"}], observation_selectors=selectors)
    with pytest.raises(ValueError):
        cs.pivot_entity("host", observation_selectors=selectors)
    org.client.request.assert_not_called()


@pytest.mark.parametrize("selectors", [
    [_host()] * 4,
    [_host(value="h" * 512)],
    [_host(value="中" * 170 + "ab")],
    [_dev(value="d" * 128)],
    [_dev(value="中" * 42 + "ab")],
    [_dev(value="a:b@c")],
    [_dev(platform=p) for p in ("sophos", "crowdstrike", "office365", "entraid")],
    [_dev(platform=p, origin_sid=COLLECTOR) for p in ("okta", "duo")],
])
def test_selector_limits_are_inclusive(sdk, selectors):
    cs, org = sdk
    org.client.request.return_value = {}
    cs.resolve_entities([{"value": "host"}], observation_selectors=selectors)
    assert _selector_body(org)["observation_selectors"] == selectors


def test_selectors_count_towards_the_body_size_limit(sdk):
    cs, org = sdk
    org.client.request.return_value = {}
    # NUL escapes to six bytes, so 100 of these ride just under 128 KiB on their own.
    size = 0
    for n in range(1, 400):
        ids = [{"value": "\x00" * n}] * 100
        encoded = len(json.dumps({"identifiers": ids}, ensure_ascii=False, separators=(",", ":")))
        if encoded > 128 * 1024:
            break
        size = n
    ids = [{"value": "\x00" * size}] * 100
    cs.resolve_entities(ids)
    big = [_host(value=chr(ord("a") + i) * 512) for i in range(4)]
    with pytest.raises(ValueError, match="128 KiB"):
        cs.resolve_entities(ids, observation_selectors=big)
    assert org.client.request.call_count == 1


def test_pivot_threads_selectors_and_never_follows_observed_candidates():
    authoritative = _id(1)
    resolution = {
        "index_ready": True,
        "results": [{"ambiguous": False, "matches": [_match(authoritative)], "possible": []}],
        "observed_matches": [{"selector": DEVICE_SELECTOR, "devices": [
            _observed_device(candidates=[
                {"entity": {"id": HOST_ID, "kind": "host", "display_name": "web-01"},
                 "confidence": "corroborated", "reason": "hostname_internal_ip_same_day"},
                {"entity": {"id": _id(2), "kind": "user", "display_name": "x"},
                 "confidence": "possible", "reason": "x"}])]}],
        "observations": {"status": "incomplete", "reason": "bounds", "queries": 16, "rows": 2000,
                         "truncated": True},
    }
    cs, calls = _pivot_org(resolution)
    out = cs.pivot_entity("web-01", type="hostname", at=1791200000,
                          observation_selectors=[DEVICE_SELECTOR])
    body = json.loads(cs._org.client.request.call_args_list[0].kwargs["raw_body"])
    assert body == {"identifiers": [{"value": "web-01", "type": "hostname"}], "at": 1791200000,
                    "observation_selectors": [DEVICE_SELECTOR]}
    assert _card_ids(calls) == [authoritative]
    assert out["observed_matches"] == resolution["observed_matches"]
    assert out["observations"] == resolution["observations"]
    assert "results" not in out and len(out["cards"]) == 1


def test_pivot_with_only_observed_candidates_reads_no_cards():
    cs, calls = _pivot_org(OBSERVED_RESOLVE)
    out = cs.pivot_entity("WEB-01", type="hostname", observation_selectors=[DEVICE_SELECTOR])
    assert _card_ids(calls) == []
    assert out["cards"] == []
    assert out["observed_matches"][0]["devices"][0]["candidates"][0]["entity"]["id"] == HOST_ID


def test_card_observation_fields_and_chrome_user_are_preserved(sdk):
    cs, org = sdk
    card_response = {
        "index_ready": True,
        "card": {
            "entity": {"id": "eu_aaaa", "kind": "user", "attrs": {"external": True}},
            "telemetry_sources": [{"sid": COLLECTOR, "platform": "chrome", "identity_type": "email",
                                   "identity_source": "parser", "hostname": "Profile (a@example.com)"}],
            "also_seen_as": [_observed_device(confidence="possible", incomplete=True,
                                              conflicting_names=True)],
            "cloud_sign_ins": [{
                "origin_sid": COLLECTOR, "platform": "office365", "day": "2026-10-05",
                "principal_type": "email", "principal": "a@example.com", "outcome": "success",
                "successful": True, "first_ts": 1791200000, "last_ts": 1791230000,
                "recipes": [{"id": "o365.signin", "version": 1}],
                "samples": [{"ts": 1791200000, "label": "first", "hosts": [], "no_observed_match": True}],
            }],
        },
        "observations": {"status": "unavailable", "reason": "schema_missing", "queries": 0, "rows": 0},
    }
    org.client.request.return_value = card_response
    assert cs.get_entity("eh_aaaa", sightings_days=7) == card_response
    org.client.request.return_value = {"index_ready": True, "redirect_to": "eu_aaaa",
                                       "card": card_response["card"]}
    assert cs.get_entity("eh_aaaa")["redirect_to"] == "eu_aaaa"


# ---- CLI ------------------------------------------------------------------

def _invoke(verb, *args):
    with patch("limacharlie.commands.cloudsec._get_cloudsec") as get_cs:
        cs = get_cs.return_value
        cs.resolve_entities.return_value = OBSERVED_RESOLVE
        cs.pivot_entity.return_value = OBSERVED_RESOLVE
        result = CliRunner().invoke(cli, ["--output", "json", "cloudsec", "entity", verb, *args])
    return result, cs


@pytest.mark.parametrize("flags,expected", [
    (["--device", f"sophos:dev-123@{COLLECTOR}"], [DEVICE_SELECTOR]),
    (["--device", "crowdstrike:aid-1"],
     [{"type": "vendor_device_id", "value": "aid-1", "platform": "crowdstrike"}]),
    # Only the first ':' splits the platform; the last '@' splits the collector.
    (["--device", f"okta:a:b@c@{COLLECTOR}"],
     [{"type": "vendor_device_id", "value": "a:b@c", "platform": "okta", "origin_sid": COLLECTOR}]),
    (["--foreign-hostname", "WEB-01"], [HOSTNAME_SELECTOR]),
    (["--foreign-hostname", "b", "--device", "duo:d1", "--foreign-hostname", "a", "--device", "entraid:e1"],
     [{"type": "vendor_device_id", "value": "d1", "platform": "duo"},
      {"type": "vendor_device_id", "value": "e1", "platform": "entraid"},
      {"type": "foreign_hostname", "value": "b"}, {"type": "foreign_hostname", "value": "a"}]),
])
def test_cli_builds_selectors_for_resolve_and_pivot(flags, expected):
    result, cs = _invoke("resolve", "--identifier", "web-01", "--at", "5", *flags)
    assert result.exit_code == 0, result.output
    cs.resolve_entities.assert_called_once_with(
        [{"value": "web-01"}], at=5, observation_selectors=expected)
    assert json.loads(result.output) == OBSERVED_RESOLVE
    result, cs = _invoke("pivot", "--identifier", "web-01", "--type", "hostname", *flags)
    assert result.exit_code == 0, result.output
    cs.pivot_entity.assert_called_once_with(
        "web-01", type="hostname", at=None, observation_selectors=expected)


@pytest.mark.parametrize("flags,fragment", [
    (["--device", "sophos"], "PLATFORM:VENDOR_ID"),
    (["--device", ":dev"], "PLATFORM:VENDOR_ID"),
    (["--device", "sophos:"], "PLATFORM:VENDOR_ID"),
    (["--device", "sophos:dev@"], "non-empty"),
    (["--device", f"sophos:@{COLLECTOR}"], "non-empty"),
    (["--device", "defender:dev"], "platform"),
    (["--device", f"sophos:dev@{COLLECTOR.upper()}"], "origin_sid"),
    (["--device", "sophos:dev@nope"], "origin_sid"),
    (["--device", "sophos:" + "d" * 129], "128"),
    (["--foreign-hostname", "   "], "blank"),
    (["--foreign-hostname", "h" * 513], "512"),
    (["--device", "sophos:a", "--device", "sophos:b", "--foreign-hostname", "c",
      "--foreign-hostname", "d", "--foreign-hostname", "e"], "at most 4"),
])
@pytest.mark.parametrize("verb", ["resolve", "pivot"])
def test_cli_rejects_bad_selectors_before_any_call(verb, flags, fragment):
    result, cs = _invoke(verb, "--identifier", "web-01", *flags)
    assert result.exit_code == 2, result.output
    assert fragment in result.output
    cs.resolve_entities.assert_not_called()
    cs.pivot_entity.assert_not_called()


def test_cli_four_selectors_are_accepted():
    result, cs = _invoke("resolve", "--identifier", "x", "--device", "sophos:a", "--device", "sophos:b",
                         "--foreign-hostname", "c", "--foreign-hostname", "d")
    assert result.exit_code == 0, result.output
    assert len(cs.resolve_entities.call_args.kwargs["observation_selectors"]) == 4


@pytest.mark.parametrize("verb", ["resolve", "pivot"])
def test_cli_help_documents_selectors_at_and_typed_hostname(verb):
    result = CliRunner().invoke(cli, ["cloudsec", "entity", verb, "--help"], terminal_width=200)
    assert result.exit_code == 0
    flat = " ".join(result.output.split())
    assert "--device" in flat and "--foreign-hostname" in flat
    assert "PLATFORM:VENDOR_ID[@ORIGIN_SID]" in flat
    assert "also pins the UTC day" in flat
    assert "'hostname' that the inventory does not know" in flat


def test_ai_help_states_unknown_not_none_and_observation_vocabulary():
    from limacharlie.discovery import get_explain
    resolve, pivot, card = (get_explain(f"cloudsec.entity.{v}") for v in ("resolve", "pivot", "get"))
    for text in (resolve, pivot, card):
        for word in ("incomplete", "unavailable", "forbidden", "UNKNOWN", "schema_missing",
                     "query_budget", "deadline", "bounds"):
            assert word in text, word
    for key in ("observed_matches", "--device", "--foreign-hostname", "corroborated", "approximate",
                "candidates[].entity", "conflicting_names"):
        assert key in resolve, key
    assert "does NOT read their cards" in pivot and "entity get" in pivot
    for key in ("also_seen_as", "cloud_sign_ins", "identity_source", "'parser'", "'mapping'",
                "Chrome", "eu_", "redirect_to"):
        assert key in card, key
    assert "16 queries" in pivot and "16 queries" in card
    assert "typed" in resolve and "never does" in resolve
