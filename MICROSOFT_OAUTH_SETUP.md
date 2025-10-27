# Microsoft OAuth Setup for LimaCharlie CLI

## Problem
When using `limacharlie login --oauth` and selecting Microsoft as the provider, you may encounter this error:

```
We're unable to complete your request
invalid_request: The provided value for the input parameter 'redirect_uri' is not valid.
The expected value is a URI which matches a redirect URI registered for this client application.
```

## Solution
Microsoft OAuth requires redirect URIs to be explicitly whitelisted. You need to add the CLI's localhost redirect URIs to your Microsoft OAuth app configuration.

## Setup Instructions

### Option 1: Configure via Firebase Console (Recommended)

1. Visit [Firebase Console](https://console.firebase.google.com/)
2. Select your LimaCharlie project
3. Go to **Authentication** → **Sign-in method**
4. Click on the **Microsoft** provider
5. Click **Edit** or configure the Microsoft OAuth app settings
6. Add these **5 redirect URIs** to the allowed list (note the `/callback` path):

```
http://localhost:8085/callback
http://localhost:8086/callback
http://localhost:8087/callback
http://localhost:8088/callback
http://localhost:8089/callback
```

7. **Save** the configuration
8. Wait a few minutes for the changes to propagate
9. Try `limacharlie login --oauth` again and select Microsoft when prompted

### Option 2: Configure via Azure Portal (Direct Access)

If you have direct access to the Microsoft OAuth app in Azure:

1. Go to [Azure Portal](https://portal.azure.com/)
2. Navigate to **Azure Active Directory** → **App registrations**
3. Find your LimaCharlie OAuth application
4. Go to **Authentication** section
5. Under **Platform configurations** → **Web** → **Redirect URIs**
6. Add all the localhost URIs listed above
7. Click **Save**

## Why These URIs?

The LimaCharlie CLI uses a local HTTP server to receive OAuth callbacks. It automatically finds an available port from the range 8085-8089 (5 ports total).

By whitelisting these 5 ports, the CLI can work regardless of which specific port is available on your system. If all 5 ports are in use, the CLI will provide clear instructions on how to free one up.

## Verification

After configuring the redirect URIs, test the Microsoft OAuth flow:

```bash
limacharlie login --oauth
```

When prompted, select Microsoft (option 2). You should see:
1. Browser opens to Microsoft login
2. You authenticate with your Microsoft account
3. Browser redirects back to localhost (shows success page)
4. CLI completes authentication and saves credentials

If you have 2FA enabled, you'll also be prompted for your verification code after the OAuth flow.

## Note on Google OAuth

Google OAuth works out of the box without this configuration because Google automatically allows `http://localhost` with any port for development/testing purposes. Microsoft has stricter requirements for security reasons.

## Troubleshooting

**Still getting the error after adding redirect URIs?**
- Wait 5-10 minutes for Azure/Firebase changes to propagate
- Clear your browser cache and try again
- Verify you saved the configuration in both Firebase and Azure
- Check that you added `http://` (not `https://`) for localhost URIs

**Don't have access to Firebase Console?**
- Contact your LimaCharlie administrator
- They need to configure the Microsoft OAuth provider settings

**OAuth works but MFA prompt doesn't appear?**
- This is normal if you don't have 2FA enrolled on your account
- To enable 2FA, go to LimaCharlie web console → Account Settings → Enable MFA
