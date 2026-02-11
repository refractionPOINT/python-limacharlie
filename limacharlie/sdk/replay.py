"""Replay SDK for LimaCharlie v2."""

import json


class Replay:
    """D&R rule replay against historical data."""

    def __init__(self, org):
        self._org = org

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
            params["detect"] = json.dumps(detect)
        if respond:
            params["respond"] = json.dumps(respond)
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

        return self._org.service_request("replay", params)
