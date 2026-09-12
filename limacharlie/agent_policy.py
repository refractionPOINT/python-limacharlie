"""CLI-owned agent workflow policy; not a sandbox for arbitrary local code.

Installed on Click leaf callbacks so options have already been parsed and help
remains offline. Human CLI use is unchanged unless LC_AGENT_MODE=1 is set.
"""
import functools
import json
import os
import uuid

import click

from . import agent_state as state


def enabled():
    return os.environ.get('LC_AGENT_MODE') == '1'


def check_permission(org):
    identity = org.who_am_i()
    perms = identity.get('perms', [])
    if not isinstance(perms, list):
        perms = []
    perms = list(perms)
    for values in identity.get('user_perms', {}).values():
        if isinstance(values, list):
            perms.extend(values)
    if 'ai_agent.operate' not in perms:
        raise ValueError('Identity lacks ai_agent.operate in this organization')


def validate(path, params, options):
    """Validate parsed values, including short flags and --option=value syntax."""
    root, verb = path[0], path[1] if len(path) > 1 else ''
    if options.profile or options.environment or options.debug or options.debug_full or options.debug_curl or options.quiet:
        raise ValueError('Agent credentials and diagnostic output are managed by the session; omit profile/env/debug/quiet')
    if (root == 'auth' and verb not in {'whoami', 'list-orgs'}) or root == 'config':
        raise ValueError('Use the secure account interface to manage session credentials')
    if root == 'dr' and verb in {'set', 'import'}:
        raise ValueError('Use dr deploy with positive and negative fixtures')
    if (root, verb) in {('dr', 'convert-rules'), ('sync', 'push')} and not params.get('dry_run'):
        raise ValueError('Use --dry-run, then deploy individual validated resources')
    hive = params.get('hive_name', '')
    if root == 'hive' and hive in {'dr-general', 'dr-managed', 'dr-service'} and verb in {'set', 'import'}:
        raise ValueError('Use dr deploy for ordinary D&R writes')
    if (root == 'secret' or root == 'hive' and hive == 'secret') and verb in {'get', 'export'}:
        raise ValueError('Secret values must use the secure user interface')
    if root == 'api':
        endpoint = params.get('endpoint', '')
        if (not (endpoint == 'outputs/{oid}' or endpoint.startswith('outputs/{oid}/'))
                or any(c in endpoint for c in ('..', ':', '%', '?', '#', '\\'))
                or params.get('target', 'api') != 'api'
                or any(params.get(k) for k in ('no_auth', 'header', 'include_status', 'silent'))):
            raise ValueError('Agent API fallback only supports scoped outputs/{oid} paths without host/header overrides')


def relevant(path, params):
    from .capabilities import discover
    caps = discover()['capabilities']
    result = {c['id'] for c in caps if any(path[:len(r.split())] == r.split() for r in c['cli_roots'])}
    # Shared administration commands have a primary procedure; load product
    # procedures only when the parsed operation actually targets that product.
    defaults = {'extension': {'extensions'}, 'hive': {'hive-data'},
                'cloudsec': {'cloud-security'}, 'org': {'organization-access'},
                'job': {'endpoint-services'}, 'download': {'sensors-tasking'}}
    if path[0] in defaults:
        result = set(defaults[path[0]])
    if path[:2] == ['cloudsec', 'code']:
        result.add('code-security')
    if path[0] == 'extension':
        name = params.get('name') or params.get('extension_name') or ''
        if name in {'cloudsec', 'ext-cloudsec'}:
            result.add('cloud-security')
        if name in {'mailsec', 'ext-mailsec'}:
            result.add('email-security')
    if path[0] == 'api':
        result.add('outputs')
    if path[0] == 'hive':
        owners = {'dr-mail': ['email-security'], 'cloudsec_policy': ['cloud-security', 'code-security'],
                  'ai_agent': ['ai-agents'], 'ai_skill': ['ai-agents'], 'sop': ['ai-agents'],
                  'org_notes': ['ai-agents'], 'ai_memory': ['ai-agents']}
        result.update(owners.get(params.get('hive_name'), []))
    return sorted(result)


def deliver(org, path, params):
    from .capabilities import discover, ROOT
    fingerprint = state.identifier((ROOT / 'catalog.json').read_text(),
                                   *[p.read_text() for p in sorted((ROOT / 'capabilities').rglob('*.md'))])
    key = state.identifier('guidance', os.environ.get('LC_AI_SESSION_ID', ''), org.oid, fingerprint)
    with state.resource_lock(key), state.database() as db:
        previous = state.read(db, key) or {'capabilities': [], 'indexes': False}
        missing = set(relevant(path, params)) - set(previous['capabilities'])
        if not missing and previous['indexes']:
            return
        response = {'status': 'procedure_required', 'org_id': org.oid,
                    'instructions': [discover(i) for i in sorted(missing)],
                    'next': 'Read this guidance, then rerun the same command. No requested operation was executed.'}
        if not previous['indexes']:
            from .sdk.hive import Hive
            response['organization_instructions'] = {}
            for hive_name in ('sop', 'ai_skill'):
                try:
                    records = Hive(org, hive_name).list()
                    response['organization_instructions'][hive_name] = {
                        name: {'description': str(rec.data.get('description', ''))[:200] if isinstance(rec.data, dict) else '',
                               'enabled': rec.enabled} for name, rec in list(records.items())[:20]}
                    while len(json.dumps(response['organization_instructions'][hive_name])) > 6000:
                        response['organization_instructions'][hive_name].popitem()
                    if len(records) > len(response['organization_instructions'][hive_name]):
                        response['organization_instructions'][hive_name + '_truncated'] = {
                            'total': len(records), 'next': 'Use list --brief to inspect the remaining instruction index.'}
                except Exception:
                    response['organization_instructions'][hive_name] = {'status': 'unavailable',
                        'next': 'Use the corresponding list --brief command to diagnose; do not assume an empty index.'}
        # Write and flush before recording delivery; a broken output pipe must not acknowledge it.
        click.echo(json.dumps(response), err=True)
        state.save(db, key, {'capabilities': sorted(set(previous['capabilities']) | missing), 'indexes': True})
    raise click.ClickException('procedure_required: read the supplied guidance and rerun')


def invoke(callback, args, kwargs):
    ctx = click.get_current_context()
    chain = []
    cursor = ctx
    while cursor.parent is not None:
        chain.append(cursor.info_name)
        cursor = cursor.parent
    path = list(reversed(chain))
    if path[0] in {'help', 'completion'}:
        return callback(*args, **kwargs)
    try:
        validate(path, ctx.params, ctx.obj)
        from .client import Client
        from .sdk.organization import Organization
        oid = ctx.obj.oid or os.environ.get('LC_OID')
        if not oid:
            raise ValueError('Agent operations require an explicit --oid or LC_OID')
        org = Organization(Client(oid=oid))
        check_permission(org)
        deliver(org, path, ctx.params)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    receipt_id = uuid.uuid4().hex
    receipt = {'id': receipt_id, 'org_id': oid, 'command': path, 'status': 'started'}
    with state.database() as db:
        state.save(db, receipt_id, receipt)
        click.echo(json.dumps({'receipt_id': receipt_id}), err=True)
        try:
            result = bounded_output(callback, args, kwargs, receipt_id, receipt)
        except BaseException:
            receipt['status'] = 'failed_or_unknown'
            state.save(db, receipt_id, receipt)
            raise
        receipt['status'] = 'executed_outcome_unverified'
        state.save(db, receipt_id, receipt)
        return result


def instrument(command):
    if getattr(command, '_agent_instrumented', False):
        return
    command._agent_instrumented = True
    if isinstance(command, click.Group):
        for child in command.commands.values():
            instrument(child)
    elif command.callback:
        original = command.callback
        @functools.wraps(original)
        def wrapped(*args, **kwargs):
            return invoke(original, args, kwargs) if enabled() else original(*args, **kwargs)
        command.callback = wrapped


def permission_aliases(command):
    """Additional deny-policy spellings for semantic commands (never allow grants)."""
    import shlex
    from pathlib import Path
    try:
        words = shlex.split(command)
    except ValueError:
        return []
    if not words or Path(words[0]).name != 'limacharlie':
        return []
    rest = words[1:]
    normalized = []
    i = 0
    while i < len(rest):
        word = rest[i]
        if word in {'--oid', '--output'}:
            i += 2
            continue
        if word.startswith(('--oid=', '--output=')):
            i += 1
            continue
        normalized.append(word)
        i += 1
    aliases = ['limacharlie ' + shlex.join(normalized)]
    if normalized[:2] == ['dr', 'deploy']:
        aliases.append(shlex.join(['limacharlie', 'dr', 'set', *normalized[2:]]))
    return aliases



def bounded_output(callback, args, kwargs, receipt_id, receipt):
    """Spool command output on disk and return a bounded artifact reference."""
    import contextlib
    import sys
    directory = state.directory() / 'artifacts'
    directory.mkdir(mode=0o700, exist_ok=True)
    path = directory / (receipt_id + '.stdout')
    class BinaryWriter:
        def __init__(self, owner):
            self.owner = owner
        def write(self, raw):
            self.owner.binary = True
            return self.owner.write_bytes(raw)
        def flush(self):
            self.owner.flush()
        def isatty(self):
            return False
    class LimitedWriter:
        def __init__(self, handle):
            self.handle, self.count, self.binary = handle, 0, False
            self.buffer = BinaryWriter(self)
        def write_bytes(self, raw):
            self.count += len(raw)
            if self.count > 32 * 1024 * 1024:
                raise ValueError('Command output exceeds 32 MiB; use an output file or narrow the query and reconcile side effects')
            return self.handle.write(raw)
        def write(self, text):
            self.write_bytes(text.encode('utf-8'))
            return len(text)
        def flush(self):
            self.handle.flush()
        def isatty(self):
            return False
        @property
        def encoding(self):
            return 'utf-8'
    with path.open('wb') as handle:
        writer = LimitedWriter(handle)
        try:
            with contextlib.redirect_stdout(writer):
                result = callback(*args, **kwargs)
        finally:
            writer.flush()
            receipt['stdout_artifact'] = str(path.resolve())
            size = path.stat().st_size
            with path.open('rb') as source:
                preview = source.read(16000).decode('utf-8', errors='replace')
            if size <= 16000 and not writer.binary:
                click.echo(preview, nl=False)
            else:
                click.echo(json.dumps({'status': 'output_saved', 'bytes': size,
                    'artifact_path': str(path.resolve()), 'binary': writer.binary,
                    'preview': None if writer.binary else preview,
                    'next': 'Read or query the saved artifact; the preview is incomplete.'}))
    return result
