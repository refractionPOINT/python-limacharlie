"""Replay SDK for LimaCharlie v2."""

from __future__ import annotations

import json
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .organization import Organization


class Replay:
    """D&R rule replay against historical data."""

    def __init__(self, org: Organization) -> None:
        self._org = org
        self._replay_url: str | None = None

    def _get_replay_url(self) -> str:
        if self._replay_url is None:
            urls = self._org.get_urls()
            self._replay_url = urls.get("replay", "")
        return self._replay_url

    def run(self, rule_name: str | None = None, detect: dict[str, Any] | None = None,
            respond: list[dict[str, Any]] | None = None, start: int | None = None,
            end: int | None = None, sid: str | None = None, selector: str | None = None,
            stream: str | None = None, trace: bool = False, dry_run: bool = False,
            limit_events: int | None = None, limit_evals: int | None = None) -> dict[str, Any]:
        """Replay a rule against historical data.

        Args:
            rule_name: Existing rule name (OR provide detect/respond).
            detect: Detection component dict.
            respond: Response component list.
            start: Start time (unix seconds).
            end: End time (unix seconds).
            sid: Specific sensor ID.
            selector: Sensor selector expression.
            stream: Stream type.
            trace: Enable trace output.
            dry_run: Simulate without generating detections.
            limit_events: Max events to scan.
            limit_evals: Max evaluations.

        Returns:
            dict: Replay results.
        """
        replay_url = self._get_replay_url()

        rule_source: dict[str, Any] = {}
        if rule_name:
            rule_source["rule_name"] = rule_name
        if detect is not None or respond is not None:
            rule_source["rule"] = {}
            if detect is not None:
                rule_source["rule"]["detect"] = detect
            if respond is not None:
                rule_source["rule"]["respond"] = respond

        sensor_events: dict[str, Any] = {}
        if start is not None:
            sensor_events["start_time"] = int(start)
        if end is not None:
            sensor_events["end_time"] = int(end)
        if sid:
            sensor_events["sid"] = str(sid)
        if selector:
            sensor_events["selector"] = selector

        req: dict[str, Any] = {
            "oid": self._org.oid,
            "rule_source": rule_source,
            "event_source": {
                "stream": stream or "event",
                "sensor_events": sensor_events,
            },
            "trace": trace,
            "is_dry_run": dry_run,
            "limit_event": limit_events or 0,
            "limit_eval": limit_evals or 0,
        }

        return self._org.client.request(
            "POST", "",
            alt_root=f"https://{replay_url}/",
            raw_body=json.dumps(req).encode(),
            content_type="application/json",
        )

    def scan_events(self, events: list[dict[str, Any]], rule_name: str | None = None,
                    namespace: str | None = None, rule_content: dict[str, Any] | None = None,
                    trace: bool = False, dry_run: bool = False, limit_events: int | None = None,
                    limit_evals: int | None = None, stream: str = "event") -> dict[str, Any]:
        """Test a rule against specific events.

        Args:
            events: List of event dicts to evaluate.
            rule_name: Existing rule name (OR provide rule_content).
            namespace: Rule namespace (if using rule_name).
            rule_content: Dict with 'detect' and 'respond' keys.
            trace: Enable trace output.
            dry_run: Simulate without generating detections.
            limit_events: Max events to scan.
            limit_evals: Max evaluations.
            stream: Data stream type (default 'event').

        Returns:
            dict: Evaluation results.
        """
        replay_url = self._get_replay_url()

        req: dict[str, Any] = {
            "oid": self._org.oid,
            "rule_source": {
                "rule_name": rule_name or "",
                "namespace": namespace or "",
                "rule": rule_content,
            },
            "event_source": {
                "stream": stream,
                "sensor_events": {},
                "events": events,
            },
            "trace": trace,
            "limit_event": limit_events or 0,
            "limit_eval": limit_evals or 0,
            "is_dry_run": dry_run,
        }

        return self._org.client.request(
            "POST", "",
            alt_root=f"https://{replay_url}/",
            raw_body=json.dumps(req).encode(),
            content_type="application/json",
        )

    def validate_rule(self, rule_content: dict[str, Any]) -> dict[str, Any]:
        """Validate that a D&R rule compiles properly.

        Sends a minimal event through the replay engine to check that
        the rule structure is valid without producing real detections.

        Args:
            rule_content: Dict with 'detect' and 'respond' keys.

        Returns:
            dict: Validation results (empty results means valid).
        """
        return self.scan_events(
            events=[{"event": {}, "routing": {}}],
            rule_content=rule_content,
            stream="event",
        )
