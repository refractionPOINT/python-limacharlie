"""Per-user-turn CLI drafting guardrail, not an arbitrary-code sandbox.

The runner clears this only on a new user prompt. Preparation activates it;
model tool calls cannot broaden it through a CLI command. Credentials still
need least-privilege permissions for isolation from arbitrary Python/HTTP.
"""
from . import agent_state as state

KEY = 'active-draft-operation'
READS = {
    ('org', 'list'), ('org', 'info'), ('org', 'get'), ('auth', 'whoami'), ('auth', 'list-orgs'),
    ('sensor', 'list'), ('sensor', 'get'), ('sensor', 'info'),
    ('event', 'list'), ('event', 'get'), ('event', 'children'), ('event', 'types'), ('event', 'schema'),
    ('schema', 'list'), ('schema', 'get'), ('ioc', 'search'), ('ioc', 'batch-search'),
    ('dr', 'prepare'), ('dr', 'build'), ('dr', 'check'), ('dr', 'validate'), ('dr', 'test'), ('dr', 'list'), ('dr', 'get'),
    ('sop', 'list'), ('sop', 'get'), ('ai-skill', 'list'), ('ai-skill', 'get'),
}


def activate(oid, workspace):
    with state.database() as db:
        state.save(db, KEY, {'oid': oid, 'workspace': str(workspace)})


def clear():
    # Avoid creating a state DB for ordinary turns that never enter a workflow.
    if not (state.directory() / 'state.sqlite3').exists():
        return
    with state.database() as db:
        db.execute('DELETE FROM records WHERE id=?', (KEY,)); db.commit()


def current():
    if not (state.directory() / 'state.sqlite3').exists():
        return None
    with state.database() as db:
        return state.read(db, KEY)


def validate(path, params, oid):
    active = current()
    if not active or path[0] in {'help', 'completion'}:
        return
    if oid and oid != active['oid']:
        raise ValueError('Drafting is scoped to the prepared organization until the next user request')
    if tuple(path) in READS or tuple(path) == ('dr', 'deploy') and params.get('dry_run'):
        return
    raise ValueError('Active D&R drafting permits stored-evidence reads and local checks only. '
                     'Endpoint tasking, historical scans and remote mutations are outside this workflow. '
                     'Use dr check; a new user request ends the drafting scope.')
