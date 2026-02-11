"""Authentication commands for LimaCharlie CLI v2.

Commands for managing credentials, testing authentication, and
switching between organizations and environments.
"""

import click

from ..cli import pass_context
from ..config import (
    load_config,
    resolve_credentials,
    write_credentials,
    save_config,
    list_environments,
    is_ephemeral,
)
from ..client import Client
from ..sdk.organization import Organization
from ..output import format_output, detect_output_format
from ..discovery import register_explain


# ---------------------------------------------------------------------------
# Explain texts
# ---------------------------------------------------------------------------

_EXPLAIN_LOGIN = """\
Store LimaCharlie credentials on disk so that subsequent CLI invocations
can authenticate automatically.  Credentials are written to ~/.limacharlie
(or the path in LC_CREDS_FILE) with file-mode 0600.

You must supply at least --oid and --api-key.  If you are using a
user-scoped API key, also pass --uid.  Use --env to store credentials
under a named environment so you can switch between multiple orgs or
accounts with 'limacharlie auth use-org' or the LC_CURRENT_ENV
environment variable.

In CI/CD pipelines, prefer setting LC_OID and LC_API_KEY environment
variables instead of calling login.  If LC_EPHEMERAL_CREDS is set,
login will refuse to write to disk.
"""

_EXPLAIN_LOGOUT = """\
Remove stored credentials from the local configuration file.  By default
the 'default' environment credentials are cleared.  Pass --env to clear
a specific named environment instead.

This does NOT revoke the API key on the server side.  To revoke, use
'limacharlie api-key delete'.
"""

_EXPLAIN_WHOAMI = """\
Display the identity, permissions, and accessible organizations for the
currently configured credentials.  This calls the /who API endpoint and
shows the result.  Useful for verifying which API key or user account is
active, what permissions it has, and which organizations it can access.
"""

_EXPLAIN_USE_ORG = """\
Set the default organization ID (OID) in your credential file so that
subsequent commands do not require --oid on every invocation.  This
updates the 'default' environment (or the environment specified by
--env on the top-level CLI).

If you work with multiple organizations, consider using named
environments instead: 'limacharlie auth login --env prod --oid ... --api-key ...'.
"""

_EXPLAIN_TEST = """\
Test whether the currently configured credentials are valid by attempting
to generate a JWT token.  Returns a success/failure status.  This is a
lightweight check that does not query any org-specific resources, so it
works even if the API key has minimal permissions.
"""

register_explain("auth.login", _EXPLAIN_LOGIN)
register_explain("auth.logout", _EXPLAIN_LOGOUT)
register_explain("auth.whoami", _EXPLAIN_WHOAMI)
register_explain("auth.use-org", _EXPLAIN_USE_ORG)
register_explain("auth.test", _EXPLAIN_TEST)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_explain_callback(text):
    """Return a Click callback that prints explain text and exits."""
    def callback(ctx, param, value):
        if value:
            click.echo(text.strip())
            ctx.exit()
    return callback


def _output(ctx, data):
    fmt = ctx.obj.output_format or detect_output_format()
    if not ctx.obj.quiet:
        click.echo(format_output(data, fmt))


def _get_client(ctx, oid_override=None):
    creds = resolve_credentials(
        oid=oid_override or ctx.obj.oid,
        environment=ctx.obj.environment,
    )
    return Client(
        oid=creds["oid"],
        api_key=creds.get("api_key"),
        uid=creds.get("uid"),
    )


def _get_org(ctx):
    client = _get_client(ctx)
    return Organization(client)


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------

@click.group("auth")
def group():
    """Manage authentication credentials and identity.

    Store, test, and switch LimaCharlie credentials.  Credentials are
    persisted in ~/.limacharlie and can be organized into named
    environments for multi-org workflows.
    """


# ---------------------------------------------------------------------------
# login
# ---------------------------------------------------------------------------

@group.command()
@click.option("--oid", required=True, help="Organization ID (UUID).")
@click.option("--api-key", required=True, help="API key (UUID).")
@click.option(
    "--env", "environment", default=None,
    help="Named environment to store credentials under (default: 'default').",
)
@click.option("--uid", default=None, help="User ID for user-scoped API keys.")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_LOGIN),
    help="Show detailed explanation of this command.",
)
@pass_context
def login(ctx, oid, api_key, environment, uid):
    """Store API-key credentials in the local configuration file.

    Example:
        limacharlie auth login --oid <OID> --api-key <KEY>
    """
    env_name = environment or ctx.obj.environment or "default"
    write_credentials(env_name, oid=oid, api_key=api_key, uid=uid or "")
    if not ctx.obj.quiet:
        click.echo(f"Credentials saved for environment '{env_name}'.")


# ---------------------------------------------------------------------------
# logout
# ---------------------------------------------------------------------------

@group.command()
@click.option(
    "--env", "environment", default=None,
    help="Named environment to clear (default: 'default').",
)
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_LOGOUT),
    help="Show detailed explanation of this command.",
)
@pass_context
def logout(ctx, environment):
    """Remove stored credentials from the local configuration file.

    Example:
        limacharlie auth logout
        limacharlie auth logout --env staging
    """
    if is_ephemeral():
        click.echo("Ephemeral mode active -- nothing to clear.", err=True)
        ctx.exit(1)
        return

    env_name = environment or ctx.obj.environment or "default"
    config = load_config() or {}

    if env_name == "default":
        for key in ("oid", "api_key", "uid", "oauth"):
            config.pop(key, None)
    else:
        envs = config.get("env", {})
        envs.pop(env_name, None)

    save_config(config)
    if not ctx.obj.quiet:
        click.echo(f"Credentials removed for environment '{env_name}'.")


# ---------------------------------------------------------------------------
# whoami
# ---------------------------------------------------------------------------

@group.command()
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_WHOAMI),
    help="Show detailed explanation of this command.",
)
@pass_context
def whoami(ctx):
    """Show the current identity and permissions.

    Example:
        limacharlie auth whoami
    """
    org = _get_org(ctx)
    data = org.who_am_i()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# use-org
# ---------------------------------------------------------------------------

@group.command("use-org")
@click.option("--oid", required=True, help="Organization ID to set as default.")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_USE_ORG),
    help="Show detailed explanation of this command.",
)
@pass_context
def use_org(ctx, oid):
    """Set the default organization for subsequent commands.

    Example:
        limacharlie auth use-org --oid <OID>
    """
    env_name = ctx.obj.environment or "default"
    config = load_config() or {}

    if env_name == "default":
        config["oid"] = oid
    else:
        config.setdefault("env", {})
        config["env"].setdefault(env_name, {})
        config["env"][env_name]["oid"] = oid

    save_config(config)
    if not ctx.obj.quiet:
        click.echo(f"Default organization set to {oid} (environment '{env_name}').")


# ---------------------------------------------------------------------------
# test
# ---------------------------------------------------------------------------

@group.command()
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_TEST),
    help="Show detailed explanation of this command.",
)
@pass_context
def test(ctx):
    """Test whether the current credentials are valid.

    Attempts to generate a JWT.  Exits with code 0 on success, 2 on failure.

    Example:
        limacharlie auth test
    """
    try:
        client = _get_client(ctx)
        client.refresh_jwt()
        if not ctx.obj.quiet:
            click.echo("Authentication successful.")
    except Exception as exc:
        if not ctx.obj.quiet:
            click.echo(f"Authentication failed: {exc}", err=True)
        ctx.exit(2)
