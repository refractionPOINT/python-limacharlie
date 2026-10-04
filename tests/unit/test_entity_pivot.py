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
    lambda cs: cs.resolve_entities([{"value": "host", "type": "unknown"}]),
    lambda cs: cs.resolve_entities([{"value": "host", "type": []}]),
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
     "resolve_entities", ([{"value": "host", "type": "hostname"}, {"value": "other", "type": "hostname"}],), {"at": 123}),
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
    for verb in ("resolve", "get", "search", "sightings", "activity"):
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
        [{"value": "octo-fixture", "type": "github_login"}], at=None)
