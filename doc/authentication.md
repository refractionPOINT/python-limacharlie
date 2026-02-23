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

Credentials are stored in `~/.limacharlie` (YAML, mode 0600):

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

Override the credentials file path with `LC_CREDS_FILE`. Set `LC_EPHEMERAL_CREDS` to prevent any file I/O (for CI/CD).

## Resolution Order

Credentials are resolved in this order (highest priority first):

1. Explicit parameters passed to `Client()`
2. `LC_OID`, `LC_API_KEY`, `LC_UID` environment variables
3. Named environment from `LC_CURRENT_ENV` (or `default`)
4. Default credentials in `~/.limacharlie`

## See Also

- [Getting Started](getting-started.md) — Installation and quick start
- [SDK Overview](sdk/README.md) — Using credentials in Python code
