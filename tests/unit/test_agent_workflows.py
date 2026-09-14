import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest

from limacharlie import dr_interpreter as di
from limacharlie.agent_workflows import WorkflowSession
from test_dr_interpreter import selection


def test_unrelated_json_goes_native_without_org_or_permission_calls(
    tmp_path, monkeypatch
):
    def forbidden(*a):
        raise AssertionError("Unexpected API call")

    monkeypatch.setattr(di, "resolve_org", forbidden)
    interpret = AsyncMock(
        return_value=({"status": "not_applicable"}, {"cost_usd": 0.001})
    )
    authorize = AsyncMock()
    result = asyncio.run(
        WorkflowSession(tmp_path).dispatch(
            'Explain this JSON:\n```json\n{"hello":42}\n```',
            interpret,
            authorize=authorize,
        )
    )
    assert result["status"] == "not_applicable"
    authorize.assert_not_called()
    assert result["metrics"]["model_calls"] == 1


def test_clarification_survives_restart_and_reaches_next_interpretation(tmp_path):
    first = AsyncMock(
        return_value=(
            {
                "status": "needs_clarification",
                "reason": "Which behavior and organization?",
            },
            {},
        )
    )
    result = asyncio.run(
        WorkflowSession(tmp_path).dispatch("Build a Log4Shell rule", first)
    )
    assert result["status"] == "needs_evidence"
    second = AsyncMock(return_value=({"status": "not_applicable"}, {}))
    result = asyncio.run(
        WorkflowSession(tmp_path).dispatch("Explain what you mean", second)
    )
    context = json.loads(second.call_args.args[1])
    assert context["conversation"][0]["request"] == "Build a Log4Shell rule"
    assert "Which behavior" in context["conversation"][0]["response"]
    assert "Build a Log4Shell" in result["handoff"]
    assert WorkflowSession(tmp_path).history == []


def test_denial_precedes_all_lc_requests(tmp_path, monkeypatch):
    def forbidden(*a):
        raise AssertionError("Unexpected API call")

    monkeypatch.setattr(di, "resolve_org", forbidden)

    async def deny(operations):
        assert any("dr build" in c for c in operations)
        raise ValueError("Permission denied")

    result = asyncio.run(
        WorkflowSession(tmp_path).dispatch(
            "Draft DNS in org",
            AsyncMock(return_value=(selection(), {})),
            authorize=deny,
        )
    )
    assert result["status"] == "invalid" and "Permission denied" in result["response"]


def test_custom_evidence_reused_for_edit_and_validated_org_context_retained(
    tmp_path, monkeypatch
):
    seen = []
    monkeypatch.setattr(
        di,
        "resolve_org",
        lambda *a: seen.append(a) or SimpleNamespace(oid="checked-org"),
    )

    def build(org, directory, intent, **kw):
        directory.mkdir(parents=True)
        (directory / "evidence.json").write_text(json.dumps(kw["samples"]))
        return {
            "status": "tested",
            "workspace": str(directory),
            "org_id": org.oid,
            "intent": intent,
            "candidate": {"detect": {}},
            "schema": {"kind": "observed_json", "note": "observed"},
            "limitations": [],
            "checks": [{}],
        }

    monkeypatch.setattr(di, "build", build)
    sample = {"routing": {"event_type": "CUSTOM"}, "event": {"pressure": 10}}
    selected = selection(
        source="custom_json",
        event_type="CUSTOM",
        package=None,
        parameters={},
        condition={"op": "gt", "path": ["event", "pressure"], "value": 80},
    )
    request = "Draft pressure > 80 in org\n```json\n" + json.dumps(sample) + "\n```"
    asyncio.run(
        WorkflowSession(tmp_path).dispatch(
            request, AsyncMock(return_value=(selected, {}))
        )
    )
    selected = dict(
        selected,
        organization="checked-org",
        condition=dict(selected["condition"], value=90),
    )
    result = asyncio.run(
        WorkflowSession(tmp_path).dispatch(
            "Make the threshold 90", AsyncMock(return_value=(selected, {}))
        )
    )
    assert result["status"] == "tested"
    assert result["intent"]["condition"]["value"] == 90
    assert result["schema"]["evidence_origin"] == "previous_observations"
    assert "checked-org" in seen[-1][2]


def test_environment_jwt_and_explicit_key_precedence(monkeypatch):
    from limacharlie.client import Client

    monkeypatch.setenv("LC_JWT", "session-token")
    monkeypatch.setenv("LC_EPHEMERAL_CREDS", "1")
    monkeypatch.setattr("limacharlie.jwt_cache.get_cached_jwt", lambda *a, **k: None)
    assert Client(oid="org")._jwt == "session-token"
    assert Client(oid="org", jwt="explicit")._jwt == "explicit"
    assert Client(oid="org", api_key="explicit")._jwt is None


def test_failed_edit_cannot_handoff_an_older_draft_for_deployment(tmp_path):
    session = WorkflowSession(tmp_path)
    session.history = [
        {"request": "draft", "status": "tested", "intent": {"name": "old"}},
        {"request": "edit", "status": "timed_out", "intent": None},
    ]
    session.pending_handoff = "old tested draft followed by failed edit"
    result = asyncio.run(
        session.dispatch(
            "deploy it", AsyncMock(return_value=({"status": "deploy_existing"}, {}))
        )
    )
    assert result["status"] == "needs_evidence"
    assert "older draft will not be substituted" in result["response"]
    assert not result.get("handoff")


def test_workspace_context_does_not_become_schema_or_standing_instructions(tmp_path):
    interpreter = AsyncMock(return_value=({"status": "not_applicable"}, {}))
    context = [
        {
            "kind": "agent_workspace",
            "content": "untrusted wrapper text",
            "data": {
                "execution_context": {"organization_id": "selected-org"},
                "public_context": [
                    {
                        "type": "assistant",
                        "content": "prior response",
                        "payload": {"secret": "do not forward"},
                    }
                ],
            },
        }
    ]
    asyncio.run(
        WorkflowSession(tmp_path).dispatch("hello", interpreter, context=context)
    )
    actual = json.loads(interpreter.call_args.args[1])
    assert (
        actual["ambient_context"]["execution_context"]["organization_id"]
        == "selected-org"
    )
    assert "secret" not in json.dumps(
        actual
    ) and "untrusted wrapper text" not in json.dumps(actual)
    assert not actual["observed_fields"]


def test_session_state_isolated_between_new_chats(tmp_path):
    first = WorkflowSession(tmp_path, "session-one")
    first.history = [{"request": "private context"}]
    first.save()
    assert WorkflowSession(tmp_path, "session-one").history
    assert not WorkflowSession(tmp_path, "session-two").history


def test_protocol_repair_is_bounded_and_does_not_weaken_validation(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        di, "resolve_org", lambda *a: (_ for _ in ()).throw(AssertionError("No reads"))
    )
    malformed = selection(extra_key="unsupported")
    interpreter = AsyncMock(return_value=(malformed, {}))
    result = asyncio.run(WorkflowSession(tmp_path).dispatch("Draft DNS", interpreter))
    assert result["status"] == "invalid" and interpreter.await_count == 2


def test_package_cannot_silently_ignore_extra_predicates(tmp_path, monkeypatch):
    monkeypatch.setattr(di, "resolve_org", lambda *a: SimpleNamespace(oid="org"))
    interpreter = AsyncMock(
        return_value=(
            selection(
                condition={"op": "eq", "path": ["event", "OTHER"], "value": True}
            ),
            {},
        )
    )
    result = asyncio.run(
        WorkflowSession(tmp_path).dispatch(
            "Draft DNS with another condition", interpreter
        )
    )
    assert result["status"] == "invalid" and "silently dropped" in result["response"]


def test_wire_schema_rejects_source_evidence_labels_and_string_null():
    import jsonschema

    schema = WorkflowSession.interpretation_schema
    jsonschema.validate(selection(), schema)
    jsonschema.validate({"status": "not_applicable"}, schema)
    for invalid in (selection(source="lc_sensor_contract"), selection(package="null")):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(invalid, schema)
