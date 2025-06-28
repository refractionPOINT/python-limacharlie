# LimaCharlie OAuth Authentication

This document describes the OAuth authentication feature for the LimaCharlie CLI.

## Overview

The LimaCharlie CLI now supports OAuth authentication as an alternative to API keys. This allows users to authenticate using their Google account through a browser-based flow, similar to Firebase CLI and other modern tools.

## Features

- **Browser-based authentication**: Opens your default browser for secure authentication
- **Automatic token refresh**: Tokens are automatically refreshed when they expire
- **Backward compatibility**: Existing API key authentication continues to work unchanged
- **Multiple environments**: OAuth credentials can be stored per environment
- **Secure credential storage**: OAuth tokens are stored with the same security as API keys

## Usage

### OAuth Login (Recommended)

```bash
limacharlie login --oauth
```

This will:
1. Open your browser to Google's OAuth page
2. After you authenticate, redirect back to localhost  
3. Firebase handles the code exchange server-side
4. No client secrets required in the CLI - perfect for public distribution

### OAuth Login Without Browser

```bash
limacharlie login --oauth --no-browser
```

This will print the URL for you to manually open instead of launching the browser.

### OAuth Device Flow (Alternative)

```bash
limacharlie login --device-flow
```

This uses the device flow which:
1. Displays a URL and code
2. You visit the URL and enter the code
3. The CLI polls for completion

### OAuth Login with Organization ID

```bash
limacharlie login --oauth --oid YOUR-ORG-ID
```

### OAuth Login to Named Environment

```bash
limacharlie login --oauth --environment production
```

## Configuration

OAuth credentials are stored in the same configuration file as API keys (`~/.limacharlie`):

```yaml
# Default OAuth credentials
oid: your-org-id
oauth:
  id_token: <firebase-id-token>
  refresh_token: <refresh-token>
  expires_at: <unix-timestamp>
  provider: google

# Named environment with OAuth
env:
  production:
    oid: prod-org-id
    oauth:
      id_token: <token>
      refresh_token: <token>
      expires_at: <timestamp>
      provider: google
```

## Configuration

No configuration is required! The OAuth feature comes pre-configured with LimaCharlie's Firebase project settings.

### Security Note

This CLI implementation does not include any client secrets. The OAuth flow uses PKCE for security, and Firebase handles the code exchange server-side using the client credentials configured in the Firebase Console. This makes the CLI safe for public distribution.

### Optional Environment Variables

If you need to override the default configuration (e.g., for development), you can set:

- `LC_FIREBASE_API_KEY`: Override Firebase Web API key
- `LC_FIREBASE_AUTH_DOMAIN`: Override Firebase auth domain
- `LC_GOOGLE_CLIENT_ID`: Override Google OAuth client ID
- `LC_GOOGLE_CLIENT_SECRET`: Override Google OAuth client secret (desktop apps only)

## Checking Authentication Status

To see your current authentication method and status:

```bash
limacharlie who
```

Output for OAuth authentication:
```
OID: your-org-id
UID: your-user-id
AUTH: OAuth (Provider: google)
TOKEN: Valid for 45 minutes
PERMISSIONS:
  ...
```

## Token Management

- Firebase tokens are automatically refreshed when they expire
- The CLI checks token expiry with a 5-minute buffer
- Firebase ID tokens are exchanged for LimaCharlie JWTs via jwt.limacharlie.io
- The exchange happens automatically on each API call
- Refresh tokens are used to obtain new Firebase ID tokens without re-authentication

## Backward Compatibility

All existing functionality remains unchanged:

### Traditional API Key Login
```bash
limacharlie login
# Or with arguments:
limacharlie login --oid ORG-ID --api-key YOUR-KEY
```

### Using API Keys
Organizations using API keys will continue to work without any changes.

## Security Considerations

1. OAuth tokens are stored with the same file permissions (600) as API keys
2. The local callback server only accepts connections from localhost
3. Authorization codes are single-use and expire quickly
4. Refresh tokens should be kept secure as they provide long-term access

## Troubleshooting

### Browser doesn't open
Use `--no-browser` flag and manually copy/paste the URL

### Port conflicts
The callback server automatically finds a free port. If issues persist, check firewall settings.

### Token expired
The CLI automatically refreshes expired tokens. If refresh fails, re-authenticate with `limacharlie login --oauth`

### "OAuth client requires a client secret" error
This error occurs when the Google OAuth client is configured as a "Web application" type. For a public CLI tool, the OAuth client must be configured as a "Desktop" or "Installed" application type in Google Cloud Console. This is a configuration issue that needs to be fixed by the LimaCharlie team.

**Workaround**: Use traditional API key authentication with `limacharlie login` (without --oauth)

### Invalid configuration
Ensure the required Firebase environment variables are set correctly

## Implementation Details

The OAuth feature is implemented in:
- `limacharlie/oauth.py`: Main OAuth flow logic
- `limacharlie/oauth_server.py`: Local callback server
- `limacharlie/__main__.py`: CLI command updates
- `limacharlie/Manager.py`: Firebase JWT to LimaCharlie JWT exchange

### Authentication Flow
1. User authenticates with Google OAuth using PKCE flow (no client secret needed)
2. Google returns an authorization code
3. The authorization code is sent to Firebase's signInWithIdp endpoint
4. Firebase exchanges the code server-side (using stored client credentials)
5. Firebase returns ID and refresh tokens
6. The Firebase ID token is sent to jwt.limacharlie.io with `fb_auth` parameter
7. jwt.limacharlie.io verifies the Firebase token and returns a LimaCharlie JWT
8. The LimaCharlie JWT is used for API calls

### OAuth Redirect URIs
The OAuth implementation uses the following redirect URIs (in order of preference):
- `http://localhost:8085`
- `http://localhost:8086`
- `http://localhost:8087`
- `http://localhost:8088`
- `http://localhost:8089`

These URIs must be added to the Google OAuth client's authorized redirect URIs in the Google Cloud Console.

The implementation follows OAuth 2.0 best practices and integrates with Firebase Authentication for token management.