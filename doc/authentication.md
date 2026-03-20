[Documentation](README.md) > Authentication

# Authentication

Two authentication methods are supported: **API keys** (for automation and CI/CD) and **OAuth** (for interactive use with your Google or Microsoft account).

## New Account Signup

Create a brand new LimaCharlie account and organization directly from the CLI:

```bash
# Sign up with Google (default) -- opens browser for OAuth
limacharlie auth signup

# Sign up with Microsoft
limacharlie auth signup --provider microsoft

# Provide the organization name upfront (non-interactive)
limacharlie auth signup --org-name "My Company"

# Headless environments
limacharlie auth signup --no-browser
```

This performs the full onboarding flow: OAuth authentication, account creation, and organization setup. After signup, the CLI is immediately ready to use.

## API Key Login

Store credentials locally using an [API key](https://docs.limacharlie.io/docs/platform-management-api-keys):

```bash
limacharlie auth login --oid YOUR_ORG_ID --api-key YOUR_API_KEY

# With a user-scoped API key
limacharlie auth login --oid YOUR_ORG_ID --api-key YOUR_API_KEY --uid YOUR_USER_ID

# Store under a named environment
limacharlie auth login --oid YOUR_ORG_ID --api-key YOUR_API_KEY --env staging
```

## OAuth Login (Browser-Based)

Authenticate interactively using your Google or Microsoft identity. This opens a browser window for authentication and supports MFA/2FA.

```bash
# Login with Google (default)
limacharlie auth login --oauth --oid YOUR_ORG_ID

# Login with Microsoft
limacharlie auth login --oauth --oid YOUR_ORG_ID --provider microsoft

# Login without specifying org (set it later with use-org)
limacharlie auth login --oauth

# Headless environments (prints URL instead of opening browser)
limacharlie auth login --oauth --no-browser

# Save to a named environment
limacharlie auth login --oauth --oid YOUR_ORG_ID --env production
```

OAuth tokens are automatically refreshed when they expire.

## Managing Environments

```bash
# List configured environments
limacharlie auth list-envs

# Switch environment
limacharlie auth use-env production

# Set default org (useful after OAuth login without --oid)
limacharlie auth use-org YOUR_ORG_ID

# Check current identity
limacharlie auth whoami

# Test credentials
limacharlie auth test

# List accessible organizations
limacharlie auth list-orgs
```

## Environment Variables

```bash
export LC_OID=your-org-id
export LC_API_KEY=your-api-key
# Optional: user-scoped key
export LC_UID=your-user-id
# Optional: select a named environment
export LC_CURRENT_ENV=staging
```

## Credentials File

Credentials are stored in `~/.limacharlie.d/config.yaml` (YAML, mode 0600):

| Platform | Path |
|----------|------|
| Linux/macOS | `~/.limacharlie.d/config.yaml` |
| Windows | `%APPDATA%\limacharlie\config.yaml` |

```yaml
# Default credentials (API key)
api_key: xxx
oid: xxx
uid: xxx  # optional, for user-scoped keys

# Default credentials (OAuth)
oid: xxx
oauth:
  id_token: xxx
  refresh_token: xxx
  expires_at: 1704067200
  provider: google

# Named environments
env:
  staging:
    api_key: xxx
    oid: xxx
  production:
    oid: xxx
    oauth:
      id_token: xxx
      refresh_token: xxx
      expires_at: 1704067200
      provider: google
```

Other files in the config directory:

| File | Purpose |
|------|---------|
| `config.yaml` | Credentials and environment configuration |
| `jwt_cache.json` | Cached JWT tokens (avoids repeated auth requests) |
| `search_checkpoints/` | Resume state for long-running search queries |

Use `limacharlie config show-paths` to see all resolved paths.

Override the credentials file path with `LC_CREDS_FILE`. Set `LC_EPHEMERAL_CREDS` to prevent any file I/O (for CI/CD).

## Config Directory Migration

Starting with CLI v2 (5.x), configuration files are stored in a dedicated directory (`~/.limacharlie.d/`) instead of the previous flat-file layout (`~/.limacharlie`). If you have existing configuration from an earlier version, the CLI will auto-detect it and print a warning to stderr:

```
Warning: Using legacy config location '/home/user/.limacharlie'.
Run 'limacharlie config migrate' to move to '/home/user/.limacharlie.d/config.yaml'.
```

Migration is intentionally not automatic - you control when it happens.

**To migrate:**

```bash
# Preview what will happen
limacharlie config migrate --dry-run

# Migrate (copies files to new location, keeps old files as backup)
limacharlie config migrate

# Migrate and remove old files
limacharlie config migrate --remove-old
```

**To suppress the warning without migrating:**

```bash
# Option 1: Environment variable (suppresses warning only, keeps new layout resolution)
export LC_NO_MIGRATION_WARNING=1

# Option 2: Force legacy layout entirely (no warning, no new paths)
export LC_LEGACY_CONFIG=1
```

**Useful commands:**

```bash
# See all resolved paths and which layout is active
limacharlie config show-paths

# Clean up old files after a previous migration
limacharlie config migrate --remove-old
```

## JWT Token Caching

The CLI automatically generates short-lived JWT tokens from your API key or OAuth credentials for each API call. To avoid requesting a new JWT on every CLI invocation, tokens are cached to disk in `jwt_cache.json` inside the config directory.

**How it works:**

- On each CLI invocation, the SDK checks if a cached JWT exists for the current credentials.
- A cached JWT is reused if it has more than 10 minutes remaining before expiration.
- If no valid cache entry exists, a fresh JWT is fetched from the server and cached.
- Each credential set (OID + API key, or OID + OAuth refresh token) gets its own cache entry, so multiple environments don't interfere with each other.
- Cache writes are atomic (write to temp file, then rename) to prevent corruption from concurrent CLI invocations.

**Long-lived tokens for search:**

For long-running operations like search queries, you can generate a token with a longer validity period:

```bash
# Generate an 8-hour token for a long search session
limacharlie auth get-token --hours 8

# JSON output with metadata
limacharlie auth get-token --hours 8 --format json
```

**Disabling JWT caching:**

```bash
# Via environment variable
export LC_NO_JWT_CACHE=1

# Via config file (add to config.yaml)
no_jwt_cache: true

# Ephemeral mode disables all disk I/O including JWT cache
export LC_EPHEMERAL_CREDS=1
```

**Clearing the cache:**

The JWT cache is automatically cleared on `auth logout`. To manually clear it, delete the `jwt_cache.json` file from your config directory (use `limacharlie config show-paths` to find it).

## Resolution Order

Credentials are resolved in this order (highest priority first):

1. Explicit parameters passed to `Client()`
2. `LC_OID`, `LC_API_KEY`, `LC_UID` environment variables
3. Named environment from `LC_CURRENT_ENV` (or `default`)
4. Default credentials in config file

## See Also

- [Getting Started](getting-started.md) - Installation and quick start
- [SDK Overview](sdk/README.md) - Using credentials in Python code
