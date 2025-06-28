# LimaCharlie OAuth Authentication

This document describes the OAuth authentication feature for the LimaCharlie CLI.

## Overview

The LimaCharlie CLI supports OAuth authentication as an alternative to API keys. This allows users to authenticate using their Google account through a browser-based flow.

## Features

- **Browser-based authentication**: Opens your default browser for secure authentication
- **Automatic token refresh**: Tokens are automatically refreshed when they expire
- **Backward compatibility**: Existing API key authentication continues to work unchanged
- **Multiple environments**: OAuth credentials can be stored per environment
- **Secure credential storage**: OAuth tokens are stored with the same security as API keys

## Usage

### OAuth Login

```bash
limacharlie login --oauth
```

This will:
1. Open your browser to Google's OAuth page
2. After you authenticate, redirect back to localhost  
3. Exchange the authorization code for tokens
4. Store the tokens securely in `~/.limacharlie`

### OAuth Login Without Browser

```bash
limacharlie login --oauth --no-browser
```

This will print the URL for you to manually open instead of launching the browser.

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

### Security

The OAuth implementation uses Google's OAuth 2.0 flow with PKCE (Proof Key for Code Exchange) for enhanced security. Desktop OAuth clients include a "public" client secret as per Google's guidelines for desktop applications.

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
The callback server automatically finds a free port from the range 8085-8089. If all ports are in use, check your firewall settings.

### Token expired
The CLI automatically refreshes expired tokens. If refresh fails, re-authenticate with `limacharlie login --oauth`

## Implementation Details

The OAuth feature is implemented in:
- `limacharlie/oauth_firebase_direct.py`: OAuth flow implementation
- `limacharlie/oauth_server.py`: Local callback server
- `limacharlie/oauth.py`: Token management utilities
- `limacharlie/__main__.py`: CLI command integration
- `limacharlie/Manager.py`: Firebase JWT to LimaCharlie JWT exchange

### Authentication Flow
1. User authenticates with Google OAuth using PKCE flow
2. Google returns an authorization code
3. The code is exchanged for Google tokens
4. Google ID token is sent to Firebase's signInWithIdp endpoint
5. Firebase returns ID and refresh tokens
6. The Firebase ID token is sent to jwt.limacharlie.io with `fb_auth` parameter
7. jwt.limacharlie.io verifies the Firebase token and returns a LimaCharlie JWT
8. The LimaCharlie JWT is used for API calls

### OAuth Redirect URIs
The implementation uses localhost ports 8085-8089 for OAuth callbacks. These URIs are configured in the Google OAuth client settings.