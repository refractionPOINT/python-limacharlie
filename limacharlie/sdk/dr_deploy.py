"""Experimental all-in-one D&R deployment; no MCP or agent-backend dependency."""
import hashlib
import json
from pathlib import Path
from urllib.parse import quote

import yaml

from ..errors import ApiError, NotFoundError
from .replay import Replay


def evidence(data, expected=None):
    if not isinstance(data, dict) or data.get("error") or data.get("errors"):
        raise ValueError("Replay returned errors or no recognizable evidence")
    stats = data.get("stats", {})
    if (not isinstance(stats, dict) or type(stats.get("n_proc")) is not int
            or stats["n_proc"] <= 0 or stats.get("results_partial")
            or data.get("cursor") or data.get("retryable_partial")
            or not isinstance(data.get("results"), list)
            or type(data.get("did_match")) is not bool):
        raise ValueError("Replay evidence is partial, empty or unrecognized")
    if expected is not None and data["did_match"] is not expected:
        raise ValueError("Positive/negative fixture did not have its required outcome")
    return {"processed": stats["n_proc"], "matched": data["did_match"]}


def deploy(org, key, candidate_path, positive_path, negative_path, namespace="general", dry_run=False):
    if namespace not in ("general", "managed", "service") or not key:
        raise ValueError("A resource key and valid namespace are required")
    paths = [Path(p) for p in (candidate_path, positive_path, negative_path)]
    raw = [p.read_bytes() for p in paths]
    if any(len(x) > 2 * 1024 * 1024 for x in raw):
        raise ValueError("Candidate and fixtures must each fit within 2 MiB")
    candidate = yaml.safe_load(raw[0])
    if not isinstance(candidate, dict) or not isinstance(candidate.get("data"), dict):
        raise ValueError("Use a full Hive envelope with data and explicit usr_mtd.enabled")
    rule, metadata = candidate["data"], candidate.get("usr_mtd", {})
    if (not isinstance(rule.get("detect"), dict) or not isinstance(rule.get("respond"), list)
            or not isinstance(metadata, dict) or type(metadata.get("enabled")) is not bool):
        raise ValueError("Require detect/respond and explicit boolean usr_mtd.enabled")
    fixtures = [json.loads(x) for x in raw[1:]]
    if any(not isinstance(x, list) or not x or not all(isinstance(e, dict) for e in x) for x in fixtures):
        raise ValueError("Fixtures must be nonempty JSON arrays of event objects")
    identity = org.who_am_i()
    perms = list(identity.get("perms", []))
    for p in identity.get("user_perms", {}).values():
        if isinstance(p, list): perms.extend(p)
    if "ai_agent.operate" not in perms:
        raise ValueError("Identity lacks ai_agent.operate in this organization")
    endpoint = f"hive/dr-{namespace}/{org.oid}/{quote(key, safe='')}"
    try:
        current = org.client.request("GET", endpoint + "/data")
    except NotFoundError:
        current = None
    except ApiError as exc:
        expected = f"lc_error_code:RECORD_NOT_FOUND - record name 'dr-{namespace}:{org.oid}:{key}'"
        body = exc.response_body
        if not (exc.status_code == 400 and isinstance(body, dict)
                and body.get("error") == expected and body.get("data") == {}
                and body.get("retry") is False):
            raise
        current = None
    if current is not None:
        if not isinstance(current, dict) or not isinstance(current.get("usr_mtd"), dict):
            raise ValueError("Unrecognized current record; cannot safely update")
        missing = set(current["usr_mtd"]) - set(metadata)
        if missing:
            raise ValueError("Preserve or explicitly change current metadata: " + ", ".join(sorted(missing)))
        etag = current.get("sys_mtd", {}).get("etag")
        if not etag or candidate.get("etag") != etag:
            raise ValueError("Stale or missing etag; re-read and reconcile the current record")
    replay = Replay(org)
    stream = {"detection": "detect", "audit": "audit"}.get(rule["detect"].get("target"), "event")
    # The positive fixture proves compilation on the actual target layout too.
    # Replay dry_run is estimation, not the inline fixture evaluation used by dr test.
    positive = evidence(replay.scan_events(fixtures[0], rule_content=rule, stream=stream), True)
    negative = evidence(replay.scan_events(fixtures[1], rule_content=rule, stream=stream), False)
    if any(p.read_bytes() != original for p, original in zip(paths, raw)):
        raise ValueError("Input changed during validation; nothing was written")
    result = {"status": "previewed", "org_id": org.oid, "key": key, "namespace": namespace,
              "candidate_sha256": hashlib.sha256(raw[0]).hexdigest(),
              "checks": {"compiled": True, "positive": positive, "negative": negative,
                         "metadata_and_etag": True}, "before": current, "candidate": candidate}
    if dry_run:
        return result
    params = {"data": json.dumps(rule), "usr_mtd": json.dumps(metadata)}
    if current is not None: params["etag"] = candidate["etag"]
    # Do not retry ambiguous writes here. The caller must reconcile remote state.
    org.client.request("POST", endpoint + "/data", params=params)
    observed = org.client.request("GET", endpoint + "/data")
    if (observed.get("data") != rule or
            any(observed.get("usr_mtd", {}).get(k) != v for k, v in metadata.items())):
        raise ValueError("Write accepted but read-back differs; outcome unverified, inspect remote state")
    result.update(status="verified", observed=observed)
    return result
