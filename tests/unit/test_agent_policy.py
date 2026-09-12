import json
from types import SimpleNamespace
from unittest.mock import Mock

import click
from click.testing import CliRunner
import pytest

from limacharlie import agent_policy as policy, agent_state as state
from limacharlie.cli import cli, LimaCharlieContext
from limacharlie.capabilities import validate_package


@pytest.fixture
def agent(tmp_path, monkeypatch):
    monkeypatch.setenv('LC_AGENT_MODE', '1')
    monkeypatch.setenv('LC_OID', 'tenant-a')
    monkeypatch.setenv('LC_AGENT_STATE_DIR', str(tmp_path))
    org = Mock(oid='tenant-a')
    org.who_am_i.return_value = {'perms': ['ai_agent.operate']}
    monkeypatch.setattr('limacharlie.client.Client', lambda **kwargs: object())
    monkeypatch.setattr('limacharlie.sdk.organization.Organization', lambda _: org)
    monkeypatch.setattr('limacharlie.sdk.hive.Hive', lambda *args: SimpleNamespace(list=lambda: {}))
    return org


def test_packaged_first_level_capabilities_resolve():
    assert validate_package() == {'capabilities': 15, 'command_roots': 55}


def test_first_operation_delivers_procedure_then_executes_and_rechecks_permission(agent):
    command = click.Command('list', callback=Mock(return_value=None))
    callback = command.callback
    policy.instrument(command)
    group = click.Group('sensor', commands={'list': command})
    root = click.Group('test', commands={'sensor': group})
    result = CliRunner().invoke(root, ['sensor', 'list'], obj=LimaCharlieContext())
    assert result.exit_code != 0
    assert 'procedure_required' in result.output
    assert 'Sensors and endpoint tasking' in result.output
    callback.assert_not_called()
    result = CliRunner().invoke(root, ['sensor', 'list'], obj=LimaCharlieContext())
    assert result.exit_code == 0, result.output
    callback.assert_called_once()
    assert agent.who_am_i.call_count == 2
    agent.who_am_i.return_value = {'perms': []}
    result = CliRunner().invoke(root, ['sensor', 'list'], obj=LimaCharlieContext())
    assert result.exit_code != 0
    assert 'ai_agent.operate' in result.output
    callback.assert_called_once()


@pytest.mark.parametrize('path,params', [
    (['dr','set'], {}), (['dr','import'], {}), (['sync','push'], {}),
    (['hive','set'], {'hive_name':'dr-general'}), (['secret','get'], {}),
    (['hive','export'], {'hive_name':'secret'}), (['auth','get-token'], {}),
    (['api'], {'endpoint':'hive/dr-general/{oid}/x'}),
    (['api'], {'endpoint':'outputs/{oid}', 'header':['Authorization: x']}),
    (['api'], {'endpoint':'outputs/{oid}', 'target':'https://example.com'}),
    (['api'], {'endpoint':'outputs/{oid}/../secrets'}),
])
def test_agent_policy_rejects_workflow_bypasses(path, params):
    with pytest.raises(ValueError):
        policy.validate(path, params, LimaCharlieContext())


def test_scoped_output_api_and_dry_run_are_supported():
    policy.validate(['api'], {'endpoint':'outputs/{oid}', 'target':'api'}, LimaCharlieContext())
    policy.validate(['sync','push'], {'dry_run': True}, LimaCharlieContext())


def test_help_is_offline_in_agent_mode(agent):
    for args in [['sensor','list','--ai-help'], ['help','capability','sensors-tasking']]:
        result = CliRunner().invoke(cli, args)
        assert result.exit_code == 0, result.output
    agent.who_am_i.assert_not_called()



def test_large_output_is_durably_saved_without_unbounded_tool_result(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('LC_AGENT_STATE_DIR', str(tmp_path))
    receipt = {}
    policy.bounded_output(lambda: click.echo('x' * 20000), (), {}, 'receipt', receipt)
    response = json.loads(capsys.readouterr().out)
    assert response['status'] == 'output_saved'
    assert len(response['preview']) == 16000
    from pathlib import Path
    assert Path(response['artifact_path']).read_text() == 'x' * 20000 + '\n'


def test_shared_roots_only_load_relevant_product_guidance():
    assert policy.relevant(['extension', 'list'], {}) == ['extensions']
    assert policy.relevant(['hive', 'list'], {}) == ['hive-data']
    assert policy.relevant(['cloudsec', 'code', 'list'], {}) == ['cloud-security', 'code-security']
    assert policy.relevant(['hive', 'get'], {'hive_name': 'dr-mail'}) == ['email-security', 'hive-data']
