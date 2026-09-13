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


def test_read_executes_first_time_without_receipts_and_rechecks_permission(agent, tmp_path):
    command = click.Command('list', callback=Mock(side_effect=lambda: click.echo('{"sensors": []}')))
    callback = command.callback
    policy.instrument(command)
    root = click.Group('test', commands={'sensor': click.Group('sensor', commands={'list': command})})
    for _ in range(2):
        result = CliRunner().invoke(root, ['sensor', 'list'], obj=LimaCharlieContext())
        assert result.exit_code == 0, result.output
        assert json.loads(result.output) == {'sensors': []}
    assert callback.call_count == 2
    assert agent.who_am_i.call_count == 2
    assert list(tmp_path.iterdir()) == []
    agent.who_am_i.return_value = {'perms': []}
    result = CliRunner().invoke(root, ['sensor', 'list'], obj=LimaCharlieContext())
    assert result.exit_code != 0 and 'ai_agent.operate' in result.output
    assert callback.call_count == 2


@pytest.mark.parametrize('path', [('org', 'list'), ('auth', 'list-orgs'), ('auth', 'whoami')])
def test_identity_discovery_without_oid(agent, monkeypatch, path):
    monkeypatch.delenv('LC_OID')
    callback = Mock(side_effect=lambda: click.echo('{"identity": "user"}'))
    command = click.Command(path[1], callback=callback)
    policy.instrument(command)
    root = click.Group('test', commands={path[0]: click.Group(path[0], commands={path[1]: command})})
    result = CliRunner().invoke(root, list(path), obj=LimaCharlieContext())
    assert result.exit_code == 0, result.output
    callback.assert_called_once()
    agent.who_am_i.assert_not_called()


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



@pytest.mark.parametrize('command', [['dr', 'deploy'], ['org', 'list']])
def test_ai_help_preserves_choices_and_negative_flags(agent, command):
    result = CliRunner().invoke(cli, command + ['--ai-help'])
    assert result.exit_code == 0, result.output
    if command == ['dr', 'deploy']:
        assert '--disabled' in result.output
        assert 'general, managed, service' in result.output


def test_binary_and_streaming_output_not_replaced(agent):
    import sys
    command = click.Command('list', callback=lambda: sys.stdout.buffer.write(b'\x00\xffpayload'))
    policy.instrument(command)
    root = click.Group('test', commands={'sensor': click.Group('sensor', commands={'list': command})})
    result = CliRunner().invoke(root, ['sensor', 'list'], obj=LimaCharlieContext())
    assert result.exit_code == 0
    assert result.stdout_bytes == b'\x00\xffpayload'
