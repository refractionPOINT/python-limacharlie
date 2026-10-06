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
     "resolve_entities", ([{"value": "host", "type": "hostname"}, {"value": "other", "type": "hostname"}],),
     {"at": 123, "observation_selectors": None}),
    (["pivot", "--identifier", "host", "--type", "hostname", "--at", "123"],
     "pivot_entity", ("host",), {"type": "hostname", "at": 123, "observation_selectors": None}),
    (["pivot", "--identifier", "host"], "pivot_entity", ("host",),
     {"type": None, "at": None, "observation_selectors": None}),
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


# ---------------------------------------------------------------------------
# Observation selectors
# ---------------------------------------------------------------------------

DEVICE = {"type": "vendor_device_id", "platform": "sophos", "value": "device-1",
          "origin_sid": "00000000-0000-4000-8000-000000000000"}
HOSTNAME = {"type": "foreign_hostname", "value": "WEB-01"}


def test_resolve_forwards_selectors_and_returns_observed_matches(sdk):
    cs, org = sdk
    response = {"index_ready": True, "results": [{"matches": [], "possible": []}],
                "observed_matches": [{"selector": DEVICE, "devices": [{"vendor_device_id": "device-1"}]}],
                "observations": {"status": "ok", "queries": 1, "rows": 1}}
    org.client.request.return_value = response
    assert cs.resolve_entities([{"value": "web-01"}], at=7, observation_selectors=[DEVICE, HOSTNAME]) == response
    assert json.loads(org.client.request.call_args.kwargs["raw_body"]) == {
        "identifiers": [{"value": "web-01"}], "at": 7, "observation_selectors": [DEVICE, HOSTNAME]}


def test_resolve_omits_selectors_when_none_or_empty(sdk):
    cs, org = sdk
    org.client.request.return_value = {}
    for selectors in (None, [], ()):
        cs.resolve_entities([{"value": "web-01"}], observation_selectors=selectors)
        assert json.loads(org.client.request.call_args.kwargs["raw_body"]) == {
            "identifiers": [{"value": "web-01"}]}


def test_selector_types_and_platforms_are_not_allowlisted_by_the_client(sdk):
    cs, org = sdk
    org.client.request.return_value = {}
    future = [{"type": "future_selector", "platform": "future_platform", "value": "x"}]
    cs.resolve_entities([{"value": "web-01"}], observation_selectors=future)
    assert json.loads(org.client.request.call_args.kwargs["raw_body"])["observation_selectors"] == future


def test_selector_input_is_copied_not_aliased(sdk):
    cs, org = sdk
    org.client.request.return_value = {}
    selector = dict(HOSTNAME)
    cs.resolve_entities([{"value": "web-01"}], observation_selectors=(selector,))
    selector["value"] = "mutated"
    assert json.loads(org.client.request.call_args.kwargs["raw_body"])["observation_selectors"] == [HOSTNAME]


@pytest.mark.parametrize("selectors", [
    [HOSTNAME] * 5,
    "foreign_hostname",
    {"type": "foreign_hostname", "value": "x"},
    ["foreign_hostname"],
    [{"type": "foreign_hostname", "value": "x", "oid": "other"}],
    [{"type": "foreign_hostname"}],
    [{"value": "x"}],
    [{"type": "foreign_hostname", "value": 5}],
    [{"type": "foreign_hostname", "value": ""}],
    [{"type": "foreign_hostname", "value": "   "}],
    [{"type": "foreign_hostname", "value": "x" * 513}],
    [{"type": "foreign_hostname", "value": "中" * 171}],
    [{"type": 1, "value": "x"}],
    [{"type": "", "value": "x"}],
    [{"type": "vendor_device_id", "platform": ["sophos"], "value": "x"}],
    [{"type": "vendor_device_id", "platform": "", "value": "x"}],
    [{"type": "vendor_device_id", "platform": "sophos", "origin_sid": 3, "value": "x"}],
])
def test_invalid_selector_shapes_never_send_http(sdk, selectors):
    cs, org = sdk
    with pytest.raises(ValueError):
        cs.resolve_entities([{"value": "web-01"}], observation_selectors=selectors)
    with pytest.raises(ValueError):
        cs.pivot_entity("web-01", observation_selectors=selectors)
    org.client.request.assert_not_called()


def test_selector_value_at_the_byte_bound_is_accepted(sdk):
    cs, org = sdk
    org.client.request.return_value = {}
    cs.resolve_entities([{"value": "web-01"}],
                        observation_selectors=[{"type": "foreign_hostname", "value": "x" * 512}])
    cs.resolve_entities([{"value": "web-01"}],
                        observation_selectors=[{"type": "foreign_hostname", "value": "中" * 170}])
    assert org.client.request.call_count == 2


def test_selectors_still_obey_the_body_size_limit(sdk):
    cs, org = sdk
    org.client.request.return_value = {}
    identifiers = [{"value": "\x00" * 200}] * 100  # escapes to 6 bytes each in JSON
    cs.resolve_entities(identifiers)  # fits on its own
    org.client.request.reset_mock()
    selectors = [{"type": "foreign_hostname", "value": "\x00" * 512}] * 4
    with pytest.raises(ValueError, match="128 KiB"):
        cs.resolve_entities(identifiers, observation_selectors=selectors)
    org.client.request.assert_not_called()


def test_pivot_forwards_selectors_and_passes_observed_fields_through():
    observed = [{"selector": HOSTNAME, "devices": [{"platform": "crowdstrike"}], "truncated": True}]
    observations = {"status": "incomplete", "reason": "row_bound", "queries": 2, "rows": 20, "truncated": True}
    results = [{"ambiguous": False, "matches": [_match(_id(1))]}]
    cs, calls = _pivot_org({"index_ready": True, "results": results,
                            "observed_matches": observed, "observations": observations})
    out = cs.pivot_entity("web-01", type="hostname", at=9, observation_selectors=[HOSTNAME])
    assert json.loads(cs._org.client.request.call_args_list[0].kwargs["raw_body"]) == {
        "identifiers": [{"value": "web-01", "type": "hostname"}], "at": 9,
        "observation_selectors": [HOSTNAME]}
    assert out["observed_matches"] == observed
    assert out["observations"] == observations
    # Observed leads are never followed: only the confident match is read.
    assert _card_ids(calls) == [_id(1)]
    assert [c["card"]["entity"]["id"] for c in out["cards"]] == [_id(1)]


def test_pivot_without_selectors_sends_no_selector_field():
    cs, calls = _pivot_org({"index_ready": True, "results": []})
    cs.pivot_entity("web-01")
    assert "observation_selectors" not in json.loads(cs._org.client.request.call_args.kwargs["raw_body"])


@pytest.mark.parametrize("verb,method,positional", [
    ("resolve", "resolve_entities", ([{"value": "web-01"}],)),
    ("pivot", "pivot_entity", ("web-01",)),
])
def test_cli_builds_selectors_from_both_flags(verb, method, positional):
    with patch("limacharlie.commands.cloudsec._get_cloudsec") as get_cs:
        getattr(get_cs.return_value, method).return_value = {"observed_matches": []}
        result = CliRunner().invoke(cli, [
            "--output", "json", "cloudsec", "entity", verb, "--identifier", "web-01",
            "--foreign-hostname", "WEB-01", "--foreign-hostname", "web-01.corp",
            "--observation-selector", json.dumps(DEVICE),
            "--observation-selector", '{"type":"future_selector","value":"x"}'])
    assert result.exit_code == 0, result.output
    kwargs = getattr(get_cs.return_value, method).call_args.kwargs
    assert kwargs["observation_selectors"] == [
        {"type": "foreign_hostname", "value": "WEB-01"},
        {"type": "foreign_hostname", "value": "web-01.corp"},
        DEVICE,
        {"type": "future_selector", "value": "x"}]
    assert json.loads(result.output) == {"observed_matches": []}


@pytest.mark.parametrize("verb", ["resolve", "pivot"])
@pytest.mark.parametrize("flags", [
    ["--foreign-hostname", "a", "--foreign-hostname", "b", "--foreign-hostname", "c",
     "--foreign-hostname", "d", "--foreign-hostname", "e"],
    ["--foreign-hostname", "a", "--foreign-hostname", "b", "--foreign-hostname", "c",
     "--observation-selector", json.dumps(DEVICE), "--observation-selector", json.dumps(DEVICE)],
    ["--observation-selector", "not json"],
    ["--observation-selector", '["foreign_hostname"]'],
    ["--observation-selector", '"foreign_hostname"'],
])
def test_cli_rejects_bad_selector_flags_before_any_call(verb, flags):
    with patch("limacharlie.commands.cloudsec._get_cloudsec") as get_cs:
        result = CliRunner().invoke(cli, ["cloudsec", "entity", verb, "--identifier", "web-01"] + flags)
    assert result.exit_code != 0
    get_cs.return_value.resolve_entities.assert_not_called()
    get_cs.return_value.pivot_entity.assert_not_called()


def test_cli_resolve_keeps_identifier_required():
    with patch("limacharlie.commands.cloudsec._get_cloudsec") as get_cs:
        result = CliRunner().invoke(cli, ["cloudsec", "entity", "resolve", "--foreign-hostname", "WEB-01"])
    assert result.exit_code != 0
    get_cs.assert_not_called()


def test_cli_sdk_shape_error_never_sends_http(sdk):
    # The API owns selector types, but a shape error the SDK catches (a
    # non-string value) must fail before any HTTP call.
    cs, org = sdk
    with patch("limacharlie.commands.cloudsec._get_cloudsec", return_value=cs):
        result = CliRunner().invoke(cli, ["cloudsec", "entity", "resolve", "--identifier", "web-01",
                                          "--observation-selector", '{"type":"foreign_hostname","value":3}'])
    assert result.exit_code != 0
    org.client.request.assert_not_called()


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


def test_explain_texts_cover_observed_pivots():
    from limacharlie.discovery import get_explain
    for verb in ("resolve", "pivot"):
        text = get_explain(f"cloudsec.entity.{verb}")
        for needle in ("observed_matches", "insight.evt.get", "--foreign-hostname",
                       "--observation-selector", "sophos", "forbidden", "unavailable", "incomplete"):
            assert needle in text, (verb, needle)
    resolve = get_explain("cloudsec.entity.resolve")
    assert "--type hostname" in resolve and "--identifier stays required" in resolve
    get = get_explain("cloudsec.entity.get")
    for needle in ("also_seen_as", "cloud_sign_ins", "observations", "insight.evt.get",
                   "eh_ Host id", "eu_", "attrs.external", "Chrome"):
        assert needle in get, needle
    for verb in ("resolve", "pivot", "get"):
        text = get_explain(f"cloudsec.entity.{verb}")
        assert "lead" in text.lower(), verb
        assert "verified same" not in text


def test_resolve_and_pivot_help_list_selector_flags():
    for verb in ("resolve", "pivot"):
        result = CliRunner().invoke(cli, ["cloudsec", "entity", verb, "--help"])
        assert result.exit_code == 0
        assert "--foreign-hostname" in result.output and "--observation-selector" in result.output
