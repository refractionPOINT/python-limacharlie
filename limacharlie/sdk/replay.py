"""Replay SDK for LimaCharlie v2."""

import json


class Replay:
    """D&R rule replay against historical data."""

    def __init__(self, org):
        self._org = org
        self._replay_url = None

    def _get_replay_url(self):
        if self._replay_url is None:
            urls = self._org.get_urls()
            self._replay_url = urls.get("replay", "")
        return self._replay_url

    def run(self, rule_name=None, detect=None, respond=None, start=None, end=None,
            sid=None, selector=None, stream=None, trace=False, dry_run=False,
            limit_events=None, limit_evals=None):
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
        params = {}
        if rule_name:
            params["rule_name"] = rule_name
        if detect:
            params["detect"] = detect
        if respond:
            params["respond"] = respond
        if start:
            params["start"] = str(int(start))
        if end:
            params["end"] = str(int(end))
        if sid:
            params["sid"] = str(sid)
        if selector:
            params["selector"] = selector
        if stream:
            params["stream"] = stream
        if trace:
            params["trace"] = "true"
        if dry_run:
            params["dry_run"] = "true"
        if limit_events:
            params["limit_events"] = str(limit_events)
        if limit_evals:
            params["limit_evals"] = str(limit_evals)

        return self._org.service_request("replay", params, is_async=True)

    def scan_events(self, events, rule_name=None, namespace=None, rule_content=None,
                    trace=False, dry_run=False, limit_events=None, limit_evals=None,
                    stream="event"):
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

        req = {
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

    def validate_rule(self, rule_content):
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
