"""CS-15: the PUBLIC five-rung runtime ladder in the SDK and the CLI.

These tests exist to pin the two properties the ladder is FOR, not to restate its
shape. Both come from the plan, not from taste:

* plan 24 §14 — "Decode legacy dormant as not_observed but never emit it"; and
* plan 24 §18 gate 12 — "Runtime negative only on complete window; telemetry lapse
  yields unknown", which at this grain means no fold over incomplete input may ever
  produce ``not_observed``.

Authority for the contract: go-cloudsec ``findings/runtime.go`` +
``runtimeevidence/verdict.go`` (PR refractionPOINT/go-cloudsec#413).
"""

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
    RUNTIME_UNKNOWN,
    CloudSec,
    decode_runtime_status,
    is_runtime_negative,
    is_runtime_positive,
    runtime_headline,
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


def test_only_sightings_are_positive_and_only_not_observed_is_negative():
    assert [s for s in RUNTIME_STATUSES if is_runtime_positive(s)] == ["loaded", "executing"]
    assert [s for s in RUNTIME_STATUSES if is_runtime_negative(s)] == ["not_observed"]
    # "not loaded and not executing" is NOT the negative rung — the inference the
    # helper exists to stop a caller from making.
    assert not is_runtime_negative(RUNTIME_PRESENT)
    assert not is_runtime_negative(RUNTIME_UNKNOWN)


# ---------------------------------------------------------------------------
# The legacy token
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("token", ["dormant", "DORMANT", "  Dormant  "])
def test_legacy_dormant_decodes_to_not_observed(token):
    assert decode_runtime_status(token) == (RUNTIME_NOT_OBSERVED, True)


def test_the_legacy_token_can_never_be_emitted():
    # Plan §14: decode it, never emit it. There is no code path that produces it, so
    # the guarantee is checked structurally rather than by inspecting one caller.
    assert _LEGACY not in RUNTIME_STATUSES
    for token in list(RUNTIME_STATUSES) + ["dormant", "", None, "sixth_rung", 7]:
        status, _ = decode_runtime_status(token)
        assert status != _LEGACY
        assert status in RUNTIME_STATUSES
    # And a whole fold cannot smuggle it out either.
    folded = runtime_headline({
        "packages": [{"key": "deb|openssl|3.0.2", "verdict": {"status": "dormant"}}],
        "sensors_complete": True,
    })
    assert folded["status"] == RUNTIME_NOT_OBSERVED


@pytest.mark.parametrize("token", [None, "", "   "])
def test_absent_or_empty_status_is_unknown_not_a_verdict(token):
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
# The fold: no negative from incomplete input
# ---------------------------------------------------------------------------


def _row(key, status, reason=""):
    return {"key": key, "verdict": {"status": status, "reason": reason, "level": "derived"}}


def test_empty_result_is_unknown_and_says_which_kind_of_nothing_it_is():
    assert runtime_headline({"packages": [], "sensors_complete": True}) == {
        "status": RUNTIME_UNKNOWN, "reason": "no_evidence", "level": "unknown",
    }
    # A partial sensor enumeration is a DIFFERENT nothing, and the reason says so.
    assert runtime_headline({"packages": [], "sensors_complete": False})["reason"] == "sensors_partial"
    assert runtime_headline({})["reason"] == "sensors_partial"


def test_a_partial_sensor_set_vetoes_a_unanimous_negative():
    # §18 gate 12 at the resource grain: the negative needs a complete window AND a
    # complete sensor enumeration. Without the second one the honest answer is unknown.
    result = {
        "packages": [_row("deb|openssl|3.0.2", RUNTIME_NOT_OBSERVED, "complete_window")],
        "sensors_complete": False,
    }
    folded = runtime_headline(result)
    assert folded["status"] == RUNTIME_UNKNOWN
    assert folded["reason"] == "sensors_partial"


def test_one_incomplete_package_vetoes_a_whole_resource_negative():
    # THE REASON runtime_headline EXISTS. A naive max over the rungs would return
    # not_observed here, because the negative outranks nothing. The real ranking puts
    # the negative BELOW present precisely so this veto works.
    result = {
        "packages": [
            _row("deb|openssl|3.0.2", RUNTIME_NOT_OBSERVED, "complete_window"),
            _row("deb|zlib1g|1.2.11", RUNTIME_PRESENT, "telemetry_absent"),
        ],
        "sensors_complete": True,
    }
    folded = runtime_headline(result)
    assert folded["status"] == RUNTIME_PRESENT
    assert folded["reason"] == "telemetry_absent"


def test_one_unknown_sibling_also_vetoes_the_negative():
    result = {
        "packages": [
            _row("deb|openssl|3.0.2", RUNTIME_NOT_OBSERVED, "complete_window"),
            _row("deb|libxml2|2.9.13", RUNTIME_UNKNOWN, "inventory_conflict"),
        ],
        "sensors_complete": True,
    }
    folded = runtime_headline(result)
    assert not is_runtime_negative(folded["status"])
    assert folded["status"] == RUNTIME_UNKNOWN


def test_a_unanimous_negative_over_a_complete_sensor_set_survives():
    # The negative is reachable — it just has to be earned. A fold that could NEVER
    # return it would make the rung decorative and hide a real regression.
    result = {
        "packages": [
            _row("deb|openssl|3.0.2", RUNTIME_NOT_OBSERVED, "complete_window"),
            _row("deb|zlib1g|1.2.11", RUNTIME_NOT_OBSERVED, "complete_window"),
        ],
        "sensors_complete": True,
    }
    folded = runtime_headline(result)
    assert folded["status"] == RUNTIME_NOT_OBSERVED
    assert folded["reason"] == "complete_window"


@pytest.mark.parametrize("sighting", [RUNTIME_LOADED, RUNTIME_EXECUTING])
def test_a_sighting_on_any_package_is_the_answer(sighting):
    # Incomplete evidence can hide a sighting; it cannot invent one. So a positive
    # needs no completeness precondition — not even a complete sensor set.
    result = {
        "packages": [
            _row("deb|zlib1g|1.2.11", RUNTIME_NOT_OBSERVED, "complete_window"),
            _row("deb|openssl|3.0.2", sighting, "observed_loaded"),
        ],
        "sensors_complete": False,
    }
    assert runtime_headline(result)["status"] == sighting


def test_executing_outranks_loaded():
    result = {
        "packages": [
            _row("deb|a|1", RUNTIME_LOADED, "observed_loaded"),
            _row("deb|b|1", RUNTIME_EXECUTING, "observed_executing"),
        ],
        "sensors_complete": True,
    }
    assert runtime_headline(result)["status"] == RUNTIME_EXECUTING


def test_an_all_unknown_fold_keeps_a_real_reason_from_the_closed_vocabulary():
    result = {
        "packages": [_row("deb|openssl|3.0.2", RUNTIME_UNKNOWN, "unversioned")],
        "sensors_complete": True,
    }
    folded = runtime_headline(result)
    assert folded["status"] == RUNTIME_UNKNOWN
    assert folded["reason"] == "unversioned"
    assert folded["reason"] in RUNTIME_REASONS


def test_the_client_fold_never_invents_a_producer_for_a_verdict_no_producer_emitted():
    # go-cloudsec's Unknown() stamps source because THERE it is the producer. Doing the
    # same here would fabricate provenance for a reduction that happened client-side.
    assert "source" not in runtime_headline({"packages": [], "sensors_complete": True})


def test_the_fold_tolerates_a_malformed_row_without_reading_it_as_a_verdict():
    result = {
        "packages": [{"key": "deb|openssl|3.0.2"}, None, {"key": "x", "verdict": None}],
        "sensors_complete": True,
    }
    folded = runtime_headline(result)
    assert folded["status"] == RUNTIME_UNKNOWN
    assert not is_runtime_negative(folded["status"])


# ---------------------------------------------------------------------------
# The transport
# ---------------------------------------------------------------------------


def test_check_finding_runtime_posts_the_documented_route_and_returns_it_verbatim():
    org = MagicMock()
    org.oid = "b85fd2bd-ae21-4c1f-8a42-b90b51aeddeb"
    payload = {
        "resource_urn": "lcrn:cloud:gcp:proj:instance/vm-1",
        "packages": [_row("deb|openssl|3.0.2", RUNTIME_PRESENT, "window_short")],
        "sensors": 1,
        "sensors_complete": True,
        "complete": False,
        "retry_after": 240000000000,
    }
    org.client.request.return_value = payload

    result = CloudSec(org).check_finding_runtime("fnd_0123abcd")

    assert org.client.request.call_count == 1
    call = org.client.request.call_args
    assert call.args[0] == "POST"
    assert call.args[1] == f"cloudsec/{org.oid}/findings/fnd_0123abcd/runtime-check"
    # Passed through with nothing reinterpreted: the SDK must not "helpfully" turn an
    # unsettled answer into a settled one, or a duration into a guess.
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


def _affirms_no_safety(text: str) -> None:
    """Assert the text never AFFIRMS safety, allowing it to deny it.

    Written this way deliberately. The sentence that makes this copy honest is itself a
    denial — "not that the vulnerability is not exploitable" — so a flat substring ban
    on "not exploitable" would forbid exactly the fix and pass on silence instead. So:
    ban phrases that affirm in any context, and require every clause that mentions
    exploitability, being fixed or being safe to carry a negation.
    """
    lowered = text.lower()
    for claim in ["is safe", "proves safe", "no risk", "safe to ignore",
                  "no action needed", "is not vulnerable", "false positive"]:
        assert claim not in lowered, claim
    for word in ["exploit", "fixed"]:
        clauses = [c for c in lowered.replace("\n", " ").split(".") if word in c]
        assert clauses, word
        for clause in clauses:
            assert "not" in clause or "never" in clause, (word, clause)


def test_cli_help_states_that_the_negative_rung_is_not_a_safety_claim():
    runner = CliRunner()
    result = runner.invoke(cli, ["cloudsec", "finding", "runtime-check", "--help"])
    assert result.exit_code == 0
    text = result.output
    # Says what not_observed does and does not mean, and claims nothing about
    # exploitability.
    assert "not_observed" in text
    assert "COMPLETE telemetry window" in text
    assert "Informational only" in text
    _affirms_no_safety(text)


def test_explain_documents_all_five_rungs_and_the_veto():
    # `explain` text is the agent-facing surface (limacharlie help discover / explain),
    # registered from the command module, so it is read through the registry rather than
    # through a top-level CLI verb, which does not exist.
    from limacharlie.discovery import get_explain

    text = get_explain("cloudsec.finding.runtime-check")
    assert text, "the command must be discoverable via explain"
    for rung in ["present", "not_observed", "loaded", "executing", "unknown"]:
        assert rung in text, rung
    # The reason the fold exists at all.
    assert "vetoes" in text
    assert "not a safety claim" in text.lower()
    _affirms_no_safety(text)
