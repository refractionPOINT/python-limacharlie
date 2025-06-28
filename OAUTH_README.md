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

### Basic OAuth Login

```bash
limacharlie login --oauth
```

This will:
1. Start a local HTTP server on a random port
2. Open your browser to the Google OAuth page
3. After authentication, redirect back to the local server
4. Exchange the authorization code for Firebase tokens
5. Store the tokens securely in `~/.limacharlie`

### OAuth Login Without Browser

If you're on a headless system or prefer to copy/paste the URL:

```bash
limacharlie login --oauth --no-browser
```

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

### Optional Environment Variables

If you need to override the default configuration (e.g., for development), you can set:

- `LC_FIREBASE_API_KEY`: Override Firebase Web API key
- `LC_FIREBASE_AUTH_DOMAIN`: Override Firebase auth domain
- `LC_GOOGLE_CLIENT_ID`: Override Google OAuth client ID

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

### Invalid configuration
Ensure the required Firebase environment variables are set correctly

## Implementation Details

The OAuth feature is implemented in:
- `limacharlie/oauth.py`: Main OAuth flow logic
- `limacharlie/oauth_server.py`: Local callback server
- `limacharlie/__main__.py`: CLI command updates
- `limacharlie/Manager.py`: Firebase JWT to LimaCharlie JWT exchange

### Authentication Flow
1. User authenticates with Google via Firebase
2. Firebase returns an ID token and refresh token
3. The Firebase ID token is sent to jwt.limacharlie.io with `fb_auth` parameter
4. jwt.limacharlie.io verifies the Firebase token and returns a LimaCharlie JWT
5. The LimaCharlie JWT is used for API calls

The implementation follows OAuth 2.0 best practices and integrates with Firebase Authentication for token management.