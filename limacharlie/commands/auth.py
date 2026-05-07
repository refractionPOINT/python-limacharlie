"""Authentication commands for LimaCharlie CLI v2.

Commands for managing credentials, testing authentication, and
switching between organizations and environments.
"""

from __future__ import annotations

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
from ..discovery import register_explain
from ._output_helpers import command_output as _output


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_client(ctx: click.Context, oid_override: str | None = None) -> Client:
    return Client(
        oid=oid_override or ctx.obj.oid,
        environment=ctx.obj.environment,
        print_debug_fn=ctx.obj.debug_fn,
        debug_full_response=ctx.obj.debug_full,
        debug_curl=ctx.obj.debug_curl,
        debug_verbose=ctx.obj.debug_verbose,
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
    persisted in ~/.limacharlie.d/config.yaml (or the legacy ~/.limacharlie)
    and can be organized into named environments for multi-org workflows.
    Use 'limacharlie config show-paths' to see active config locations.
    """


# ---------------------------------------------------------------------------
# login
# ---------------------------------------------------------------------------

_EXPLAIN_LOGIN = """\
Store LimaCharlie credentials on disk so that subsequent CLI invocations
can authenticate automatically.  Credentials are written to
~/.limacharlie.d/config.yaml (or the path in LC_CREDS_FILE) with
file-mode 0600.

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

The credential file (~/.limacharlie.d/config.yaml) is YAML formatted:

    oid: <organization-id>
    api_key: <api-key-uuid>
    uid: <user-id>
    env:
      staging:
        oid: <staging-org-id>
        api_key: <staging-api-key>
      production:
        oid: <prod-org-id>
        api_key: <prod-api-key>

Environment variables for CI/CD (no file write needed):
  LC_OID          - Organization ID
  LC_API_KEY      - API key
  LC_UID          - User ID (optional, for user-scoped keys)
  LC_CREDS_FILE   - Override credential file path
  LC_CURRENT_ENV  - Override active named environment
  LC_EPHEMERAL_CREDS - If set, login refuses to write to disk
"""
register_explain("auth.login", _EXPLAIN_LOGIN)


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
    env_name = environment or ctx.obj.environment or "default"

    if oauth:
        _login_oauth(ctx, oid, env_name, provider, no_browser)
        return

    # API key login. Two valid shapes:
    #   1. --oid + --api-key                — org-scoped key (and optional --uid for service accounts).
    #   2. --uid + --api-key (oid optional) — user-scoped key on a brand-new account with no orgs yet.
    if not api_key:
        click.echo(
            "Error: --api-key is required for API key login.\n"
            "Suggestion: Use --oauth for browser-based OAuth login, or provide --api-key with "
            "either --oid (org-scoped key) or --uid (user-scoped key).",
            err=True,
        )
        ctx.exit(4)
        return

    if not oid and not uid:
        click.echo(
            "Error: provide either --oid (org-scoped key) or --uid (user-scoped key) along with --api-key.\n"
            "Suggestion: --uid is correct for User API Keys generated under your account profile; "
            "--oid is correct for Organization API Keys generated under an org's settings.",
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
                click.echo("Tip: Set a default org with 'limacharlie auth use-org <OID>'.")

    except FirebaseAuthError as e:
        click.echo(f"OAuth authentication failed: {e}", err=True)
        ctx.exit(2)
    except KeyboardInterrupt:
        click.echo("\nAuthentication cancelled.", err=True)
        ctx.exit(1)


# ---------------------------------------------------------------------------
# logout
# ---------------------------------------------------------------------------

_EXPLAIN_LOGOUT = """\
Remove stored credentials from the local configuration file.  By default
the 'default' environment credentials are cleared.  Pass --env to clear
a specific named environment instead.

This does NOT revoke the API key on the server side.  To revoke, use
'limacharlie api-key delete'.
"""
register_explain("auth.logout", _EXPLAIN_LOGOUT)


@group.command()
@click.option(
    "--env", "environment", default=None,
    help="Named environment to clear (default: 'default').",
)
@pass_context
def logout(ctx: click.Context, environment: str | None) -> None:
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

_EXPLAIN_WHOAMI = """\
Display the identity and accessible organizations for the currently
configured credentials.  This calls the /who API endpoint and shows
the result.  Useful for verifying which API key or user account is
active and which organizations it can access.

By default, permissions are omitted to keep the output compact (helpful
for automated / LLM-driven workflows).  Use the flags below to control
permission output:

  --show-perms       Include the full list of permissions in the output.
  --check-perm NAME  Check whether a specific permission is present.
                     Returns {"has_perm": true/false, "perm": "NAME"}.
"""
register_explain("auth.whoami", _EXPLAIN_WHOAMI)


@group.command()
@click.option("--show-perms", is_flag=True, default=False,
              help="Include full permissions in the output.")
@click.option("--check-perm", default=None,
              help="Check for a specific permission and return a boolean result.")
@pass_context
def whoami(ctx: click.Context, show_perms: bool, check_perm: str | None) -> None:
    client = _get_client(ctx)
    # --check-perm requires a real OID — fail early before the fallback.
    if check_perm is not None and client.oid is None:
        raise click.UsageError(
            "--check-perm requires an OID to be specified (use --oid or set the LC_OID environment variable)"
        )
    # whoami works without a specific org — fall back to "-" if no OID resolved.
    if client.oid is None:
        client = _get_client(ctx, oid_override="-")
    org = Organization(client)
    data = org.who_am_i()

    # --check-perm: return a minimal boolean result and exit early.
    if check_perm is not None:
        all_perms: list[str] = []
        raw = data.get("perms", [])
        if isinstance(raw, list):
            all_perms.extend(raw)
        raw_user = data.get("user_perms", {})
        if isinstance(raw_user, dict):
            for v in raw_user.values():
                if isinstance(v, list):
                    all_perms.extend(v)
        _output(ctx, {"perm": check_perm, "has_perm": check_perm in all_perms})
        return

    # Prepend stored credential info like the old CLI did.
    cred_info = {}
    if client.oid:
        cred_info["oid"] = client.oid
    if client.uid:
        cred_info["uid"] = client.uid

    if show_perms:
        # Expand list fields so they display in full
        # instead of being truncated to "[N items]" in table mode.
        for key in ("perms", "user_perms"):
            val = data.get(key)
            if isinstance(val, list):
                data[key] = ", ".join(str(v) for v in val)
            elif isinstance(val, dict):
                # user_perms is {oid: [perms]} — expand each sub-list.
                data[key] = {k: ", ".join(str(p) for p in v) if isinstance(v, list) else v
                             for k, v in val.items()}
    else:
        # Strip permission fields to keep output compact.
        data.pop("perms", None)
        data.pop("user_perms", None)

    merged = {**cred_info, **data}
    _output(ctx, merged)


# ---------------------------------------------------------------------------
# use-org
# ---------------------------------------------------------------------------

_EXPLAIN_USE_ORG = """\
Set the default organization ID (OID) in your credential file so that
subsequent commands do not require --oid on every invocation.  This
updates the 'default' environment (or the environment specified by
--env on the top-level CLI).

If you work with multiple organizations, consider using named
environments instead: 'limacharlie auth login --env prod --oid ... --api-key ...'.
"""
register_explain("auth.use-org", _EXPLAIN_USE_ORG)


@group.command("use-org")
@click.argument("oid")
@pass_context
def use_org(ctx: click.Context, oid: str) -> None:
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

_EXPLAIN_TEST = """\
Test whether the currently configured credentials are valid by attempting
to generate a JWT token.  Returns a success/failure status.  This is a
lightweight check that does not query any org-specific resources, so it
works even if the API key has minimal permissions.
"""
register_explain("auth.test", _EXPLAIN_TEST)


@group.command()
@pass_context
def test(ctx: click.Context) -> None:
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

_EXPLAIN_USE_ENV = """\
Switch the active named environment in the configuration file.  Once
set, subsequent commands will use the credentials from the specified
environment without needing --env on every invocation.  This is
equivalent to setting LC_CURRENT_ENV but persists across shell sessions.

Use 'limacharlie auth list-envs' to see available environments.
"""
register_explain("auth.use-env", _EXPLAIN_USE_ENV)


@group.command("use-env")
@click.argument("name")
@pass_context
def use_env(ctx: click.Context, name: str) -> None:
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

_EXPLAIN_LIST_ENVS = """\
List all named environments configured in the credential file.  Each
environment stores a separate set of credentials (OID, API key, UID).
The 'default' environment is shown if top-level credentials exist.

Use 'limacharlie auth login --env <name>' to create a new environment
and 'limacharlie auth use-env <name>' to switch between them.
"""
register_explain("auth.list-envs", _EXPLAIN_LIST_ENVS)


@group.command("list-envs")
@pass_context
def list_envs(ctx: click.Context) -> None:
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

_EXPLAIN_LIST_ORGS = """\
List all organizations accessible to the current credentials.  This
queries the LimaCharlie API for organizations the authenticated user
or API key can access.  Use --filter to search by name substring.

Unlike 'limacharlie org list', this command does not require an OID
to already be configured, making it useful for initial setup.
"""
register_explain("auth.list-orgs", _EXPLAIN_LIST_ORGS)


@group.command("list-orgs")
@click.option("--filter", "filter_text", default=None, help="Case-insensitive name filter.")
@pass_context
def list_orgs(ctx: click.Context, filter_text: str | None) -> None:
    org = _get_org(ctx)
    data = org.list_accessible_orgs(filter_text=filter_text)

    orgs = data.get("orgs", [])
    names = data.get("names", {})
    result = [{"oid": oid, "name": names.get(oid, "")} for oid in orgs]
    _output(ctx, result)


# ---------------------------------------------------------------------------
# signup
# ---------------------------------------------------------------------------

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
register_explain("auth.signup", _EXPLAIN_SIGNUP)


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
        client = Client(environment=env_name if env_name != "default" else None, print_debug_fn=ctx.obj.debug_fn, debug_full_response=ctx.obj.debug_full, debug_curl=ctx.obj.debug_curl, debug_verbose=ctx.obj.debug_verbose)
        client.refresh_jwt(oid_override="-")
    except Exception as e:
        click.echo(f"Error: Failed to obtain API token: {e}", err=True)
        click.echo(
            "Your OAuth credentials have been saved. You can create an org "
            "later via the web UI and set it with 'limacharlie auth use-org <OID>'.",
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
            "later via the web UI and set it with 'limacharlie auth use-org <OID>'.",
            err=True,
        )
        ctx.exit(5)
        return

    if chosen_oid:
        write_credentials(env_name, oid=chosen_oid, api_key=None)
        if not ctx.obj.quiet:
            click.echo(f"Organization created: {chosen_oid}")
            click.echo(f"\nAll set! Credentials saved for environment '{env_name}'.")


# ---------------------------------------------------------------------------
# get-token
# ---------------------------------------------------------------------------

_EXPLAIN_GET_TOKEN = """\
Generate a JWT token with optional custom expiry for long-running
operations. By default, JWT tokens expire after ~1 hour. For operations
like search download jobs or long search queries, you can generate a
token with a longer validity period.

Use --hours to set the validity duration. Use --format to choose between
raw token output (default) or JSON with metadata.

Examples:
  limacharlie auth get-token --hours 8
  limacharlie auth get-token --hours 8 --format json
"""
register_explain("auth.get-token", _EXPLAIN_GET_TOKEN)


@group.command("get-token")
@click.option(
    "--hours", type=float, default=1.0,
    help="Token validity duration in hours (default: 1). "
         "For long search queries, use 4-8 hours.",
)
@click.option(
    "--format", "output_format", type=click.Choice(["raw", "json"]),
    default="raw",
    help="Output format: 'raw' prints just the token, 'json' includes metadata.",
)
@pass_context
def get_token(ctx: click.Context, hours: float, output_format: str) -> None:
    """Generate a JWT with custom expiry for long-running operations."""
    import json as json_mod
    import time as time_mod
    from datetime import datetime, timezone

    if hours > 24:
        click.echo(
            f"Warning: generating a token valid for {hours} hours. "
            "Long-lived tokens increase security exposure if leaked.",
            err=True,
        )

    client = _get_client(ctx)
    # Compute expiry timestamp before generating the token so the displayed
    # value closely matches the actual JWT expiry (avoids time skew).
    expiry_ts = int(time_mod.time()) + int(hours * 3600)
    token = client.get_jwt(expiry_hours=hours)

    if output_format == "json":
        expiry_iso = datetime.fromtimestamp(expiry_ts, tz=timezone.utc).isoformat()
        data = {
            "token": token,
            "expiry": expiry_ts,
            "expiry_iso": expiry_iso,
            "valid_hours": hours,
            "oid": client.oid,
        }
        click.echo(json_mod.dumps(data, indent=2))
    else:
        click.echo(token)
