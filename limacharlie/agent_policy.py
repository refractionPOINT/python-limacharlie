"""CLI-owned agent workflow policy; not a sandbox for arbitrary local code.

Installed on Click leaf callbacks so options have already been parsed and help
remains offline. Human CLI use is unchanged unless LC_AGENT_MODE=1 is set.
"""
import functools
import os

import click



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
    from .draft_guard import validate as validate_draft
    validate_draft(path, params, options.oid or os.environ.get('LC_OID'))
    root, verb = path[0], path[1] if len(path) > 1 else ''
    if options.profile or options.environment or options.debug or options.debug_full or options.debug_curl or options.quiet:
        raise ValueError('Agent credentials and diagnostic output are managed by the session; omit profile/env/debug/quiet')
    if (root == 'auth' and verb not in {'whoami', 'list-orgs'}) or (root == 'config' and verb != 'show-paths'):
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
        # Discovery and local introspection must work before an organization
        # is selected. Their own commands retain authentication/argument checks.
        context_free = {('org', 'list'), ('org', 'check-name'),
                        ('auth', 'list-orgs'), ('auth', 'whoami'),
                        ('config', 'show-paths'),
                        ('search', 'checkpoints'), ('search', 'checkpoint-show')}
        if tuple(path) not in context_free:
            oid = ctx.obj.oid or os.environ.get('LC_OID')
            if not oid:
                raise ValueError('Select an organization with --oid; use org list to discover accessible organizations')
            check_permission(Organization(Client(oid=oid)))
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    return callback(*args, **kwargs)


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
