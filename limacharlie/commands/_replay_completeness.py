"""Detect and report a replay that did not cover its whole request.

Replay answers HTTP 200 when it stops early: at its server-side deadline, when a
batch could not be fetched or was too slow, when an event was too large to
evaluate, or at a limit the caller set. The response still carries matches and
counts, but they cover only part of the window, so "0 matches" from such a run
says nothing about the rule. The flags that say so sit deep in ``stats`` and are
easy to miss; these helpers surface them on stderr.
"""

from __future__ import annotations

from typing import Any

import click

# stats.stop_reason values that mean the scan ended before the window was
# covered. "none" and an empty value mean it ran to completion.
_COMPLETE_STOP_REASONS = frozenset({"", "none"})


def partial_reasons(data: Any) -> list[str]:
    """Return why a replay response is incomplete, or an empty list.

    Args:
        data: The decoded replay response.

    Returns:
        list[str]: One short reason per signal found, in a stable order.
    """
    if not isinstance(data, dict):
        return []
    reasons: list[str] = []
    stats = data.get("stats")
    if not isinstance(stats, dict):
        stats = {}

    if stats.get("results_partial"):
        reasons.append("stats.results_partial is true")
    stop_reason = stats.get("stop_reason") or ""
    if isinstance(stop_reason, str) and stop_reason not in _COMPLETE_STOP_REASONS:
        reasons.append(f"stopped early (stats.stop_reason: {stop_reason})")
    stopped_early = stats.get("stopped_early_reason")
    if stopped_early:
        reasons.append(f"stopped early (stats.stopped_early_reason: {stopped_early})")
    skipped = stats.get("skipped_events")
    if isinstance(skipped, list) and skipped:
        reasons.append(f"{len(skipped)} event(s) skipped (stats.skipped_events)")
    error = data.get("error")
    if error:
        reasons.append(f"error: {error}")
    return reasons


def warn_if_partial(data: Any) -> None:
    """Print a warning to stderr when a replay response is incomplete.

    The warning is printed even under --quiet: it changes what the result means.

    Args:
        data: The decoded replay response.
    """
    reasons = partial_reasons(data)
    if not reasons:
        return
    click.echo(
        "Warning: replay results are PARTIAL: " + "; ".join(reasons) + ". "
        "Matches and counts cover only part of the requested window, so zero "
        "matches does not show the rule is clean. Re-run with a narrower scope "
        "(--sid or --selector) or a shorter window until no warning is printed.",
        err=True,
    )
