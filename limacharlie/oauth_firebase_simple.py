"""
Simplified Firebase Authentication for LimaCharlie CLI.

This implementation uses Firebase's createAuthUri approach which eliminates
the need to manage OAuth provider credentials directly. Instead of handling
Google OAuth ourselves, we let Firebase manage the OAuth flow:

1. Request auth URI from Firebase (createAuthUri) - Firebase generates the 
   proper OAuth URL for the provider
2. User authenticates with the provider (Google) via Firebase's generated URL
3. Provider redirects back with auth response
4. Exchange the response with Firebase (signInWithIdp) to get Firebase tokens

Benefits over direct OAuth implementation:
- No OAuth client secrets needed in our code
- Firebase handles OAuth complexity and provider-specific quirks
- Easy to add support for other providers (GitHub, Apple, etc.)
- More secure - provider tokens never touch our infrastructure
"""

import json
import webbrowser
import urllib.parse
import requests
import time
import os
import select
import sys
from typing import Dict, Optional, Tuple

from .oauth_server import OAuthCallbackServer
from .constants import FIREBASE_API_KEY, EPHEMERAL_CREDS_ENV_VAR
from .oauth_mfa import MFAHandler, FirebaseMFAError


class FirebaseAuthError(Exception):
    """Firebase authentication errors."""
    pass


class SimpleFirebaseAuth:
    """Simplified Firebase authentication without provider secrets.
    
    This class implements the Firebase authentication flow where Firebase
    manages all OAuth provider interactions. We only need the Firebase API key,
    not any OAuth client credentials.
    """
    
    # Firebase configuration - imported from constants
    
    # Firebase Auth API endpoints
    _BASE = "https://identitytoolkit.googleapis.com/v1"
    _CREATE_AUTH_URI = f"{_BASE}/accounts:createAuthUri"
    _SIGN_IN_WITH_IDP = f"{_BASE}/accounts:signInWithIdp"
    _REFRESH = "https://securetoken.googleapis.com/v1/token"
    
    def __init__(self):
        """Initialize Firebase auth manager."""
        self.callback_server = None
    
    def start_auth_flow(self, provider_id: str = "google.com", no_browser: bool = False) -> Dict[str, str]:
        """
        Start OAuth flow using Firebase's createAuthUri.
        
        Args:
            provider_id: OAuth provider ID (e.g., "google.com", "microsoft.com")
            no_browser: If True, print URL instead of opening browser
            
        Returns:
            Dictionary containing tokens and expiry information
            
        Raises:
            FirebaseAuthError: If authentication fails
        """
        # Start local callback server
        self.callback_server = OAuthCallbackServer()
        port = self.callback_server.start()
        
        try:
            redirect_uri = f'http://localhost:{port}/callback'

            print(f"OAuth callback server started on port {port}")
            print(f"Using OAuth provider: {provider_id}")
            
            # Step 1: Get auth URI from Firebase
            session_id, auth_uri = self._create_auth_uri(
                provider_id=provider_id,
                scopes=("openid", "email", "profile"),
                redirect_uri=redirect_uri
            )
            
            if not no_browser and _is_remote_session():
                print("SSH session without a display detected, not opening a browser.")
                no_browser = True

            # Open browser or print URL. When the user signs in from another
            # machine, the redirect to localhost cannot reach this process, so
            # they can paste the redirect URL into the terminal instead.
            allow_paste = no_browser
            if no_browser:
                print(f"\nPlease visit this URL to authenticate:\n{auth_uri}\n")
            else:
                print(f"Opening browser for authentication...")
                if not webbrowser.open(auth_uri):
                    print(f"\nCould not open browser. Please visit this URL:\n{auth_uri}\n")
                    allow_paste = True

            allow_paste = allow_paste and _stdin_can_be_polled()
            if allow_paste:
                print(
                    f"After you sign in, your browser is sent to {redirect_uri}.\n"
                    "If you signed in on another machine (for example over SSH), that page\n"
                    "will not load. That is expected: copy the full URL from the browser's\n"
                    "address bar and paste it here.\n"
                )
                print("Paste the URL and press Enter, or wait for the browser: ", end="", flush=True)
            else:
                print("Waiting for authentication...")

            callback_data = self._wait_for_redirect(allow_paste, redirect_uri)

            # Extract query string from callback
            query_string = self._extract_query_string(callback_data)
            
        finally:
            # Always stop the server
            self.callback_server.stop()
        
        # Step 2: Exchange with Firebase using signInWithIdp
        return self._sign_in_with_idp(redirect_uri, query_string, session_id, provider_id)
    
    def _wait_for_redirect(self, allow_paste: bool, redirect_uri: str) -> str:
        """
        Wait for the provider redirect, either on the local callback server
        or, when allow_paste is set, pasted into the terminal.

        Returns:
            The callback path including its query string.

        Raises:
            FirebaseAuthError: On timeout or a failed callback.
        """
        server = self.callback_server
        reader = _StdinLineReader() if allow_paste else None
        deadline = time.monotonic() + server.timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise FirebaseAuthError("Authentication failed: Authentication timeout")

            if allow_paste:
                # Check the terminal first, then give the server a short turn.
                line = reader.read_line(min(remaining, 0.5))
                if line is not None:
                    if line == "":
                        # stdin closed: stop reading it, keep waiting on the server.
                        allow_paste = False
                    else:
                        path = _parse_pasted_redirect(line)
                        if path is not None:
                            return path
                        if line.strip():
                            print(
                                "That does not look like the sign-in redirect URL. It should start with\n"
                                f"{redirect_uri} and contain 'code='. Try again: ",
                                end="", flush=True,
                            )
                result = server.poll_callback(timeout=0)
            else:
                result = server.poll_callback(timeout=min(remaining, 1.0))

            if result is None:
                continue
            success, callback_data, error = result
            if not success:
                raise FirebaseAuthError(f"Authentication failed: {error}")
            if allow_paste:
                # The prompt is still on screen; end its line.
                print()
            return callback_data

    def _create_auth_uri(self, provider_id: str, scopes: Tuple[str, ...], 
                        redirect_uri: str) -> Tuple[str, str]:
        """
        Get auth URI from Firebase.
        
        Args:
            provider_id: OAuth provider (e.g., "google.com")
            scopes: OAuth scopes to request
            redirect_uri: Local redirect URI
            
        Returns:
            Tuple of (session_id, auth_uri)
            
        Raises:
            FirebaseAuthError: If request fails
        """
        url = f"{self._CREATE_AUTH_URI}?key={FIREBASE_API_KEY}"
        payload = {
            "providerId": provider_id,
            "continueUri": redirect_uri,
            "authFlowType": "CODE_FLOW",
            "oauthScope": " ".join(scopes),
        }
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            return data["sessionId"], data["authUri"]
            
        except requests.exceptions.RequestException as e:
            raise FirebaseAuthError(f"Failed to create auth URI: {str(e)}")
    
    def _extract_query_string(self, callback_path: str) -> str:
        """
        Extract query string from callback URL.
        
        Args:
            callback_path: The callback path with query parameters
            
        Returns:
            The full query string
            
        Raises:
            FirebaseAuthError: If callback data is invalid
        """
        if not callback_path:
            raise FirebaseAuthError("No callback path received")
        
        # Parse the URL to get query string
        parsed = urllib.parse.urlparse(f"http://localhost{callback_path}")
        query_string = parsed.query or parsed.fragment
        
        if not query_string:
            raise FirebaseAuthError("No query parameters in callback")
        
        # Check for error in query
        params = urllib.parse.parse_qs(query_string)
        if 'error' in params:
            error = params['error'][0]
            error_desc = params.get('error_description', ['Unknown error'])[0]
            raise FirebaseAuthError(f"OAuth error: {error} - {error_desc}")
        
        return query_string
    
    def _sign_in_with_idp(self, request_uri: str, query_string: str,
                         session_id: str, provider_id: str) -> Dict[str, str]:
        """
        Exchange provider response with Firebase.

        Args:
            request_uri: The redirect URI used
            query_string: Full query string from provider
            session_id: Session ID from createAuthUri
            provider_id: OAuth provider ID

        Returns:
            Dictionary with Firebase tokens

        Raises:
            FirebaseAuthError: If exchange fails
        """
        url = f"{self._SIGN_IN_WITH_IDP}?key={FIREBASE_API_KEY}"
        payload = {
            "requestUri": request_uri,
            "postBody": query_string,  # Full query from provider redirect
            "sessionId": session_id,
            "returnSecureToken": True,
            "returnIdpCredential": True,
        }

        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()

            data = response.json()

            # Check if MFA is required
            mfa_pending_credential = data.get('mfaPendingCredential')
            mfa_info = data.get('mfaInfo', [])

            if mfa_pending_credential and mfa_info:
                # MFA is required - handle it
                print("\nInitial OAuth authentication successful.")
                return self._handle_mfa_verification(
                    mfa_pending_credential,
                    mfa_info,
                    provider_id,
                    data.get('localId'),
                    data.get('email'),
                )

            # No MFA required - return tokens as normal
            # Calculate expiry timestamp
            expires_in = int(data.get('expiresIn', '3600'))
            expires_at = int(time.time()) + expires_in

            # Extract Firebase UID (localId)
            firebase_uid = data.get('localId')

            result = {
                'id_token': data['idToken'],
                'refresh_token': data['refreshToken'],
                'expires_at': expires_at,
                'provider': provider_id  # Store the actual provider used
            }

            # Include UID if available
            if firebase_uid:
                result['uid'] = firebase_uid

            # Include email if available (used for account signup)
            email = data.get('email')
            if email:
                result['email'] = email

            return result

        except requests.exceptions.RequestException as e:
            raise FirebaseAuthError(f"Failed to sign in with IdP: {str(e)}")

    def _handle_mfa_verification(self, mfa_pending_credential: str,
                                mfa_info: list, provider_id: str,
                                firebase_uid: Optional[str],
                                email: Optional[str] = None) -> Dict[str, str]:
        """
        Handle MFA verification flow after OAuth sign-in.

        Args:
            mfa_pending_credential: The pending credential from signInWithIdp
            mfa_info: List of enrolled MFA factors
            provider_id: OAuth provider ID
            firebase_uid: Firebase user ID
            email: User email from initial signInWithIdp response

        Returns:
            Dictionary with MFA-verified tokens

        Raises:
            FirebaseAuthError: If MFA verification fails
        """
        try:
            # Use MFA handler to complete the verification flow
            tokens = MFAHandler.handle_mfa_flow(mfa_pending_credential, mfa_info)

            # Add provider and UID to the result
            tokens['provider'] = provider_id
            if firebase_uid:
                tokens['uid'] = firebase_uid
            if email:
                tokens['email'] = email

            return tokens

        except FirebaseMFAError as e:
            raise FirebaseAuthError(f"MFA verification failed: {str(e)}")
        except KeyboardInterrupt:
            raise FirebaseAuthError("MFA verification cancelled by user")

    def refresh_id_token(self, refresh_token: str) -> Tuple[str, int]:
        """
        Refresh an expired Firebase ID token.
        
        Args:
            refresh_token: The Firebase refresh token
            
        Returns:
            Tuple of (new_id_token, expires_at_timestamp)
            
        Raises:
            FirebaseAuthError: If refresh fails
        """
        url = f"{self._REFRESH}?key={FIREBASE_API_KEY}"
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        
        try:
            response = requests.post(url, data=payload, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            expires_in = int(data["expires_in"])
            expires_at = int(time.time()) + expires_in - 60  # 60 second buffer
            
            return data["id_token"], expires_at
            
        except requests.exceptions.RequestException as e:
            raise FirebaseAuthError(f"Failed to refresh token: {str(e)}")


def _is_remote_session() -> bool:
    """True when running over SSH with no graphical display to open a browser on."""
    if not (os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_TTY")):
        return False
    return not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _stdin_can_be_polled() -> bool:
    """
    True when stdin can be waited on together with the callback server.

    On Windows, select() only accepts sockets, not stdin, so the paste
    fallback is not offered there.
    """
    if os.name == "nt":
        return False
    stdin = sys.stdin
    if stdin is None or getattr(stdin, "closed", True):
        return False
    try:
        stdin.fileno()
    except (AttributeError, OSError, ValueError):
        return False
    return True


class _StdinLineReader:
    """
    Reads stdin lines without blocking, so the wait can also watch the
    callback server.

    Reads the raw file descriptor rather than sys.stdin: sys.stdin buffers
    ahead, and select() cannot see lines already sitting in that buffer.
    """

    def __init__(self):
        self._fd = sys.stdin.fileno()
        self._buf = b""
        self._eof = False

    def read_line(self, timeout: float) -> Optional[str]:
        """
        Return the next line if one is ready within ``timeout`` seconds.

        Returns:
            None if nothing is ready, "" at end of input, else the line
            (a blank line is returned as " ").
        """
        if b"\n" not in self._buf and not self._eof:
            try:
                ready, _, _ = select.select([self._fd], [], [], timeout)
                if ready:
                    chunk = os.read(self._fd, 65536)
                    if chunk:
                        self._buf += chunk
                    else:
                        self._eof = True
            except (OSError, ValueError):
                self._eof = True
        if b"\n" in self._buf:
            line, self._buf = self._buf.split(b"\n", 1)
        elif self._eof and self._buf:
            line, self._buf = self._buf, b""
        elif self._eof:
            return ""
        else:
            return None
        text = line.decode("utf-8", errors="replace")
        return text if text.strip() else " "


def _parse_pasted_redirect(text: str) -> Optional[str]:
    """
    Turn a pasted redirect URL into the callback path the server would see.

    Accepts the full URL from the browser address bar, the path, or the bare
    query string. Returns None when the text does not carry an OAuth
    response (no 'code' or 'error' parameter).
    """
    text = text.strip().strip("'\"")
    if not text:
        return None
    if "://" in text or text.startswith("/"):
        parsed = urllib.parse.urlparse(text)
        query = parsed.query or parsed.fragment
    else:
        query = text.lstrip("?")
    if not query:
        return None
    params = urllib.parse.parse_qs(query)
    if "code" not in params and "error" not in params:
        return None
    return f"/callback?{query}"


def perform_simple_firebase_auth(oid: Optional[str] = None, 
                                environment: Optional[str] = None,
                                no_browser: bool = False,
                                provider: str = 'google') -> bool:
    """
    Perform simplified Firebase authentication and save credentials.
    
    Args:
        oid: Organization ID (optional)
        environment: Environment name (optional)
        no_browser: Don't open browser automatically
        provider: OAuth provider to use ('google' or 'microsoft')
        
    Returns:
        True if login successful
    """
    try:
        from . import utils
        
        # Initialize Firebase auth
        auth = SimpleFirebaseAuth()
        
        # Map CLI provider names to Firebase provider IDs
        provider_map = {
            'google': 'google.com',
            'microsoft': 'microsoft.com'
        }
        
        # Perform auth flow
        tokens = auth.start_auth_flow(
            provider_id=provider_map[provider],
            no_browser=no_browser
        )
        
        # Load existing config
        config = utils.loadCredentials()
        if config is None:
            config = {}
        
        # Prepare OAuth data
        oauth_data = {
            'oauth': tokens
        }

        # Add OID if provided
        if oid:
            oauth_data['oid'] = oid

        # Extract UID from tokens if available
        uid = tokens.get('uid', '')

        # Save credentials using the same logic as other auth methods
        is_ephemeral = os.environ.get(EPHEMERAL_CREDS_ENV_VAR)

        if environment and environment != 'default':
            # Save to named environment
            if 'env' not in config:
                config['env'] = {}
            config['env'][environment] = oauth_data
            if is_ephemeral:
                print(f"\nOAuth authentication successful (ephemeral mode - not persisted to disk)")
            else:
                print(f"\nOAuth credentials saved to environment: {environment}")
        else:
            # Save to default
            config.update(oauth_data)
            if is_ephemeral:
                print("\nOAuth authentication successful (ephemeral mode - not persisted to disk)")
            else:
                print("\nOAuth credentials saved as default")

        # Write config (will be skipped in ephemeral mode)
        utils.writeCredentialsToConfig(
            environment if environment else 'default',
            oauth_data.get('oid'),
            None,  # No API key
            uid=uid,  # Pass Firebase UID
            oauth_creds=oauth_data.get('oauth')
        )
        
        # Small delay to ensure output is flushed
        time.sleep(1.0)
        
        return True
        
    except FirebaseAuthError as e:
        print(f"\nFirebase auth failed: {str(e)}")
        return False
    except Exception as e:
        print(f"\nUnexpected error during authentication: {str(e)}")
        import traceback
        traceback.print_exc()
        return False