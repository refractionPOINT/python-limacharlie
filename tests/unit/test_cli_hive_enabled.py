"""Check CLI metadata intent at the HTTP request boundary."""

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from limacharlie.cli import cli
from limacharlie.errors import ApiError, PermissionDeniedError


@pytest.mark.parametrize("payload", [
    {"data": {"policy_type": "classification", "classification": {}}},
    {"policy_type": "classification", "classification": {}},
])
def test_data_only_leaves_metadata_to_the_hive(payload):
    params = _set_request(payload)
    assert "usr_mtd" not in params
    assert json.loads(params["data"]) == {"policy_type": "classification", "classification": {}}


@pytest.mark.parametrize("metadata,flags,want", [
    ({}, [], {"enabled": False}),
    ({"enabled": None}, [], {"enabled": False}),
    ({"enabled": False}, [], {"enabled": False}),
    ({"enabled": True}, [], {"enabled": True}),
    ({"comment": "staged"}, [], {"enabled": False, "comment": "staged"}),
    ({"enabled": False, "tags": ["draft"]}, ["--enabled"], {"enabled": True, "tags": ["draft"]}),
    ({"enabled": True, "comment": "stage"}, ["--disabled"], {"enabled": False, "comment": "stage"}),
])
def test_explicit_metadata_and_flags_remain_authoritative(metadata, flags, want):
    params = _set_request({"data": {"a": 1}, "usr_mtd": metadata}, flags)
    assert json.loads(params["usr_mtd"]) == want


@pytest.mark.parametrize("flag,want", [("--enabled", True), ("--disabled", False)])
def test_enablement_flag_on_new_record_creates_it_as_asked(flag, want):
    _, posts, result = _set_with_current(
        ApiError("API error (400)", status_code=400, response_body=_NOT_FOUND_BODY), [flag])
    assert result.exit_code == 0, result.output
    assert json.loads(posts[0][2]["usr_mtd"]) == {"enabled": want}
    assert "Warning" not in result.stderr


_NOT_FOUND_BODY = {
    "data": {},
    "error": "lc_error_code:RECORD_NOT_FOUND - record name 'cloudsec_policy:test-oid:policy'",
    "retry": False,
}


def _existing(usr_mtd):
    """The /mtd GET answer for an existing record (data is {} there)."""
    return {"data": {}, "usr_mtd": usr_mtd, "sys_mtd": {"etag": "server-etag"}}


def _set_with_current(current, args, payload=None):
    """Run `hive set` against a server whose /mtd GET answers `current`.

    `current` is a dict (existing record) or an Exception to raise. Returns
    (set_params, result) after checking the metadata read hit /mtd.
    """
    client = MagicMock()
    client.oid = "test-oid"
    calls = []

    def request(verb, url, params=None, **kw):
        calls.append((verb, url, params))
        if verb == "GET":
            if isinstance(current, Exception):
                raise current
            return current
        return {"guid": "test-guid"}

    client.request.side_effect = request
    with patch("limacharlie.commands.hive.Client", return_value=client):
        result = CliRunner(mix_stderr=False).invoke(cli, [
            "hive", "set", "--hive-name", "cloudsec_policy", "--key", "policy", *args,
        ], input=json.dumps(payload if payload is not None else {"data": {"a": 1}}))
    gets = [c for c in calls if c[0] == "GET"]
    posts = [c for c in calls if c[0] == "POST"]
    return gets, posts, result


@pytest.mark.parametrize("flags,want_extra", [
    (["--tag-add", "new"], {"tags": ["old", "new"], "comment": "keep me", "expiry": 123000}),
    (["--tag-rm", "old"], {"tags": [], "comment": "keep me", "expiry": 123000}),
    (["--comment", "changed"], {"tags": ["old"], "comment": "changed", "expiry": 123000}),
    (["--expiry", "0"], {"tags": ["old"], "comment": "keep me", "expiry": 0}),
])
@pytest.mark.parametrize("was_enabled", [True, False])
def test_metadata_flags_with_data_preserve_existing_record(flags, want_extra, was_enabled):
    current = _existing({"enabled": was_enabled, "tags": ["old"], "comment": "keep me", "expiry": 123000})
    gets, posts, result = _set_with_current(current, flags)
    assert result.exit_code == 0, result.output
    assert [g[1] for g in gets] == ["hive/cloudsec_policy/test-oid/policy/mtd"]
    assert len(posts) == 1
    assert posts[0][1] == "hive/cloudsec_policy/test-oid/policy/data"
    sent = json.loads(posts[0][2]["usr_mtd"])
    assert sent == {"enabled": was_enabled, **want_extra}
    assert json.loads(posts[0][2]["data"]) == {"a": 1}
    assert "Warning" not in result.output


def test_metadata_flags_with_data_preserve_ui_actions():
    actions = [{"name": "run", "url": "https://example.invalid"}]
    current = _existing({"enabled": True, "ui_actions": actions})
    _, posts, result = _set_with_current(current, ["--comment", "x"])
    assert result.exit_code == 0, result.output
    assert json.loads(posts[0][2]["usr_mtd"]) == {"enabled": True, "comment": "x", "ui_actions": actions}


def test_metadata_flags_on_new_record_warn_and_create_disabled():
    gets, posts, result = _set_with_current(ApiError("API error (400)", status_code=400, response_body=_NOT_FOUND_BODY), ["--tag-add", "new"])
    assert result.exit_code == 0, result.output
    assert len(gets) == 1
    assert json.loads(posts[0][2]["usr_mtd"]) == {"enabled": False, "tags": ["new"]}
    assert "created DISABLED" in result.stderr
    assert "--enabled" in result.stderr
    assert "created DISABLED" not in result.stdout


@pytest.mark.parametrize("error", [
    ApiError("API error (400)", status_code=400, response_body={"error": "lc_error_code:INVALID_REQUEST - bad"}),
    ApiError("API error (500)", status_code=500, response_body="boom"),
    PermissionDeniedError("Permission denied", code=403),
])
def test_metadata_read_errors_other_than_not_found_propagate(error):
    _, posts, result = _set_with_current(error, ["--tag-add", "new"])
    assert result.exit_code != 0
    assert posts == []


_STORED = {"enabled": True, "tags": ["old"], "comment": "server", "expiry": 5000,
           "ui_actions": [{"name": "run", "url": "https://example.invalid"}]}


@pytest.mark.parametrize("flags,want", [
    (["--disabled"], {**_STORED, "enabled": False}),
    (["--enabled", "--tag-add", "t"], {**_STORED, "tags": ["old", "t"]}),
    (["--disabled", "--comment", "c"], {**_STORED, "enabled": False, "comment": "c"}),
])
def test_enablement_flag_with_data_keeps_other_metadata(flags, want):
    gets, posts, result = _set_with_current(_existing(dict(_STORED)), flags)
    assert result.exit_code == 0, result.output
    assert len(gets) == 1
    assert json.loads(posts[0][2]["usr_mtd"]) == want


def test_enablement_flag_without_metadata_read_permission_sends_flags_with_warning():
    _, posts, result = _set_with_current(
        PermissionDeniedError("Permission denied", code=403), ["--enabled", "--tag-add", "t"])
    assert result.exit_code == 0, result.output
    assert json.loads(posts[0][2]["usr_mtd"]) == {"enabled": True, "tags": ["t"]}
    assert "permission denied" in result.stderr


@pytest.mark.parametrize("usr_mtd", [False, [], "x", 0])
def test_non_mapping_input_metadata_is_refused(usr_mtd):
    gets, posts, result = _set_with_current(
        _existing({"enabled": True}), [], payload={"data": {"a": 1}, "usr_mtd": usr_mtd})
    assert result.exit_code != 0
    assert "usr_mtd must be a mapping" in result.stderr
    assert posts == []


def test_input_metadata_block_keeps_its_ui_actions():
    block = {"enabled": True, "ui_actions": _STORED["ui_actions"]}
    _, posts, result = _set_with_current(
        _existing({"enabled": True}), [], payload={"data": {"a": 1}, "usr_mtd": block})
    assert result.exit_code == 0, result.output
    assert json.loads(posts[0][2]["usr_mtd"]) == block


@pytest.mark.parametrize("usr_mtd,want", [
    ({"enabled": True}, {"enabled": True, "tags": ["t"]}),
    ({"comment": "c"}, {"enabled": False, "comment": "c", "tags": ["t"]}),
])
def test_input_metadata_block_with_flags_is_authoritative_and_not_fetched(usr_mtd, want):
    gets, posts, result = _set_with_current(
        _existing({"enabled": True, "comment": "server"}), ["--tag-add", "t"],
        payload={"data": {"a": 1}, "usr_mtd": usr_mtd})
    assert result.exit_code == 0, result.output
    assert gets == []
    assert json.loads(posts[0][2]["usr_mtd"]) == want


def test_null_input_metadata_block_is_treated_as_absent():
    # A bare `usr_mtd:` in YAML parses to None: same as no block, so the
    # record's current metadata is merged rather than replaced.
    gets, posts, result = _set_with_current(
        _existing({"enabled": True, "comment": "server"}), ["--tag-add", "t"],
        payload={"data": {"a": 1}, "usr_mtd": None})
    assert result.exit_code == 0, result.output
    assert len(gets) == 1
    assert json.loads(posts[0][2]["usr_mtd"]) == {"enabled": True, "comment": "server", "tags": ["t"]}


def test_data_only_set_does_not_read_or_send_metadata():
    gets, posts, result = _set_with_current(_existing({"enabled": True}), [])
    assert result.exit_code == 0, result.output
    assert gets == []
    assert "usr_mtd" not in posts[0][2]


def _shortcut_set(group_args, current, args, payload):
    client = MagicMock()
    client.oid = "test-oid"
    calls = []

    def request(verb, url, params=None, **kw):
        calls.append((verb, url, params))
        if verb == "GET":
            if isinstance(current, Exception):
                raise current
            return current
        return {"guid": "test-guid"}

    client.request.side_effect = request
    with patch("limacharlie.commands._hive_shortcut.Client", return_value=client):
        result = CliRunner(mix_stderr=False).invoke(cli, [
            *group_args, "set", "--key", "k", *args,
        ], input=json.dumps(payload))
    return [c for c in calls if c[0] == "GET"], [c for c in calls if c[0] == "POST"], result


def test_shortcut_tag_and_comment_keep_an_existing_record_enabled():
    current = _existing({"enabled": True, "comment": "old", "expiry": 5000})
    gets, posts, result = _shortcut_set(
        ["app-control", "policy"], current,
        ["--tag", "t", "--comment", "c"], {"data": {"mode": "off"}})
    assert result.exit_code == 0, result.output
    assert [g[1] for g in gets] == ["hive/app_control_policy/test-oid/k/mtd"]
    assert json.loads(posts[0][2]["usr_mtd"]) == {"enabled": True, "tags": ["t"], "comment": "c", "expiry": 5000}


def test_shortcut_value_flag_with_comment_keeps_an_existing_record_disabled():
    current = _existing({"enabled": False})
    _, posts, result = _shortcut_set(["secret"], current, ["--value", "v", "--comment", "c"], {})
    assert result.exit_code == 0, result.output
    assert json.loads(posts[0][2]["usr_mtd"]) == {"enabled": False, "comment": "c"}


def test_shortcut_new_record_with_tag_warns_and_is_created_disabled():
    gets, posts, result = _shortcut_set(
        ["secret"],
        ApiError("API error (400)", status_code=400, response_body=_NOT_FOUND_BODY),
        ["--tag", "t"], {"data": {"secret": "v"}})
    assert result.exit_code == 0, result.output
    assert json.loads(posts[0][2]["usr_mtd"]) == {"enabled": False, "tags": ["t"]}
    assert "created DISABLED" in result.stderr


def test_shortcut_explicit_enabled_keeps_other_metadata():
    gets, posts, result = _shortcut_set(
        ["secret"], _existing({"enabled": False, "tags": ["old"], "comment": "server"}),
        ["--enabled"], {"data": {"secret": "v"}})
    assert result.exit_code == 0, result.output
    assert len(gets) == 1
    assert json.loads(posts[0][2]["usr_mtd"]) == {"enabled": True, "tags": ["old"], "comment": "server"}


def test_shortcut_write_only_key_can_still_set_with_enabled():
    _, posts, result = _shortcut_set(
        ["secret"], PermissionDeniedError("Permission denied", code=403),
        ["--value", "v", "--enabled"], {})
    assert result.exit_code == 0, result.output
    assert json.loads(posts[0][2]["usr_mtd"]) == {"enabled": True}
    assert "permission denied" in result.stderr


def test_shortcut_input_metadata_is_not_fetched():
    gets, posts, result = _shortcut_set(
        ["secret"], _existing({"enabled": False}),
        ["--tag", "t"], {"data": {"secret": "v"}, "usr_mtd": {"enabled": True}})
    assert result.exit_code == 0, result.output
    assert gets == []
    assert json.loads(posts[0][2]["usr_mtd"]) == {"enabled": True, "tags": ["t"]}


@pytest.mark.parametrize("metadata,want", [
    ({}, {"enabled": False}),
    ({"enabled": None}, {"enabled": False}),
    ({"comment": "staged"}, {"enabled": False, "comment": "staged"}),
])
def test_shortcut_input_metadata_without_enabled_means_disabled(metadata, want):
    gets, posts, result = _shortcut_set(
        ["secret"], _existing({"enabled": True}), [], {"data": {"secret": "v"}, "usr_mtd": metadata})
    assert result.exit_code == 0, result.output
    assert gets == []
    assert json.loads(posts[0][2]["usr_mtd"]) == want


def test_shortcut_data_only_set_sends_no_metadata():
    gets, posts, result = _shortcut_set(["secret"], _existing({"enabled": True}), [], {"data": {"secret": "v"}})
    assert result.exit_code == 0, result.output
    assert gets == []
    assert "usr_mtd" not in posts[0][2]


def _set_request(payload, flags=()):
    client = MagicMock()
    client.oid = "test-oid"
    client.request.return_value = {"guid": "test-guid"}
    # Keep the real Organization, HiveRecord and Hive serializers: checking a
    # mocked Hive.set call would not prove whether metadata reaches the API.
    with patch("limacharlie.commands.hive.Client", return_value=client):
        result = CliRunner().invoke(cli, [
            "hive", "set", "--hive-name", "cloudsec_policy", "--key", "policy",
            *flags,
        ], input=json.dumps(payload))
    assert result.exit_code == 0, result.output
    client.request.assert_called_once()
    args, kwargs = client.request.call_args
    assert args == ("POST", "hive/cloudsec_policy/test-oid/policy/data")
    return kwargs["params"]


def _dr_set(current, args, payload):
    client = MagicMock()
    client.oid = "test-oid"
    calls = []

    def request(verb, url, params=None, **kw):
        calls.append((verb, url, params))
        if verb == "GET":
            if isinstance(current, Exception):
                raise current
            return current
        return {"guid": "test-guid"}

    client.request.side_effect = request
    with patch("limacharlie.commands.dr.Client", return_value=client):
        result = CliRunner(mix_stderr=False).invoke(
            cli, ["dr", "set", "--key", "k", *args], input=json.dumps(payload))
    return [c for c in calls if c[0] == "GET"], [c for c in calls if c[0] == "POST"], result


_RULE = {"detect": {"event": "NEW_PROCESS", "op": "exists", "path": "event"}, "respond": [{"action": "report", "name": "x"}]}


@pytest.mark.parametrize("flags,want", [
    (["--tag", "t"], {"enabled": True, "tags": ["t"], "comment": "server"}),
    (["--disabled"], {"enabled": False, "tags": ["old"], "comment": "server"}),
])
def test_dr_set_flags_keep_a_live_rule_metadata(flags, want):
    gets, posts, result = _dr_set(
        _existing({"enabled": True, "tags": ["old"], "comment": "server"}), flags, _RULE)
    assert result.exit_code == 0, result.output
    assert [g[1] for g in gets] == ["hive/dr-general/test-oid/k/mtd"]
    assert json.loads(posts[0][2]["usr_mtd"]) == want


def test_dr_set_tag_on_new_rule_warns_and_creates_it_disabled():
    _, posts, result = _dr_set(
        ApiError("API error (400)", status_code=400, response_body=_NOT_FOUND_BODY), ["--tag", "t"], _RULE)
    assert result.exit_code == 0, result.output
    assert json.loads(posts[0][2]["usr_mtd"]) == {"enabled": False, "tags": ["t"]}
    assert "created DISABLED" in result.stderr


@pytest.mark.parametrize("usr_mtd,flags,want", [
    ({}, [], {"enabled": False}),
    ({"comment": "c"}, ["--tag", "t"], {"enabled": False, "comment": "c", "tags": ["t"]}),
])
def test_dr_set_input_metadata_is_authoritative(usr_mtd, flags, want):
    gets, posts, result = _dr_set(_existing({"enabled": True}), flags, {"data": _RULE, "usr_mtd": usr_mtd})
    assert result.exit_code == 0, result.output
    assert gets == []
    assert json.loads(posts[0][2]["usr_mtd"]) == want


def test_dr_set_null_input_metadata_is_absent():
    gets, posts, result = _dr_set(_existing({"enabled": True}), [], {"data": _RULE, "usr_mtd": None})
    assert result.exit_code == 0, result.output
    assert gets == []
    assert "usr_mtd" not in posts[0][2]
