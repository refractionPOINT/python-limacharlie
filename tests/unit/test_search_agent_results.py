"""Regressions from a user-wide session that misreported an incomplete JVM search."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from click.testing import CliRunner

from limacharlie.cli import cli
from limacharlie.sdk.search import Search
from limacharlie.commands._search_summary import output_summary


@pytest.fixture
def search():
    org = Mock(oid='tenant')
    search = Search(org)
    search._get_search_url = lambda: 'https://search.test/'
    search._extract_region = lambda: 'test'
    return search, org.client


def test_metadata_envelopes_do_not_exhaust_matching_row_limit(search):
    query, client = search
    empty_page = [{'type': 'events', 'rows': [], 'nextToken': 'page2'}]
    empty_page += [{'type': 'timeline', 'timeseries': [], 'nextToken': 'page2'}] * 55
    client.request.side_effect = [{'queryId': 'q'}, {'results': empty_page, 'completed': True},
                                 {'results': [{'type': 'events', 'rows': [{'data': {'name': 'java.exe'}}]}], 'completed': True}, {}]
    results = list(query.execute('* | NEW_PROCESS', 1000, 2000, limit=1))
    assert results[-1]['rows'][0]['data']['name'] == 'java.exe'
    assert query.execution['complete'] is True
    assert query.execution['rows_returned'] == 1
    assert query.execution['pages_completed'] == 2


def test_zero_match_page_budget_is_explicitly_partial(search):
    query, client = search
    client.request.side_effect = [{'queryId': 'q'}, {'completed': True, 'results': [
        {'type': 'events', 'rows': [], 'nextToken': 'page2'}]}, {}]
    list(query.execute('* | NEW_PROCESS', 1000, 2000, limit=50, max_pages=1))
    assert query.execution['complete'] is False
    assert query.execution['stop_reason'] == 'page_limit'
    assert query.execution['continuation'] == 'page2'


def test_summary_distinguishes_complete_search_from_truncated_display(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('LC_AGENT_STATE_DIR', str(tmp_path))
    rows = [{'data': {'name': 'java.exe', 'i': i}} for i in range(30)]
    results = [{'type': 'events', 'rows': rows,
                'stats': {'orchestratorAllocBytes': 999999, 'cumulativeStats': {'eventsScanned': 300, 'eventsMatched': 30}}}]
    output_summary(None, iter(results), {'complete': True, 'stop_reason': 'exhausted', 'pages_completed': 2})
    summary = json.loads(capsys.readouterr().out)
    assert summary['complete'] is True and summary['displayed_rows_complete'] is False
    assert summary['matching_rows_returned'] == 30
    assert len(summary['rows']) == 20
    assert summary['reported_statistics'] == {'eventsScanned': 300, 'eventsMatched': 30}
    assert [json.loads(line) for line in Path(summary['artifact_path']).read_text().splitlines()] == rows


def test_summary_failure_retains_partial_evidence(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('LC_AGENT_STATE_DIR', str(tmp_path))
    def records():
        yield {'type': 'events', 'rows': [{'data': {'name': 'java.exe'}}]}
        raise RuntimeError('connection lost')
    with pytest.raises(RuntimeError):
        output_summary(None, records(), {'complete': False, 'stop_reason': 'error'})
    result = json.loads(capsys.readouterr().out)
    assert result['status'] == 'error' and not result['complete']
    assert result['matching_rows_returned'] == 1


def test_user_wide_real_cli_org_discovery(monkeypatch):
    monkeypatch.setenv('LC_AGENT_MODE', '1')
    monkeypatch.delenv('LC_OID', raising=False)
    from limacharlie.commands import org, auth
    organization = Mock()
    organization.list_accessible_orgs.return_value = {'orgs': ['known-oid'], 'names': {'known-oid': 'test-org'}}
    monkeypatch.setattr(org, '_get_org', lambda ctx: organization)
    monkeypatch.setattr(auth, '_get_org', lambda ctx: organization)
    for args in (['org', 'list', '--filter', 'test-org'], ['auth', 'list-orgs']):
        result = CliRunner().invoke(cli, args + ['--output', 'json'])
        assert result.exit_code == 0, result.output
        assert json.loads(result.output) == [{'oid': 'known-oid', 'name': 'test-org'}]


def test_agent_search_json_has_final_coverage_without_generic_capture(search, tmp_path, monkeypatch):
    query, client = search
    monkeypatch.setenv('LC_AGENT_MODE', '1')
    monkeypatch.setenv('LC_OID', 'tenant')
    monkeypatch.setenv('LC_AGENT_STATE_DIR', str(tmp_path))
    monkeypatch.setattr('limacharlie.agent_policy.check_permission', lambda _: None)
    monkeypatch.setattr('limacharlie.client.Client', lambda **kwargs: client)
    monkeypatch.setattr('limacharlie.sdk.organization.Organization', lambda _: query._org)
    monkeypatch.setattr('limacharlie.commands.search._get_org', lambda _: query._org)
    monkeypatch.setattr('limacharlie.commands.search.Search', lambda _: query)
    client.request.side_effect = [{'queryId': 'q'}, {'completed': True, 'results': [
        {'type': 'events', 'rows': [], 'nextToken': 'more'}]}, {}]
    result = CliRunner().invoke(cli, ['search', 'run', '--query', '* | NEW_PROCESS', '--start', '1789260000',
                                     '--end', '1789263600', '--max-pages', '1', '--output', 'json'])
    assert result.exit_code == 0, result.output
    response = json.loads(result.stdout)
    assert response['status'] == 'partial' and response['stop_reason'] == 'page_limit'
    assert response['matching_rows_returned'] == 0
    assert response['continuation'] == 'more'
    assert 'receipt_id' not in result.output and 'procedure_required' not in result.output
