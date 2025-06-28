"""
Firebase Authentication using Google OAuth directly.

This approach uses Google's OAuth flow to get an ID token,
then exchanges it with Firebase's signInWithIdp endpoint.
No client secrets needed in the CLI.
"""

import json
import webbrowser
import urllib.parse
import requests
import time
from typing import Dict, Optional
import secrets
import hashlib
import base64

from .oauth_server import OAuthCallbackServer


class FirebaseAuthError(Exception):
    """Firebase authentication errors."""
    pass


class FirebaseDirectAuth:
    """Direct Firebase authentication without client secrets."""
    
    # Firebase configuration
    FIREBASE_API_KEY = 'AIzaSyB5VyO6qS-XlnVD3zOIuEVNBD5JFn22_1w'
    
    # Google OAuth configuration (Web client, no secret needed for PKCE)
    GOOGLE_CLIENT_ID = '978632190035-65t497hb3126j41in9nh3s7bsh330m1f.apps.googleusercontent.com'
    GOOGLE_AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
    GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token'
    
    # Firebase Auth API endpoint
    SIGN_IN_WITH_IDP = 'https://identitytoolkit.googleapis.com/v1/accounts:signInWithIdp'
    
    def __init__(self):
        """Initialize Firebase auth manager."""
        self.callback_server = None
    
    def start_auth_flow(self, no_browser: bool = False) -> Dict[str, str]:
        """
        Start Google OAuth flow with PKCE, then exchange with Firebase.
        
        Args:
            no_browser: If True, print URL instead of opening browser
            
        Returns:
            Dictionary containing tokens and expiry information
            
        Raises:
            FirebaseAuthError: If authentication fails
        """
        # Start local callback server
        self.callback_server = OAuthCallbackServer()
        port = self.callback_server.start()
        redirect_uri = f'http://localhost:{port}'
        
        print(f"OAuth callback server started on port {port}")
        
        # Generate PKCE parameters
        code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode('utf-8')).digest()
        ).decode('utf-8').rstrip('=')
        
        # Build Google OAuth URL with PKCE
        auth_params = {
            'client_id': self.GOOGLE_CLIENT_ID,
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'scope': 'openid email profile',
            'access_type': 'offline',
            'prompt': 'consent',
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256'
        }
        
        auth_uri = f"{self.GOOGLE_AUTH_URL}?{urllib.parse.urlencode(auth_params)}"
        
        # Open browser or print URL
        if no_browser:
            print(f"\nPlease visit this URL to authenticate:\n{auth_uri}\n")
        else:
            print(f"Opening browser for authentication...")
            if not webbrowser.open(auth_uri):
                print(f"\nCould not open browser. Please visit this URL:\n{auth_uri}\n")
        
        print("Waiting for authentication...")
        
        # Wait for callback
        success, callback_data, error = self.callback_server.wait_for_callback()
        self.callback_server.stop()
        
        if not success:
            raise FirebaseAuthError(f"Authentication failed: {error}")
        
        # Extract authorization code from callback
        auth_code = self._extract_auth_code(callback_data)
        
        # Exchange authorization code for Google tokens using PKCE
        google_tokens = self._exchange_code_for_tokens(auth_code, redirect_uri, code_verifier)
        
        # Exchange Google ID token with Firebase
        return self._exchange_with_firebase(google_tokens['id_token'])
    
    def _extract_auth_code(self, callback_path: str) -> str:
        """
        Extract authorization code from callback URL.
        
        Args:
            callback_path: The callback path with query parameters
            
        Returns:
            The authorization code
            
        Raises:
            FirebaseAuthError: If code not found or error in response
        """
        # Parse query parameters
        parsed = urllib.parse.urlparse(f"http://localhost{callback_path}")
        params = urllib.parse.parse_qs(parsed.query)
        
        # Check for error
        if 'error' in params:
            error = params['error'][0]
            error_desc = params.get('error_description', ['Unknown error'])[0]
            raise FirebaseAuthError(f"OAuth error: {error} - {error_desc}")
        
        # Extract code
        if 'code' not in params:
            raise FirebaseAuthError("No authorization code in callback")
        
        return params['code'][0]
    
    def _exchange_code_for_tokens(self, auth_code: str, redirect_uri: str, code_verifier: str) -> Dict[str, str]:
        """
        Exchange authorization code for Google tokens using PKCE.
        
        Args:
            auth_code: The authorization code
            redirect_uri: The redirect URI used in auth request
            code_verifier: The PKCE code verifier
            
        Returns:
            Dictionary with Google tokens
            
        Raises:
            FirebaseAuthError: If exchange fails
        """
        payload = {
            'code': auth_code,
            'client_id': self.GOOGLE_CLIENT_ID,
            'redirect_uri': redirect_uri,
            'grant_type': 'authorization_code',
            'code_verifier': code_verifier
        }
        
        try:
            response = requests.post(self.GOOGLE_TOKEN_URL, data=payload)
            
            if response.status_code != 200:
                error_data = response.json()
                raise FirebaseAuthError(f"Token exchange failed: {error_data.get('error_description', error_data.get('error', 'Unknown error'))}")
            
            return response.json()
            
        except requests.exceptions.RequestException as e:
            raise FirebaseAuthError(f"Failed to exchange authorization code: {str(e)}")
    
    def _exchange_with_firebase(self, google_id_token: str) -> Dict[str, str]:
        """
        Exchange Google ID token with Firebase.
        
        Args:
            google_id_token: The Google ID token
            
        Returns:
            Dictionary with Firebase tokens
            
        Raises:
            FirebaseAuthError: If exchange fails
        """
        payload = {
            'postBody': f'id_token={google_id_token}&providerId=google.com',
            'requestUri': 'http://localhost',  # Required but not used
            'returnIdpCredential': True,
            'returnSecureToken': True
        }
        
        try:
            response = requests.post(
                f"{self.SIGN_IN_WITH_IDP}?key={self.FIREBASE_API_KEY}",
                json=payload,
                headers={'Content-Type': 'application/json'}
            )
            
            if response.status_code != 200:
                error_data = response.json()
                raise FirebaseAuthError(f"Firebase sign in failed: {error_data.get('error', {}).get('message', 'Unknown error')}")
            
            data = response.json()
            
            # Calculate expiry timestamp
            expires_in = int(data.get('expiresIn', '3600'))
            expires_at = int(time.time()) + expires_in
            
            return {
                'id_token': data['idToken'],
                'refresh_token': data['refreshToken'],
                'expires_at': expires_at,
                'provider': 'google'
            }
            
        except requests.exceptions.RequestException as e:
            raise FirebaseAuthError(f"Failed to exchange with Firebase: {str(e)}")


def perform_firebase_auth(oid: Optional[str] = None, 
                         environment: Optional[str] = None,
                         no_browser: bool = False) -> bool:
    """
    Perform Firebase authentication and save credentials.
    
    Args:
        oid: Organization ID (optional)
        environment: Environment name (optional)
        no_browser: Don't open browser automatically
        
    Returns:
        True if login successful
    """
    try:
        from . import utils
        
        # Initialize Firebase auth
        auth = FirebaseDirectAuth()
        
        # Perform auth flow
        tokens = auth.start_auth_flow(no_browser=no_browser)
        
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
        
        # Save credentials using the same logic as other auth methods
        if environment and environment != 'default':
            # Save to named environment
            if 'env' not in config:
                config['env'] = {}
            config['env'][environment] = oauth_data
            print(f"\nOAuth credentials saved to environment: {environment}")
        else:
            # Save to default
            config.update(oauth_data)
            print("\nOAuth credentials saved as default")
        
        # Write config
        utils.writeCredentialsToConfig(
            environment if environment else 'default',
            oauth_data.get('oid'),
            None,  # No API key
            oauth_creds=oauth_data.get('oauth')
        )
        
        return True
        
    except FirebaseAuthError as e:
        print(f"\nFirebase auth failed: {str(e)}")
        return False
    except Exception as e:
        print(f"\nUnexpected error during authentication: {str(e)}")
        import traceback
        traceback.print_exc()
        return False