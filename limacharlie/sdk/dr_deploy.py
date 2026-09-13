"""Validated D&R deployment with typed metadata and durable reconciliation."""
import hashlib
import json
from pathlib import Path
from urllib.parse import quote

import yaml

from ..errors import ApiError, NotFoundError
from .replay import Replay
from .. import agent_state as state
from ..agent_policy import check_permission


def evidence(data: dict, expected: bool | None = None) -> dict:
    """Check that Replay returned complete, nonempty fixture evidence.

    Args:
        data: Replay response.
        expected: Required match outcome, if specified.

    Returns:
        dict: Processed event count and match outcome.

    Raises:
        ValueError: Evidence is empty, partial, malformed or disagrees with expected.
    """
    if not isinstance(data, dict) or data.get("error") or data.get("errors"):
        raise ValueError("Replay returned errors or no recognizable evidence")
    stats = data.get("stats", {})
    if (not isinstance(stats, dict) or type(stats.get("n_proc")) is not int
            or stats["n_proc"] <= 0 or stats.get("results_partial")
            or data.get("cursor") or data.get("retryable_partial") or data.get("is_dry_run") is True
            or not isinstance(data.get("results"), list)
            or type(data.get("did_match")) is not bool):
        raise ValueError("Replay evidence is partial, empty or unrecognized")
    if expected is not None and data["did_match"] is not expected:
        raise ValueError("Positive/negative fixture did not have its required outcome")
    return {"processed": stats["n_proc"], "matched": data["did_match"]}



def _current(org, key, namespace):
    endpoint = f"hive/dr-{namespace}/{org.oid}/{quote(key, safe='')}/data"
    try:
        return org.client.request("GET", endpoint)
    except NotFoundError:
        return None
    except ApiError as exc:
        expected = f"lc_error_code:RECORD_NOT_FOUND - record name 'dr-{namespace}:{org.oid}:{key}'"
        body = exc.response_body
        if (exc.status_code == 400 and isinstance(body, dict) and body.get("error") == expected
                and body.get("data") == {} and body.get("retry") is False):
            return None
        raise


def _matches(observed, candidate):
    return (isinstance(observed, dict) and observed.get('data') == candidate['data']
            and isinstance(observed.get('usr_mtd'), dict)
            and all(observed['usr_mtd'].get(k) == v for k, v in candidate['usr_mtd'].items()))


def reconcile(org, key, namespace="general", accept_current=False):
    """Read an interrupted deployment; explicitly acknowledge divergent current state.

    This never writes remote data. accept_current releases the local recovery
    fence so a freshly read, reconciled candidate can be deployed separately.

    Args:
        org: Authenticated organization.
        key: Rule record key.
        namespace: Ordinary D&R namespace.
        accept_current: Acknowledge divergent current state without retrying.

    Returns:
        dict: Receipt status and independently observed remote record.

    Raises:
        ValueError: Agent permission is absent.
        ApiError: Remote state cannot be read.
    """
    if namespace not in ('general', 'managed', 'service') or not key:
        raise ValueError('A resource key and valid namespace are required')
    check_permission(org)
    resource = state.identifier('dr', org.oid, namespace, key)
    with state.resource_lock(resource), state.database() as db:
        pending = state.read(db, resource)
        observed = _current(org, key, namespace)
        if not pending:
            return {'status': 'no_pending_write', 'observed': observed}
        receipt = state.read(db, pending['receipt_id'])
        if _matches(observed, receipt['candidate']):
            receipt.update(status='verified', observed=observed)
        elif accept_current:
            receipt.update(status='reconciled_current', observed=observed)
        else:
            return {'status': 'unknown_outcome', 'receipt_id': pending['receipt_id'], 'observed': observed,
                    'next': 'Inspect remote state; --accept-current acknowledges it without retrying the write.'}
        state.save(db, pending['receipt_id'], receipt)
        db.execute('DELETE FROM records WHERE id=?', (resource,)); db.commit()
        return receipt


def deploy(org, key, candidate_path, positive_path, negative_path, namespace="general", dry_run=False,
           *, enabled=None, tags=None, comment=None, etag=None):
    """Compile/test a rule, preserve metadata, conditionally write once and verify.

    Inputs may be a bare rule or Hive envelope. CLI metadata options override
    envelope metadata. Existing fields omitted by the caller are preserved.
    Updates require an explicitly supplied current etag. Evidence survives a
    crash and subsequent invocations reconcile instead of replaying a write.

    Args:
        org: Authenticated organization.
        key: Rule record key.
        candidate_path: JSON or YAML rule or Hive envelope file.
        positive_path: JSON event sequence, or array of sequences, each of which must match.
        negative_path: JSON event sequence, or array of sequences, none of which may match.
        namespace: Ordinary D&R namespace.
        dry_run: Validate and preview without writing.
        enabled: Explicit metadata enabled state; None preserves existing state.
        tags: Replacement metadata tags; None preserves existing tags.
        comment: Replacement metadata comment; None preserves existing comment.
        etag: Expected current record etag for conditional updates.

    Returns:
        dict: Candidate, observed state, checks and durable receipt ID/status.

    Raises:
        ValueError: Input, permission, fixture, concurrency or verification checks fail.
        ApiError: An API operation fails; reconcile an uncertain write before retrying.
    """
    if namespace not in ("general", "managed", "service") or not key:
        raise ValueError("A resource key and valid namespace are required")
    paths = [Path(p) for p in (candidate_path, positive_path, negative_path)]
    raw = []
    for path in paths:
        with path.open('rb') as handle:
            value = handle.read(2 * 1024 * 1024 + 1)
        if len(value) > 2 * 1024 * 1024:
            raise ValueError('Candidate and fixtures must each fit within 2 MiB')
        raw.append(value)
    artifact = yaml.safe_load(raw[0])
    if not isinstance(artifact, dict):
        raise ValueError('Require a rule object or Hive envelope')
    rule = artifact.get('data', artifact)
    metadata = dict(artifact.get('usr_mtd', {})) if isinstance(artifact.get('usr_mtd', {}), dict) else None
    if not isinstance(rule, dict) or not isinstance(rule.get('detect'), dict) or not isinstance(rule.get('respond'), list):
        raise ValueError('Require detect and respond in rule data')
    misplaced = set(rule) & {'tags', 'comment', 'enabled', 'expiry', 'usr_mtd', 'sys_mtd', 'etag'}
    if misplaced:
        raise ValueError('Metadata does not belong in rule data: ' + ', '.join(sorted(misplaced)) +
                         '; use --tag, --comment, --enabled/--disabled or usr_mtd')
    if metadata is None:
        raise ValueError('usr_mtd must be an object')
    for name, value in [('enabled', enabled), ('tags', tags), ('comment', comment)]:
        if value is not None:
            metadata[name] = value
    if 'enabled' in metadata and type(metadata['enabled']) is not bool:
        raise ValueError('enabled must be a boolean')
    if 'tags' in metadata and (not isinstance(metadata['tags'], list) or not all(isinstance(t, str) for t in metadata['tags'])):
        raise ValueError('tags must be an array of strings')
    if 'comment' in metadata and not isinstance(metadata['comment'], str):
        raise ValueError('comment must be a string')
    etag = etag if etag is not None else artifact.get('etag')
    fixtures = [json.loads(x) for x in raw[1:]]
    def scenarios(value):
        if isinstance(value, list) and value and all(isinstance(e, dict) for e in value):
            return [value]  # Existing format: one ordered event sequence.
        if (isinstance(value, list) and value and all(isinstance(s, list) and s
                and all(isinstance(e, dict) for e in s) for s in value)):
            return value
        raise ValueError('Fixtures must be nonempty JSON arrays of event objects or event sequences')
    fixture_scenarios = [scenarios(value) for value in fixtures]
    check_permission(org)
    resource = state.identifier('dr', org.oid, namespace, key)
    receipt_id = state.identifier(resource, [hashlib.sha256(x).hexdigest() for x in raw], metadata, etag)
    with state.resource_lock(resource), state.database() as db:
        current = _current(org, key, namespace)
        pending = state.read(db, resource)
        if pending:
            previous = state.read(db, pending['receipt_id'])
            if _matches(current, previous['candidate']):
                previous.update(status='verified', observed=current)
                state.save(db, pending['receipt_id'], previous)
                db.execute('DELETE FROM records WHERE id=?', (resource,)); db.commit()
                if pending['receipt_id'] == receipt_id:
                    return previous
            else:
                raise ValueError('Unresolved write ' + pending['receipt_id'] + '; use dr reconcile before another deployment')
        previous = state.read(db, receipt_id)
        if previous and previous['status'] == 'verified':
            if _matches(current, previous['candidate']):
                return dict(previous, observed=current)
            raise ValueError('Previously verified candidate has drifted; read current state and reconcile a fresh candidate')
        if current is not None:
            if not isinstance(current, dict) or not isinstance(current.get('usr_mtd'), dict):
                raise ValueError('Unrecognized current record; cannot safely update')
            current_etag = current.get('sys_mtd', {}).get('etag')
            if not current_etag or etag != current_etag:
                raise ValueError('Stale or missing etag; re-read and reconcile the current record')
            metadata = {**current['usr_mtd'], **metadata}
        elif etag is not None:
            raise ValueError('Expected existing record is absent; reconcile before creating')
        if type(metadata.get('enabled')) is not bool:
            raise ValueError('New rule requires explicit --enabled/--disabled or usr_mtd.enabled')
        candidate = {'data': rule, 'usr_mtd': metadata}
        replay = Replay(org)
        stream = {'detection': 'detect', 'audit': 'audit'}.get(rule['detect'].get('target'), 'event')
        proofs = [[evidence(replay.scan_events(events, rule_content=rule, stream=stream), expected)
                   for events in cases] for cases, expected in zip(fixture_scenarios, (True, False))]
        positive, negative = [items[0] if len(items) == 1 else {'scenarios': items} for items in proofs]
        for path, original in zip(paths, raw):
            with path.open('rb') as handle:
                if handle.read(2 * 1024 * 1024 + 1) != original:
                    raise ValueError('Input changed during validation; nothing was written')
        result = {'status': 'previewed', 'receipt_id': receipt_id, 'org_id': org.oid, 'key': key, 'namespace': namespace,
                  'candidate_sha256': state.identifier(candidate), 'candidate': candidate, 'before': current,
                  'checks': {'compiled': True, 'positive': positive, 'negative': negative, 'metadata_and_etag': True}}
        if dry_run:
            return result
        # Check again after potentially long Replay tests, immediately before mutation.
        check_permission(org)
        result['status'] = 'write_started'
        state.save(db, receipt_id, result)
        state.save(db, resource, {'receipt_id': receipt_id})
        params = {'data': json.dumps(rule), 'usr_mtd': json.dumps(metadata)}
        if current is not None:
            params['etag'] = etag
        endpoint = f"hive/dr-{namespace}/{org.oid}/{quote(key, safe='')}/data"
        try:
            # Client max_retries counts attempts: one prevents implicit 504 retries.
            org.client.request('POST', endpoint, params=params, max_retries=1)
            observed = _current(org, key, namespace)
            if not _matches(observed, candidate):
                raise ValueError('Write accepted but read-back differs; outcome unverified, use dr reconcile')
        except BaseException:
            result['status'] = 'unknown_outcome'
            state.save(db, receipt_id, result)
            raise
        result.update(status='verified', observed=observed)
        state.save(db, receipt_id, result)
        db.execute('DELETE FROM records WHERE id=?', (resource,)); db.commit()
        return result
