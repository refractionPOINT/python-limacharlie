import copy
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from click.testing import CliRunner

from limacharlie import dr_drafting as draft, draft_guard
from limacharlie.cli import cli

EVENT = {'routing': {'event_type': 'NETWORK_CONNECTIONS', 'sid': 's'},
         'event': {'FILE_PATH': '/tmp/java', 'NETWORK_ACTIVITY': [
             {'DESTINATION': {'PORT': 389}, 'IS_OUTGOING': 1}]}}
RULE = {'detect': {'event': 'NETWORK_CONNECTIONS', 'op': 'and', 'rules': [
    {'op': 'is', 'path': 'event/FILE_PATH', 'value': 'java', 'file name': True},
    {'op': 'scope', 'path': 'event/NETWORK_ACTIVITY/', 'rule': {'op': 'and', 'rules': [
        {'op': 'is', 'path': 'event/DESTINATION/PORT', 'value': 389},
        {'op': 'is', 'path': 'event/IS_OUTGOING', 'value': 1}]}}]},
    'respond': [{'action': 'report', 'name': 'test'}]}


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv('LC_AGENT_STATE_DIR', str(tmp_path / 'state'))
    org = SimpleNamespace(oid='o', list_sensors=Mock(return_value=iter([{'hostname': 'lab', 'sid': 's'}])))
    sensor = Mock()
    sensor.get_info.return_value = {'hostname': 'lab'}
    sensor.get_events.return_value = [copy.deepcopy(EVENT)]
    monkeypatch.setattr(draft, 'Sensor', lambda org, sid: sensor)
    root = tmp_path / 'draft'
    result = draft.prepare(org, root, hostname='lab')
    negative = copy.deepcopy(EVENT); negative['event']['FILE_PATH'] = '/tmp/python'
    for name, value in [('candidate.json', RULE), ('positive.json', [EVENT]), ('negative.json', [negative])]:
        draft.save(root / name, value)
    replay = Mock()
    replay.scan_events.side_effect = [
        {'stats': {'n_proc': 1}, 'results': [{}], 'did_match': True},
        {'stats': {'n_proc': 1}, 'results': [], 'did_match': False}]
    monkeypatch.setattr('limacharlie.sdk.replay.Replay', lambda org: replay)
    return org, root, sensor, replay, result


def test_prepare_resolves_identity_window_and_retains_array_shape(workspace):
    org, root, sensor, _, result = workspace
    assert result['sid'] == 's'
    assert result['window']['end'] - result['window']['start'] == 86400
    assert sensor.get_events.call_args.kwargs == {'limit': 200, 'event_type': None, 'is_forward': False}
    assert 'event/NETWORK_ACTIVITY/?/DESTINATION/PORT' in result['observed_paths']['NETWORK_CONNECTIONS']
    assert draft.load(root / 'evidence.json') == [EVENT]
    assert (root / 'evidence.json').stat().st_mode & 0o777 == 0o600


def test_prepare_refuses_ambiguous_host_before_fetch(workspace, tmp_path):
    org, _, sensor, _, _ = workspace
    org.list_sensors.return_value = iter([{'hostname': 'lab', 'sid': 'a'}, {'hostname': 'lab', 'sid': 'b'}])
    with pytest.raises(ValueError, match='found 2'):
        draft.prepare(org, tmp_path / 'ambiguous', hostname='lab')
    assert sensor.get_events.call_count == 1


@pytest.mark.parametrize('last', ['0h', '-1h', '32d', '2025-09-13', '1.5h'])
def test_invalid_relative_windows(last):
    with pytest.raises(ValueError): draft.relative_window(last)


def test_relative_window_never_guesses_year():
    assert draft.relative_window('24h', now=1789272000) == (1789185600, 1789272000)


def test_diagnostics_distinguish_bad_syntax_from_unobserved_fields():
    assert draft.diagnose(RULE, [EVENT]) == ([], [])
    rule = copy.deepcopy(RULE); rule['detect']['rules'][0]['path'] = 'event.FILE_PATH'
    errors, _ = draft.diagnose(rule, [EVENT]); assert any('slash' in e for e in errors)
    rule['detect']['rules'][0]['path'] = 'event/UNOBSERVED'
    errors, warnings = draft.diagnose(rule, [EVENT]); assert not errors and warnings
    rule['detect']['rules'][0]['path'] = 'event/PORT'
    errors, warnings = draft.diagnose(rule, [EVENT]); assert not errors and any('scope' in w for w in warnings)


def test_named_detect_envelope_rejected():
    errors, _ = draft.diagnose({'detect': {'my-rule': RULE['detect']}, 'respond': []}, [EVENT])
    assert any('nest a rule name' in e for e in errors)


def test_check_validates_each_fixture_and_records_provenance(workspace):
    org, root, _, replay, _ = workspace
    result = draft.check(org, root)
    assert result['status'] == 'tested' and result['grounding'] == 'sample_backed'
    assert result['fixture_provenance'] == {'positive': ['captured'], 'negative': ['synthetic_or_modified']}
    assert len(result['checks']) == 2 and not result['deployed']
    assert replay.scan_events.call_args_list[0].args == ([EVENT],)


def test_second_positive_failure_cannot_hide_behind_first(workspace):
    org, root, _, replay, _ = workspace
    (root / 'positive.json').write_text(json.dumps([EVENT, EVENT]))
    replay.scan_events.side_effect = [
        {'stats': {'n_proc': 1}, 'results': [{}], 'did_match': True},
        {'stats': {'n_proc': 1}, 'results': [], 'did_match': False},
        {'stats': {'n_proc': 1}, 'results': [], 'did_match': False}]
    result = draft.check(org, root)
    assert result['status'] == 'invalid' and 'positive[1]' in result['errors'][0]


def test_changed_captured_evidence_rejected_before_replay(workspace):
    org, root, _, replay, _ = workspace
    (root / 'evidence.json').write_text('[]')
    with pytest.raises(ValueError, match='evidence changed'): draft.check(org, root)
    replay.scan_events.assert_not_called()


def test_workspace_paths_cannot_escape(workspace):
    org, root, _, replay, _ = workspace
    with pytest.raises(ValueError, match='reside'): draft.check(org, root, candidate='../candidate.json')
    replay.scan_events.assert_not_called()


def test_invalid_candidate_replaces_stale_success(workspace):
    org, root, _, replay, _ = workspace
    assert draft.check(org, root)['status'] == 'tested'
    (root / 'candidate.json').write_text('{}')
    assert draft.check(org, root)['status'] == 'invalid'
    assert draft.load(root / 'check.json')['status'] == 'invalid'
    assert replay.scan_events.call_count == 2


def test_cli_failed_check_exits_nonzero(workspace, monkeypatch):
    org, root, _, _, _ = workspace
    monkeypatch.setattr('limacharlie.commands.dr._get_org', lambda ctx: org)
    (root / 'candidate.json').write_text('{}')
    r = CliRunner().invoke(cli, ['dr', 'check', '--workspace', str(root), '--output', 'json'])
    assert r.exit_code == 1 and json.loads(r.output)['status'] == 'invalid'


@pytest.mark.parametrize('path,params', [(('task','request'), {'command': 'os_suspend 0'}),
    (('task','send'), {'command': 'netstat'}), (('dr','deploy'), {'dry_run': False}),
    (('api','request'), {'method':'POST'}), (('sensor','delete'), {}), (('search','run'), {})])
def test_drafting_blocks_unrelated_actions_until_next_user_turn(workspace, path, params):
    org, root, _, _, _ = workspace
    draft_guard.activate(org.oid, root)
    with pytest.raises(ValueError, match='drafting permits'): draft_guard.validate(path, params, org.oid)
    draft_guard.clear()
    draft_guard.validate(path, params, org.oid)


def test_draft_allows_checks_and_denies_other_organization(workspace):
    org, root, _, _, _ = workspace
    draft_guard.activate(org.oid, root)
    draft_guard.validate(('dr','check'), {}, org.oid)
    draft_guard.validate(('dr','deploy'), {'dry_run': True}, org.oid)
    with pytest.raises(ValueError, match='prepared organization'):
        draft_guard.validate(('dr','check'), {}, 'other')


def test_stateful_scenarios_keep_event_sequence_together(workspace):
    org, root, _, replay, _ = workspace
    (root / 'positive.json').write_text(json.dumps([[EVENT, EVENT]]))
    result = draft.check(org, root)
    assert result['status'] == 'tested'
    assert replay.scan_events.call_args_list[0].args == ([EVENT, EVENT],)


def test_sdk_replay_value_error_keeps_actionable_failure(workspace):
    org, root, _, replay, _ = workspace
    replay.scan_events.side_effect = ValueError('invalid operator')
    result = draft.check(org, root)
    assert result['status'] == 'invalid' and 'invalid operator' in result['errors'][0]


def test_deployment_requires_exact_successfully_checked_files(workspace):
    org, root, _, _, _ = workspace
    draft.check(org, root)
    paths = [root / name for name in ('candidate.json', 'positive.json', 'negative.json')]
    draft.require_tested(root, org.oid, paths)
    candidate = copy.deepcopy(RULE); candidate['respond'][0]['name'] = 'changed'
    paths[0].write_text(json.dumps(candidate))
    with pytest.raises(ValueError, match='differ from the tested'):
        draft.require_tested(root, org.oid, paths)


def test_empty_runner_uid_does_not_turn_org_key_into_user_key(monkeypatch):
    from limacharlie.config import resolve_credentials
    monkeypatch.setenv('LC_API_KEY', 'org-key')
    monkeypatch.setenv('LC_OID', 'org')
    monkeypatch.setenv('LC_UID', '')
    creds = resolve_credentials()
    assert creds['uid'] is None and creds['api_key'] == 'org-key'
    assert resolve_credentials(uid='')['uid'] is None
    assert resolve_credentials(uid='real-user')['uid'] == 'real-user'


def test_yaml_fixtures_cannot_pass_check_then_fail_json_deployment(workspace):
    org, root, _, replay, _ = workspace
    (root / 'positive.json').write_text('- event:\n    FILE_PATH: /tmp/java\n')
    with pytest.raises(ValueError): draft.check(org, root)
    replay.scan_events.assert_not_called()
    assert not (root / 'check.json').exists()


def test_empty_capture_cannot_be_replaced_with_self_authored_evidence(workspace):
    org, root, _, replay, _ = workspace
    (root / 'evidence.json').write_text('[]')
    manifest = draft.load(root / 'manifest.json');manifest['evidence_sha256'] = draft.digest([])
    (root / 'manifest.json').write_text(json.dumps(manifest))
    result = draft.check(org, root)
    assert result['status'] == 'invalid'
    assert any('No captured evidence' in e for e in result['errors'])
    replay.scan_events.assert_not_called()


def test_prepare_accepts_mkdir_created_empty_workspace(workspace, tmp_path):
    org, _, _, _, _ = workspace
    root = tmp_path / 'already-created';root.mkdir()
    assert draft.prepare(org, root, sid='s')['status'] == 'prepared'
    original = (root / 'evidence.json').read_bytes()
    with pytest.raises(ValueError, match='contains files'):
        draft.prepare(org, root, sid='s')
    assert (root / 'evidence.json').read_bytes() == original


def test_capture_budget_stops_consuming_events(workspace, tmp_path, monkeypatch):
    org, _, sensor, _, _ = workspace
    monkeypatch.setattr(draft, 'MAX_BYTES', 64)
    def events():
        yield {'large': 'x' * 65}
        raise AssertionError('Read beyond byte budget')
    sensor.get_events.return_value = events()
    with pytest.raises(ValueError, match='exceeds 2 MiB'):
        draft.prepare(org, tmp_path / 'bounded', sid='s')


def test_missing_check_explains_required_next_step(workspace):
    org, root, _, _, _ = workspace
    with pytest.raises(ValueError, match='Run dr check'):
        draft.require_tested(root, org.oid, [])
