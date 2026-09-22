"""CS-15: the PUBLIC five-rung runtime ladder in the SDK and the CLI.

These tests pin the properties the ladder is FOR, not its shape. Both come from the
plan, not from taste:

* plan 24 §14 — "Decode legacy dormant as not_observed but never emit it"; and
* plan 24 §18 gate 12 — "Runtime negative only on complete window; telemetry lapse
  yields unknown", which on the client side means the SDK must never manufacture a
  negative and must never report an unavailable check as one.

Contract: go-cloudsec ``findings/runtime.go`` + ``runtimeevidence/verdict.go`` (#413,
merged). WIRE shape: the gateway route
``POST /cloudsec/{oid}/findings/{id}/runtime-check`` forwards the graph actor's Data
dict verbatim, so the envelope is ``{"accepted": bool, "runtime": {...} | None}`` with
FLAT per-package rows and the unknown rung rendered as the literal ``"unknown"``
(legion_graph ``runtimePackageWire`` / ``runtimeVerdictWire``).
"""

import re
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from limacharlie.cli import cli
from limacharlie.sdk.cloudsec import (
    RUNTIME_EXECUTING,
    RUNTIME_LOADED,
    RUNTIME_NOT_OBSERVED,
    RUNTIME_PRESENT,
    RUNTIME_REASONS,
    RUNTIME_STATUSES,
    RUNTIME_UNAVAILABLE_REASONS,
    RUNTIME_UNKNOWN,
    RUNTIME_WIRE_UNKNOWN,
    CloudSec,
    decode_runtime_status,
    is_runtime_negative,
    is_runtime_positive,
    runtime_packages,
    runtime_verdict,
)

# The pre-CS-15 spelling. Spelled out here rather than imported: the SDK keeps it
# private precisely because nothing may emit it, so a test that asserts it can never
# come back out must not depend on the SDK exporting it.
_LEGACY = "dormant"


# ---------------------------------------------------------------------------
# The ladder itself
# ---------------------------------------------------------------------------


def test_ladder_is_exactly_the_five_rungs_in_ascending_evidence_order():
    # A sixth rung here without one in go-cloudsec findings.RuntimeStatuses() is how
    # a surface starts claiming something the backend never said.
    assert RUNTIME_STATUSES == ("", "present", "not_observed", "loaded", "executing")
    assert RUNTIME_UNKNOWN == ""
    # …but the wire spells the unknown rung, because an empty string in a JSON enum
    # reads as a missing field rather than as an answer.
    assert RUNTIME_WIRE_UNKNOWN == "unknown"


def test_only_sightings_are_positive_and_only_not_observed_is_negative():
    assert [s for s in RUNTIME_STATUSES if is_runtime_positive(s)] == ["loaded", "executing"]
    assert [s for s in RUNTIME_STATUSES if is_runtime_negative(s)] == ["not_observed"]
    # "not loaded and not executing" is NOT the negative — the inference the helper
    # exists to stop a caller from making.
    assert not is_runtime_negative(RUNTIME_PRESENT)
    assert not is_runtime_negative(RUNTIME_UNKNOWN)


def test_availability_reasons_are_not_part_of_the_verdict_vocabulary():
    # They explain the ABSENCE of a verdict, not a verdict. Conflating them would let
    # "the feature is off" be reported with the authority of a measured answer.
    assert not RUNTIME_UNAVAILABLE_REASONS & RUNTIME_REASONS
    assert "feature_disabled" in RUNTIME_UNAVAILABLE_REASONS


# ---------------------------------------------------------------------------
# The decoder
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("token", [_LEGACY, "DORMANT", "  Dormant  "])
def test_legacy_dormant_decodes_to_not_observed(token):
    assert decode_runtime_status(token) == (RUNTIME_NOT_OBSERVED, True)


def test_the_legacy_token_appears_in_the_sdk_only_as_the_private_decode_constant():
    """Structural, not behavioural: nowhere in the SDK can produce the legacy token.

    A behavioural sweep only proves the callers it happens to exercise. This reads the
    module source and asserts the string exists in exactly one place — the private
    constant the decoder compares against — so a future caller that tried to emit it
    would have to add an occurrence and fail here.
    """
    import inspect

    from limacharlie.sdk import cloudsec as module

    source = inspect.getsource(module)
    occurrences = [
        line.strip() for line in source.splitlines()
        if f'"{_LEGACY}"' in line or f"'{_LEGACY}'" in line
    ]
    assert occurrences == [f'_LEGACY_RUNTIME_NOT_OBSERVED = "{_LEGACY}"'], occurrences


def test_the_legacy_token_can_never_be_emitted():
    # Plan §14: decode it, never emit it. Swept over the whole token space rather than
    # by inspecting one caller; see the structural check above for the other half.
    assert _LEGACY not in RUNTIME_STATUSES
    for token in list(RUNTIME_STATUSES) + [_LEGACY, "", None, "sixth_rung", 7, True, [], {}]:
        status, _ = decode_runtime_status(token)
        assert status != _LEGACY
        assert status in RUNTIME_STATUSES
    # And neither reader can smuggle it out of a whole response.
    wire = _response(_row("deb|openssl|3.0.2", _LEGACY, "complete_window"), status=_LEGACY)
    assert runtime_verdict(wire)["status"] == RUNTIME_NOT_OBSERVED
    assert runtime_packages(wire)[0]["status"] == RUNTIME_NOT_OBSERVED


@pytest.mark.parametrize("token", ["unknown", "UNKNOWN", "  Unknown  "])
def test_the_rendered_unknown_spelling_is_recognised(token):
    # THIS IS WHAT A LIVE RESPONSE CARRIES. findings.WireRuntimeStatus renders the
    # unknown rung as the literal token, so treating it as malformed would fire the
    # "this build does not understand the backend" signal on the most common answer
    # there is — and, in a reader that reacted to it, discard the verdict's reason.
    assert decode_runtime_status(token) == (RUNTIME_UNKNOWN, True)


@pytest.mark.parametrize("token", [None, "", "   "])
def test_absent_or_empty_status_is_also_unknown(token):
    # Go's zero value. Both spellings must decode or the round trip is not total.
    status, recognized = decode_runtime_status(token)
    assert status == RUNTIME_UNKNOWN
    assert recognized is True


@pytest.mark.parametrize("token", ["sixth_rung", "not observed", "safe", 7, [], {}])
def test_an_unrecognised_token_is_unknown_and_is_reported_as_unrecognised(token):
    # A token a newer backend invented must not be rendered as one of ours — and above
    # all must not land on the negative rung. `recognized` lets a caller COUNT that
    # instead of silently reading it as unknown.
    status, recognized = decode_runtime_status(token)
    assert status == RUNTIME_UNKNOWN
    assert recognized is False


@pytest.mark.parametrize("rung", [s for s in RUNTIME_STATUSES if s])
def test_every_rung_folds_through_unchanged_case_insensitively(rung):
    assert decode_runtime_status(rung) == (rung, True)
    assert decode_runtime_status(rung.upper()) == (rung, True)


# ---------------------------------------------------------------------------
# Reading the SERVER's verdict — the wire envelope
# ---------------------------------------------------------------------------


def _row(key, status, reason="", **extra):
    """One FLAT per-package row, exactly as legion_graph runtimeVerdictWire emits it."""
    row = {"key": key, "status": status, "reason": reason, "level": "derived", "source": "endpoint_runtime_package"}
    row.update(extra)
    return row


def _response(*rows, status="present", reason="window_short", accepted=True, **runtime):
    """The full envelope: {"accepted": ..., "runtime": {...}} with the headline on top."""
    payload = {
        "resource_urn": "lcrn:cloud:gcp:proj:instance/vm-1",
        "status": status,
        "reason": reason,
        "level": "derived",
        "source": "endpoint_runtime_package",
        "sensors": 1,
        "sensors_complete": True,
        "complete": True,
        "checked_at": "2026-09-22T20:00:00Z",
        "packages": list(rows),
    }
    payload.update(runtime)
    return {"accepted": accepted, "runtime": payload}


def test_the_verdict_is_read_from_the_servers_headline_not_re_derived():
    # The backend computes CheckResult.Headline() and puts it at the top of `runtime`.
    # This is the whole point: the per-package rows below say something different, and a
    # client that folded them itself would have to get the negative-veto right forever.
    wire = _response(
        _row("deb|openssl|3.0.2", RUNTIME_EXECUTING, "observed_executing"),
        _row("deb|zlib1g|1.2.11", RUNTIME_NOT_OBSERVED, "complete_window"),
        status=RUNTIME_PRESENT,
        reason="telemetry_absent",
    )
    verdict = runtime_verdict(wire)
    assert verdict["status"] == RUNTIME_PRESENT
    assert verdict["reason"] == "telemetry_absent"
    assert verdict["source"] == "endpoint_runtime_package"
    assert verdict["resource_urn"] == "lcrn:cloud:gcp:proj:instance/vm-1"


def test_the_rendered_unknown_rung_survives_the_envelope_with_its_reason_intact():
    wire = _response(status=RUNTIME_WIRE_UNKNOWN, reason="inventory_conflict", level="unknown")
    verdict = runtime_verdict(wire)
    assert verdict["status"] == RUNTIME_UNKNOWN
    assert verdict["status_recognized"] is True
    # The reason is the only thing that makes an unknown actionable. Losing it — by
    # treating the rendered token as malformed and overwriting the reason — would be
    # the quiet failure here.
    assert verdict["reason"] == "inventory_conflict"
    assert verdict["reason"] in RUNTIME_REASONS


def test_an_unavailable_check_is_reported_as_not_run_and_never_as_a_negative():
    # The feature is DEFAULT-OFF, so this is the answer for most orgs today. It must not
    # read as "nothing ran".
    wire = {
        "accepted": False,
        "runtime": {
            "status": RUNTIME_WIRE_UNKNOWN,
            "reason": "feature_disabled",
            "level": "unknown",
            "sensors": 0,
            "sensors_complete": False,
            "complete": False,
        },
    }
    verdict = runtime_verdict(wire)
    assert verdict["accepted"] is False
    assert verdict["status"] == RUNTIME_UNKNOWN
    assert not is_runtime_negative(verdict["status"])
    assert verdict["reason"] == "feature_disabled"
    assert verdict["reason"] in RUNTIME_UNAVAILABLE_REASONS
    assert verdict["sensors_complete"] is False


def test_an_unknown_finding_id_yields_a_null_runtime_and_still_reads_as_unknown():
    verdict = runtime_verdict({"accepted": False, "runtime": None})
    assert verdict["status"] == RUNTIME_UNKNOWN
    assert verdict["accepted"] is False
    assert not is_runtime_negative(verdict["status"])


def test_an_immature_window_reports_the_retry_the_server_stated_in_seconds():
    # Asking is what STARTS the measurement, so a cold first call is expected to be
    # inconclusive. The field is retry_after_seconds — an int number of seconds, not a
    # Go duration in nanoseconds.
    wire = _response(complete=False, retry_after_seconds=241)
    verdict = runtime_verdict(wire)
    assert verdict["complete"] is False
    assert verdict["retry_after_seconds"] == 241


def test_a_settled_answer_carries_no_retry():
    assert runtime_verdict(_response())["retry_after_seconds"] is None


@pytest.mark.parametrize("wire", [{}, None, {"runtime": {}}, {"accepted": True}])
def test_a_malformed_or_empty_envelope_reads_as_unknown_and_not_accepted(wire):
    verdict = runtime_verdict(wire)
    assert verdict["status"] == RUNTIME_UNKNOWN
    assert not is_runtime_negative(verdict["status"])
    assert verdict["level"] == "unknown"


def test_the_reader_does_not_overwrite_the_servers_reason_for_an_unreadable_status():
    # `no_evidence` means "no summary exists for this sensor". Stamping it here would
    # assert a coverage fact nobody established, and would destroy what the server said.
    wire = _response(status="sixth_rung", reason="relevance_truncated")
    verdict = runtime_verdict(wire)
    assert verdict["status"] == RUNTIME_UNKNOWN
    assert verdict["status_recognized"] is False
    assert verdict["reason"] == "relevance_truncated"


# ---------------------------------------------------------------------------
# The per-package rows
# ---------------------------------------------------------------------------


def test_rows_are_read_flat_and_keep_every_field_the_server_stated():
    wire = _response(
        _row(
            "deb|openssl|3.0.2",
            RUNTIME_LOADED,
            "observed_loaded",
            ecosystem="deb",
            package="openssl",
            version="3.0.2",
            observed_at="2026-09-22T19:50:00Z",
            stale_at="2026-09-22T20:05:00Z",
            paths=["/usr/lib/x86_64-linux-gnu/libssl.so.3"],
        )
    )
    rows = runtime_packages(wire)
    assert len(rows) == 1
    assert rows[0]["status"] == RUNTIME_LOADED
    # Rows are FLAT on the wire (no nested "verdict"); every stated field survives.
    for field in ("key", "reason", "level", "source", "ecosystem", "package", "version",
                  "observed_at", "stale_at", "paths"):
        assert field in rows[0], field
    assert rows[0]["paths"] == ["/usr/lib/x86_64-linux-gnu/libssl.so.3"]


def test_rows_decode_the_rendered_unknown_and_the_legacy_token():
    rows = runtime_packages(_response(
        _row("deb|a|1", RUNTIME_WIRE_UNKNOWN, "unversioned"),
        _row("deb|b|1", _LEGACY, "complete_window"),
    ))
    assert [r["status"] for r in rows] == [RUNTIME_UNKNOWN, RUNTIME_NOT_OBSERVED]
    assert rows[0]["reason"] == "unversioned"


def test_rows_tolerate_a_malformed_payload_without_reading_it_as_a_verdict():
    wire = {"accepted": True, "runtime": {"packages": [None, "x", {}, _row("deb|a|1", RUNTIME_PRESENT)]}}
    rows = runtime_packages(wire)
    assert [r["status"] for r in rows] == [RUNTIME_UNKNOWN, RUNTIME_PRESENT]
    assert not any(is_runtime_negative(r["status"]) for r in rows)
    assert runtime_packages({}) == []
    assert runtime_packages({"runtime": None}) == []


def test_the_reader_does_not_mutate_the_callers_response():
    row = _row("deb|a|1", RUNTIME_WIRE_UNKNOWN, "unversioned")
    wire = _response(row)
    runtime_packages(wire)
    # The caller may still want the raw wire value; decoding in place would take it.
    assert row["status"] == RUNTIME_WIRE_UNKNOWN


# ---------------------------------------------------------------------------
# The transport
# ---------------------------------------------------------------------------


def test_check_finding_runtime_posts_the_documented_route_and_returns_it_verbatim():
    org = MagicMock()
    org.oid = "b85fd2bd-ae21-4c1f-8a42-b90b51aeddeb"
    payload = _response(_row("deb|openssl|3.0.2", RUNTIME_PRESENT, "window_short"),
                        complete=False, retry_after_seconds=241)
    org.client.request.return_value = payload

    result = CloudSec(org).check_finding_runtime("fnd_0123abcd")

    assert org.client.request.call_count == 1
    call = org.client.request.call_args
    assert call.args[0] == "POST"
    assert call.args[1] == f"cloudsec/{org.oid}/findings/fnd_0123abcd/runtime-check"
    # The body stays EMPTY. Plan §9: every target is derived from the finding id
    # server-side, so a caller must not be able to name a sensor, a resource or a
    # package — and the only way to keep that true from here is to send nothing.
    assert call.kwargs["raw_body"] == b"{}"
    assert call.kwargs["content_type"] == "application/json"
    # Passed through with nothing reinterpreted: the SDK must not "helpfully" turn an
    # unsettled answer into a settled one.
    assert result is payload


def test_a_finding_id_is_path_escaped_rather_than_widening_the_route():
    org = MagicMock()
    org.oid = "b85fd2bd-ae21-4c1f-8a42-b90b51aeddeb"
    org.client.request.return_value = {}
    CloudSec(org).check_finding_runtime("fnd_a/../b")
    assert (
        org.client.request.call_args.args[1]
        == f"cloudsec/{org.oid}/findings/fnd_a%2F..%2Fb/runtime-check"
    )


# ---------------------------------------------------------------------------
# The CLI surface
# ---------------------------------------------------------------------------


# Phrases with NO honest use in this copy. This list is deliberately short, because most
# of the loaded words are context-dependent: "the finding is fixed" and "not exploitable"
# both appear in the sentence that makes the copy honest ("not that the package is gone,
# that the finding is fixed, or that the vulnerability is not exploitable"), so banning
# them outright would forbid the fix. Only constructions that cannot be part of a denial
# are listed.
_SAFETY_CLAIMS = (
    "proves safe", "no risk", "safe to ignore", "no action needed",
    "is remediated", "treat it as remediated", "effectively fixed",
    "nothing further is required", "not affected", "is not vulnerable",
    "false positive", "you may close", "can be closed", "proves the vulnerability",
)

# A proof claim about exploitability is allowed only when the negation comes BEFORE the
# verb — "nothing here proves anything about exploitability" passes, "proves the CVE is
# exploitable, nothing else does" does not. Matching the negation anywhere in the clause
# would not work: a dishonest sentence usually contains one somewhere else.
_NEGATED_PROVE = re.compile(r"\b(?:nothing|not|never|cannot|no)\b[^.]{0,40}?prove")


def _affirms_no_safety(text: str) -> None:
    """Assert the text never AFFIRMS safety, while allowing it to deny safety.

    WHAT THIS CANNOT DO. A keyword check cannot decide in general whether prose affirms
    or denies — that is the same over-claim this whole package is about. The first
    version of this helper tried, with `assert "not" in clause`, and was satisfied by
    accident in almost any sentence because the copy is saturated with the token
    `not_observed` and because `nothing`/`cannot`/`another` all contain "not".

    So it asserts only two things it can assert soundly, and the callers add the part
    with the most teeth: that the required denials are actually PRESENT. Silence is the
    other way this copy goes wrong, and no ban list catches that.
    """
    lowered = text.lower()
    for claim in _SAFETY_CLAIMS:
        assert claim not in lowered, claim
    for clause in lowered.replace("\n", " ").split("."):
        if "exploit" in clause and "prove" in clause:
            assert _NEGATED_PROVE.search(clause), clause


def test_the_guard_rejects_dishonest_copy():
    """Test the test. A guard nothing can fail is not a guard.

    Every sample below PASSED the first version of this helper. Three carry a banned
    construction; the fourth is the one that motivated the negation-before-the-verb rule,
    because its negation ("nothing else does") sits after the claim it does not soften.
    """
    for sample in [
        "not_observed proves the vulnerability is not exploitable and the finding is fixed.",
        "Nothing further is required; treat it as remediated and close the finding.",
        "A not_observed rung means the finding is effectively fixed.",
        "An executing rung proves the CVE is exploitable, nothing else does.",
    ]:
        with pytest.raises(AssertionError):
            _affirms_no_safety(sample)

    # …and it accepts the real copy's shape, so it is not merely rejecting everything.
    _affirms_no_safety(
        "not_observed says a complete window did not see the code run - not that the "
        "package is gone, that the finding is fixed, or that the vulnerability is not "
        "exploitable. Nothing here proves anything about exploitability."
    )


# The denials each surface must actually CONTAIN. The ban list above catches an
# overclaim; only this catches silence, which is the other way the copy goes wrong.
_REQUIRED_DENIALS = (
    "not that the package is gone",
    "that the finding is fixed",
    "that the vulnerability is not exploitable",
    "proves anything about exploitability",
)


def _denials_present(text: str) -> None:
    """Assert every required denial is present, ignoring line wrapping.

    Whitespace is collapsed first: click and the explain text both hard-wrap, so a
    phrase like "the finding is\nfixed" is the same statement and must not fail here.
    """
    flat = " ".join(text.lower().split())
    for denial in _REQUIRED_DENIALS:
        assert " ".join(denial.split()) in flat, denial


def _invoke_runtime_check(args, response):
    """Run the real CLI command with a mocked CloudSec, the way the other verbs are tested.

    This is the test that would have caught the first version of this change: the command
    was only ever exercised through --help, so a projection written against the wrong
    response shape composed fine and answered nonsense.
    """
    from unittest.mock import patch

    with patch("limacharlie.commands.cloudsec.Client"), \
            patch("limacharlie.commands.cloudsec.Organization"), \
            patch("limacharlie.commands.cloudsec.CloudSec") as cls:
        inst = MagicMock()
        cls.return_value = inst
        inst.check_finding_runtime.return_value = response
        result = CliRunner().invoke(cli, ["--output", "json"] + args)
    return result, inst


def test_cli_runtime_check_delegates_to_the_sdk_and_prints_the_whole_response():
    response = _response(_row("deb|openssl|3.0.2", RUNTIME_EXECUTING, "observed_executing"),
                         status=RUNTIME_EXECUTING, reason="observed_executing")
    result, inst = _invoke_runtime_check(["cloudsec", "finding", "runtime-check", "fnd_abc"], response)
    assert result.exit_code == 0, result.output
    inst.check_finding_runtime.assert_called_once_with("fnd_abc")
    assert "accepted" in result.output
    assert "observed_executing" in result.output


def test_cli_verdict_projection_reports_the_rung_the_server_stated():
    # The regression this pins: a projection written against the wrong envelope shape
    # finds no rows and answers "unknown" for a resource whose package is EXECUTING.
    response = _response(_row("deb|openssl|3.0.2", RUNTIME_EXECUTING, "observed_executing"),
                         status=RUNTIME_EXECUTING, reason="observed_executing")
    result, _ = _invoke_runtime_check(
        ["cloudsec", "finding", "runtime-check", "fnd_abc", "--verdict"], response)
    assert result.exit_code == 0, result.output
    assert RUNTIME_EXECUTING in result.output
    assert "sensors_partial" not in result.output


def test_cli_packages_projection_prints_the_flat_rows_with_statuses_decoded():
    response = _response(_row("deb|openssl|3.0.2", _LEGACY, "complete_window"))
    result, _ = _invoke_runtime_check(
        ["cloudsec", "finding", "runtime-check", "fnd_abc", "--packages"], response)
    assert result.exit_code == 0, result.output
    assert RUNTIME_NOT_OBSERVED in result.output
    assert _LEGACY not in result.output


def test_cli_verdict_projection_reports_a_disabled_feature_as_not_run():
    response = {"accepted": False, "runtime": {"status": RUNTIME_WIRE_UNKNOWN,
                                               "reason": "feature_disabled",
                                               "level": "unknown"}}
    result, _ = _invoke_runtime_check(
        ["cloudsec", "finding", "runtime-check", "fnd_abc", "--verdict"], response)
    assert result.exit_code == 0, result.output
    assert "feature_disabled" in result.output
    assert RUNTIME_NOT_OBSERVED not in result.output


def test_cli_help_states_that_the_negative_rung_is_not_a_safety_claim():
    runner = CliRunner()
    result = runner.invoke(cli, ["cloudsec", "finding", "runtime-check", "--help"])
    assert result.exit_code == 0
    text = result.output
    assert "not_observed" in text
    assert "COMPLETE telemetry window" in text
    assert "Informational only" in text
    # A first call is expected to be inconclusive; saying so is what stops an immature
    # window being reported as a finished answer.
    assert "retry_after_seconds" in text
    assert "feature_disabled" in text
    _denials_present(text)
    _affirms_no_safety(text)


def test_explain_documents_all_five_rungs_the_veto_and_the_default_off_feature():
    # `explain` text is the agent-facing surface (limacharlie help discover / explain),
    # registered from the command module, so it is read through the registry rather than
    # through a top-level CLI verb, which does not exist.
    from limacharlie.discovery import get_explain

    text = get_explain("cloudsec.finding.runtime-check")
    assert text, "the command must be discoverable via explain"
    for rung in ["present", "not_observed", "loaded", "executing", "unknown"]:
        assert rung in text, rung
    # The reason --verdict is a field read rather than a local fold.
    assert "veto" in text
    assert "DEFAULT-OFF" in text
    assert "not a safety claim" in text.lower()
    # Silence is the other way this copy goes wrong, so the denials must be PRESENT.
    _denials_present(text)
    _affirms_no_safety(text)


def test_cli_rejects_asking_for_two_different_projections_at_once():
    runner = CliRunner()
    result = runner.invoke(cli, ["cloudsec", "finding", "runtime-check", "fnd_a",
                                 "--verdict", "--packages"])
    assert result.exit_code != 0
    assert "at most one" in result.output
