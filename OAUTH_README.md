# LimaCharlie OAuth Authentication

This document describes the OAuth authentication feature for the LimaCharlie CLI.

## Overview

The LimaCharlie CLI supports OAuth authentication as an alternative to API keys. This allows users to authenticate using their Google or Microsoft account through a browser-based flow.

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
1. Prompt you to select your OAuth provider (Google or Microsoft)
2. Open your browser to the selected provider's OAuth page
3. After you authenticate, redirect back to localhost
4. Exchange the authorization code for tokens
5. Store the tokens securely in `~/.limacharlie`

Example:
```
$ limacharlie login --oauth

Select OAuth provider:
  1. Google (default)
  2. Microsoft

Enter your choice [1]: 1
Selected: Google
```

### OAuth Login Without Browser

```bash
limacharlie login --oauth --no-browser
```

This will:
1. Prompt you to select your OAuth provider
2. Print the URL for you to manually open instead of launching the browser

### OAuth Login with Organization ID

```bash
limacharlie login --oauth --oid YOUR-ORG-ID
```

### OAuth Login to Named Environment

```bash
limacharlie login --oauth --environment production
```

## Multi-Factor Authentication (2FA) Support

The CLI fully supports multi-factor authentication for OAuth users. If your account has 2FA enabled in Firebase, you'll be prompted for your second factor after completing the OAuth flow.

### How MFA Works

1. Complete OAuth sign-in with Google/Microsoft
2. If 2FA is enrolled, CLI detects this and prompts for verification
3. Enter your 6-digit code from:
   - Authenticator app (Google Authenticator, Authy, etc.)
   - SMS (if SMS factor is enrolled)
4. CLI verifies the code and completes authentication

### Example MFA Flow

```
$ limacharlie login --oauth

OAuth callback server started on port 8085
Opening browser for authentication...
Waiting for authentication...

Initial OAuth authentication successful.
============================================================
Multi-Factor Authentication Required
============================================================

Your account has 2FA enabled. Please complete verification.

Enrolled authentication factor(s):
  1. My Authenticator (Authenticator app (TOTP))

Enter the 6-digit code from My Authenticator: 123456

Verifying code...
Verification successful!

OAuth credentials saved as default
```

### Enrolling 2FA

To enroll 2FA on your account:
1. Visit the LimaCharlie web console
2. Go to your account settings
3. Enable multi-factor authentication
4. Choose your preferred method (Authenticator app or SMS)
5. Follow the enrollment steps

Once enrolled, all CLI OAuth logins will require your second factor.

### Troubleshooting MFA

**Invalid code errors:**
- Ensure your device time is synchronized (TOTP codes are time-based)
- Double-check you're using the correct authenticator app
- Try generating a new code

**MFA session expired:**
- This occurs if you wait too long between OAuth and MFA verification
- Simply run `limacharlie login --oauth` again

**"MFA required but was not performed" error:**
- Your stored credentials don't have MFA verification
- Re-authenticate: `limacharlie login --oauth`
- This will prompt for your second factor

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
AUTH: OAuth (Provider: google or microsoft)
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
- **MFA tokens**: When you complete MFA verification, the resulting ID token includes the `firebase.sign_in_second_factor` claim, which the JWT generation service verifies on every authentication

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
5. **MFA enforcement**: The JWT generation service enforces server-side MFA verification for accounts with 2FA enabled, preventing authentication bypass

## Troubleshooting

### Browser doesn't open
Use `--no-browser` flag and manually copy/paste the URL

### Port conflicts
The callback server automatically finds a free port from the range 8085-8089. If all 5 ports are in use, you'll get an error message with instructions on how to free up a port using `lsof` (macOS/Linux) or `netstat` (Windows).

### OAuth error: "redirect_uri_mismatch" or "invalid redirect_uri"
If you see errors like:
- `The provided value for the input parameter 'redirect_uri' is not valid` (Microsoft)
- `Error 400: redirect_uri_mismatch` (Google)

**Solution:**
1. The localhost redirect URIs need to be whitelisted in the OAuth provider configuration
2. See the **OAuth Redirect URIs** section above for detailed setup instructions
3. You need to add all 5 redirect URIs with the `/callback` path to **both** Google and Microsoft providers in Firebase Console
4. Format: `http://localhost:8085/callback`, `http://localhost:8086/callback`, etc.
5. This configuration is done in Firebase Console → Authentication → (Google or Microsoft) provider
6. For Microsoft, you may also need to add them in Azure Portal

### Token expired
The CLI automatically refreshes expired tokens. If refresh fails, re-authenticate with `limacharlie login --oauth`

## Implementation Details

The OAuth feature is implemented in:
- `limacharlie/oauth_firebase_simple.py`: Simplified Firebase OAuth flow implementation with MFA detection
- `limacharlie/oauth_mfa.py`: Multi-factor authentication verification logic
- `limacharlie/oauth_simple.py`: Token management utilities
- `limacharlie/oauth_server.py`: Local callback server
- `limacharlie/__main__.py`: CLI command integration with provider selection
- `limacharlie/Manager.py`: Firebase JWT to LimaCharlie JWT exchange with MFA error handling

### Authentication Flow

**Without MFA:**
1. Firebase generates an OAuth URL for the selected provider (Google or Microsoft)
2. User authenticates with their provider account
3. Provider redirects back with authentication response
4. Response is sent to Firebase's signInWithIdp endpoint
5. Firebase returns ID and refresh tokens
6. The Firebase ID token is sent to jwt.limacharlie.io with `fb_auth` parameter
7. jwt.limacharlie.io verifies the Firebase token and returns a LimaCharlie JWT
8. The LimaCharlie JWT is used for API calls

**With MFA:**
1. Steps 1-4 same as above
2. Firebase detects MFA is enrolled and returns `mfaPendingCredential` + `mfaInfo`
3. CLI prompts user for their 6-digit verification code
4. CLI calls `accounts/mfaSignIn:finalize` with code and pending credential
5. Firebase verifies the code and returns ID token with `firebase.sign_in_second_factor` claim
6. This MFA-verified ID token is sent to jwt.limacharlie.io
7. jwt.limacharlie.io verifies both the Firebase token AND the MFA claim
8. LimaCharlie JWT is issued and used for API calls

### OAuth Redirect URIs

The implementation uses localhost redirect URIs with ports 8085-8089 (5 ports total) and the `/callback` path:
- `http://localhost:8085/callback`
- `http://localhost:8086/callback`
- `http://localhost:8087/callback`
- `http://localhost:8088/callback`
- `http://localhost:8089/callback`

The CLI automatically finds an available port from this range. If all 5 ports are in use, it will provide an error with instructions on how to free up a port.

**OAuth Provider Configuration:**

Both Google and Microsoft OAuth providers in Firebase need these redirect URIs configured:

1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Select your project
3. Navigate to **Authentication** → **Sign-in method**
4. For **each provider** (Google and Microsoft):
   - Click on the provider
   - Ensure these **5 redirect URIs** are registered:
     ```
     http://localhost:8085/callback
     http://localhost:8086/callback
     http://localhost:8087/callback
     http://localhost:8088/callback
     http://localhost:8089/callback
     ```
   - Save the configuration

**Microsoft-specific:** You may also need to add these URIs directly in the [Azure Portal](https://portal.azure.com/) under your app's **Authentication** settings if you have direct access to the Microsoft OAuth app.

**Note:** Google OAuth apps configured through Firebase typically auto-allow localhost URIs, but if you're experiencing redirect_uri_mismatch errors, you need to explicitly add these URIs in the Firebase Console.