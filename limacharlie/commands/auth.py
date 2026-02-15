"""Authentication commands for LimaCharlie CLI v2.

Commands for managing credentials, testing authentication, and
switching between organizations and environments.
"""

from __future__ import annotations

from typing import Any

import click

from ..cli import pass_context
from ..config import (
    load_config,
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

Two authentication methods are supported:

  API Key:   limacharlie auth login --oid <OID> --api-key <KEY>
  OAuth:     limacharlie auth login --oauth [--oid <OID>]

For API key login, supply --oid and --api-key.  If you are using a
user-scoped API key, also pass --uid.

For OAuth login, pass --oauth to authenticate via your browser using
Google or Microsoft.  Use --provider to choose (default: google).
Use --no-browser for headless environments (prints the URL instead).
The --oid flag is optional with OAuth and can be set later via
'limacharlie auth use-org'.

Use --env to store credentials under a named environment so you can
switch between multiple orgs or accounts.

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

_EXPLAIN_USE_ENV = """\
Switch the active named environment in the configuration file.  Once
set, subsequent commands will use the credentials from the specified
environment without needing --env on every invocation.  This is
equivalent to setting LC_CURRENT_ENV but persists across shell sessions.

Use 'limacharlie auth list-envs' to see available environments.
"""

_EXPLAIN_LIST_ENVS = """\
List all named environments configured in the credential file.  Each
environment stores a separate set of credentials (OID, API key, UID).
The 'default' environment is shown if top-level credentials exist.

Use 'limacharlie auth login --env <name>' to create a new environment
and 'limacharlie auth use-env <name>' to switch between them.
"""

_EXPLAIN_LIST_ORGS = """\
List all organizations accessible to the current credentials.  This
queries the LimaCharlie API for organizations the authenticated user
or API key can access.  Use --filter to search by name substring.

Unlike 'limacharlie org list', this command does not require an OID
to already be configured, making it useful for initial setup.
"""

_EXPLAIN_SIGNUP = """\
Create a brand new LimaCharlie account through OAuth, directly from
the CLI.  This command performs the full onboarding flow:

  1. Authenticate via browser-based OAuth (Google or Microsoft).
  2. Create a LimaCharlie user profile.
  3. Create a new organization.
  4. Save credentials so the CLI is ready to use.

If you already have an account, use 'limacharlie auth login --oauth'
instead.

Examples:
  limacharlie auth signup
  limacharlie auth signup --provider microsoft
  limacharlie auth signup --org-name "My Company"
  limacharlie auth signup --no-browser
"""

register_explain("auth.login", _EXPLAIN_LOGIN)
register_explain("auth.logout", _EXPLAIN_LOGOUT)
register_explain("auth.whoami", _EXPLAIN_WHOAMI)
register_explain("auth.use-org", _EXPLAIN_USE_ORG)
register_explain("auth.test", _EXPLAIN_TEST)
register_explain("auth.use-env", _EXPLAIN_USE_ENV)
register_explain("auth.list-envs", _EXPLAIN_LIST_ENVS)
register_explain("auth.list-orgs", _EXPLAIN_LIST_ORGS)
register_explain("auth.signup", _EXPLAIN_SIGNUP)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _output(ctx: click.Context, data: Any) -> None:
    fmt = ctx.obj.output_format or detect_output_format()
    if not ctx.obj.quiet:
        click.echo(format_output(data, fmt))


def _get_client(ctx: click.Context, oid_override: str | None = None) -> Client:
    return Client(
        oid=oid_override or ctx.obj.oid,
        environment=ctx.obj.environment,
    )


def _get_org(ctx: click.Context) -> Organization:
    client = _get_client(ctx)
    return Organization(client)


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------

@click.group("auth")
def group() -> None:
    """Manage authentication credentials and identity.

    Store, test, and switch LimaCharlie credentials.  Credentials are
    persisted in ~/.limacharlie and can be organized into named
    environments for multi-org workflows.
    """


# ---------------------------------------------------------------------------
# login
# ---------------------------------------------------------------------------

@group.command()
@click.option("--oid", default=None, help="Organization ID (UUID).")
@click.option("--api-key", default=None, help="API key (UUID).")
@click.option(
    "--env", "environment", default=None,
    help="Named environment to store credentials under (default: 'default').",
)
@click.option("--uid", default=None, help="User ID for user-scoped API keys.")
@click.option("--oauth", is_flag=True, default=False, help="Authenticate via browser-based OAuth (Google or Microsoft).")
@click.option(
    "--provider", type=click.Choice(["google", "microsoft"], case_sensitive=False),
    default="google", help="OAuth provider (default: google). Only used with --oauth.",
)
@click.option("--no-browser", is_flag=True, default=False, help="Print the OAuth URL instead of opening a browser. Only used with --oauth.")
@pass_context
def login(ctx: click.Context, oid: str | None, api_key: str | None, environment: str | None, uid: str | None, oauth: bool, provider: str, no_browser: bool) -> None:
    """Store credentials in the local configuration file.

    Supports two authentication methods:

    \b
    API Key:
        limacharlie auth login --oid <OID> --api-key <KEY>

    \b
    OAuth (browser-based):
        limacharlie auth login --oauth
        limacharlie auth login --oauth --oid <OID>
        limacharlie auth login --oauth --provider microsoft
        limacharlie auth login --oauth --no-browser
    """
    env_name = environment or ctx.obj.environment or "default"

    if oauth:
        _login_oauth(ctx, oid, env_name, provider, no_browser)
    else:
        if not oid or not api_key:
            click.echo(
                "Error: --oid and --api-key are required for API key login.\n"
                "Suggestion: Use --oauth for browser-based OAuth login, or provide both --oid and --api-key.",
                err=True,
            )
            ctx.exit(4)
            return
        write_credentials(env_name, oid=oid, api_key=api_key, uid=uid or "")
        if not ctx.obj.quiet:
            click.echo(f"Credentials saved for environment '{env_name}'.")


def _login_oauth(ctx: click.Context, oid: str | None, env_name: str, provider: str, no_browser: bool) -> None:
    """Perform OAuth login via browser."""
    try:
        from ..oauth_firebase_simple import SimpleFirebaseAuth, FirebaseAuthError
    except ImportError as e:
        click.echo(
            f"Error: OAuth dependencies not available: {e}\n"
            "Suggestion: Install the 'requests' package: pip install requests",
            err=True,
        )
        ctx.exit(1)
        return

    try:
        auth = SimpleFirebaseAuth()
        provider_map = {"google": "google.com", "microsoft": "microsoft.com"}

        tokens = auth.start_auth_flow(
            provider_id=provider_map[provider],
            no_browser=no_browser,
        )

        firebase_uid = tokens.pop("uid", None)
        tokens.pop("email", None)  # Not needed for auth persistence
        write_credentials(
            env_name,
            oid=oid,
            api_key=None,
            uid=firebase_uid or "",
            oauth_creds=tokens,
        )

        # Clear any stale API key from the config so it doesn't
        # shadow the new OAuth credentials.
        config = load_config() or {}
        if env_name == "default" or env_name is None:
            if config.pop("api_key", None) is not None:
                save_config(config)
        else:
            env_data = config.get("env", {}).get(env_name, {})
            if env_data.pop("api_key", None) is not None:
                save_config(config)

        if not ctx.obj.quiet:
            click.echo(f"OAuth credentials saved for environment '{env_name}'.")
            if not oid:
                click.echo("Tip: Set a default org with 'limacharlie auth use-org --oid <OID>'.")

    except FirebaseAuthError as e:
        click.echo(f"OAuth authentication failed: {e}", err=True)
        ctx.exit(2)
    except KeyboardInterrupt:
        click.echo("\nAuthentication cancelled.", err=True)
        ctx.exit(1)


# ---------------------------------------------------------------------------
# logout
# ---------------------------------------------------------------------------

@group.command()
@click.option(
    "--env", "environment", default=None,
    help="Named environment to clear (default: 'default').",
)
@pass_context
def logout(ctx: click.Context, environment: str | None) -> None:
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
@pass_context
def whoami(ctx: click.Context) -> None:
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
@pass_context
def use_org(ctx: click.Context, oid: str) -> None:
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
@pass_context
def test(ctx: click.Context) -> None:
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


# ---------------------------------------------------------------------------
# use-env
# ---------------------------------------------------------------------------

@group.command("use-env")
@click.argument("name")
@pass_context
def use_env(ctx: click.Context, name: str) -> None:
    """Switch the active named environment.

    Example:
        limacharlie auth use-env production
        limacharlie auth use-env staging
    """
    config = load_config() or {}

    # Verify the environment exists
    available = list(config.get("env", {}).keys())
    if config.get("oid") or config.get("api_key") or config.get("oauth"):
        available.insert(0, "default")

    if name not in available:
        click.echo(f"Environment '{name}' not found.  Available: {', '.join(available) or '(none)'}", err=True)
        ctx.exit(1)
        return

    config["current_env"] = name
    save_config(config)
    if not ctx.obj.quiet:
        click.echo(f"Switched to environment '{name}'.")


# ---------------------------------------------------------------------------
# list-envs
# ---------------------------------------------------------------------------

@group.command("list-envs")
@pass_context
def list_envs(ctx: click.Context) -> None:
    """List configured environments.

    Example:
        limacharlie auth list-envs
    """
    envs = list_environments()
    if not envs:
        if not ctx.obj.quiet:
            click.echo("No environments configured.")
        return

    config = load_config() or {}
    current = config.get("current_env", "default")

    result = []
    for env_name in envs:
        entry = {"name": env_name, "active": env_name == current}
        result.append(entry)
    _output(ctx, result)


# ---------------------------------------------------------------------------
# list-orgs
# ---------------------------------------------------------------------------

@group.command("list-orgs")
@click.option("--filter", "filter_text", default=None, help="Case-insensitive name filter.")
@pass_context
def list_orgs(ctx: click.Context, filter_text: str | None) -> None:
    """List organizations accessible to the current credentials.

    Example:
        limacharlie auth list-orgs
        limacharlie auth list-orgs --filter production
    """
    org = _get_org(ctx)
    data = org.list_accessible_orgs(filter_text=filter_text)

    orgs = data.get("orgs", [])
    names = data.get("names", {})
    result = [{"oid": oid, "name": names.get(oid, "")} for oid in orgs]
    _output(ctx, result)


# ---------------------------------------------------------------------------
# signup
# ---------------------------------------------------------------------------

@group.command()
@click.option(
    "--provider", type=click.Choice(["google", "microsoft"], case_sensitive=False),
    default="google", help="OAuth provider (default: google).",
)
@click.option("--no-browser", is_flag=True, default=False, help="Print the OAuth URL instead of opening a browser.")
@click.option("--org-name", default=None, help="Create a new organization with this name.")
@click.option(
    "--env", "environment", default=None,
    help="Named environment to store credentials under (default: 'default').",
)
@pass_context
def signup(ctx: click.Context, provider: str, no_browser: bool, org_name: str | None, environment: str | None) -> None:
    """Create a new LimaCharlie account and set up an organization.

    Performs the full onboarding flow: OAuth authentication, account
    creation, and optional organization setup.

    \b
    Examples:
        limacharlie auth signup
        limacharlie auth signup --provider microsoft
        limacharlie auth signup --org-name "My Company"
    """
    env_name = environment or ctx.obj.environment or "default"

    # ------------------------------------------------------------------
    # Step 1: OAuth authentication
    # ------------------------------------------------------------------
    try:
        from ..oauth_firebase_simple import SimpleFirebaseAuth, FirebaseAuthError
    except ImportError as e:
        click.echo(
            f"Error: OAuth dependencies not available: {e}\n"
            "Suggestion: Install the 'requests' package: pip install requests",
            err=True,
        )
        ctx.exit(1)
        return

    try:
        auth = SimpleFirebaseAuth()
        provider_map = {"google": "google.com", "microsoft": "microsoft.com"}

        if not ctx.obj.quiet:
            click.echo("Step 1/3: Authenticating via OAuth...")

        tokens = auth.start_auth_flow(
            provider_id=provider_map[provider],
            no_browser=no_browser,
        )
    except FirebaseAuthError as e:
        click.echo(f"OAuth authentication failed: {e}", err=True)
        ctx.exit(2)
        return
    except KeyboardInterrupt:
        click.echo("\nAuthentication cancelled.", err=True)
        ctx.exit(1)
        return

    email = tokens.get("email")
    if not email:
        click.echo(
            "Error: Could not retrieve email from OAuth provider.\n"
            "The OAuth provider did not return an email address.",
            err=True,
        )
        ctx.exit(3)
        return

    # ------------------------------------------------------------------
    # Step 2: Create user profile (idempotent)
    # ------------------------------------------------------------------
    if not ctx.obj.quiet:
        click.echo(f"Step 2/3: Setting up user profile for {email}...")

    from ..signup import signup_user, SignupError
    try:
        signup_user(tokens["id_token"], email)
    except SignupError as e:
        click.echo(f"Warning: Account setup returned an error: {e}", err=True)
        click.echo("Continuing -- the account may already exist.", err=True)

    # ------------------------------------------------------------------
    # Step 3: Save credentials and create organization
    # ------------------------------------------------------------------
    if not ctx.obj.quiet:
        click.echo("Step 3/3: Creating organization...")

    # Save OAuth credentials (no OID yet).
    firebase_uid = tokens.pop("uid", None)
    # Remove email from tokens before saving -- it's not needed for auth.
    tokens.pop("email", None)
    write_credentials(env_name, oid=None, api_key=None, uid=firebase_uid or "", oauth_creds=tokens)

    # Prompt for org name if not provided.
    if not org_name:
        org_name = click.prompt("Enter a name for your new organization")

    # Build a Client from the just-saved credentials so we can talk to
    # the API.  Use oid="-" to get a minimal JWT (no org context).
    try:
        client = Client(environment=env_name if env_name != "default" else None)
        client.refresh_jwt(oid_override="-")
    except Exception as e:
        click.echo(f"Error: Failed to obtain API token: {e}", err=True)
        click.echo(
            "Your OAuth credentials have been saved. You can create an org "
            "later via the web UI and set it with 'limacharlie auth use-org --oid <OID>'.",
            err=True,
        )
        ctx.exit(4)
        return

    if not ctx.obj.quiet:
        click.echo(f"Creating organization '{org_name}'...")

    try:
        resp = Organization.create_org(client, name=org_name, location="auto")
        chosen_oid = resp.get("oid")
    except Exception as e:
        click.echo(f"Error creating organization: {e}", err=True)
        click.echo(
            "Your OAuth credentials have been saved. You can create an org "
            "later via the web UI and set it with 'limacharlie auth use-org --oid <OID>'.",
            err=True,
        )
        ctx.exit(5)
        return

    if chosen_oid:
        write_credentials(env_name, oid=chosen_oid, api_key=None)
        if not ctx.obj.quiet:
            click.echo(f"Organization created: {chosen_oid}")
            click.echo(f"\nAll set! Credentials saved for environment '{env_name}'.")
