"""
Firebase Authentication using createAuthUri and signInWithIdp.

This approach lets Firebase handle all OAuth complexity server-side,
no client secrets needed in the CLI.
"""

import json
import webbrowser
import urllib.parse
import requests
import time
from typing import Dict, Optional
import uuid

from .oauth_server import OAuthCallbackServer


class FirebaseAuthError(Exception):
    """Firebase authentication errors."""
    pass


class FirebaseDirectAuth:
    """Direct Firebase authentication without client secrets."""
    
    # Firebase configuration
    FIREBASE_API_KEY = 'AIzaSyB5VyO6qS-XlnVD3zOIuEVNBD5JFn22_1w'
    
    # Firebase Auth API endpoints
    CREATE_AUTH_URI = 'https://identitytoolkit.googleapis.com/v1/accounts:createAuthUri'
    SIGN_IN_WITH_IDP = 'https://identitytoolkit.googleapis.com/v1/accounts:signInWithIdp'
    
    def __init__(self):
        """Initialize Firebase auth manager."""
        self.callback_server = None
        self.session_id = str(uuid.uuid4())
    
    def start_auth_flow(self, no_browser: bool = False) -> Dict[str, str]:
        """
        Start Firebase authentication flow.
        
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
        redirect_uri = f'http://localhost:{port}/auth/handler'
        
        print(f"OAuth callback server started on port {port}")
        
        # Create auth URI with Firebase
        auth_uri = self._create_auth_uri(redirect_uri)
        
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
        
        # The callback should contain the full redirect URL
        # Parse it and sign in with IDP
        return self._sign_in_with_idp(callback_data, redirect_uri)
    
    def _create_auth_uri(self, redirect_uri: str) -> str:
        """
        Create authentication URI using Firebase.
        
        Args:
            redirect_uri: Where to redirect after auth
            
        Returns:
            The auth URI to open in browser
        """
        payload = {
            'identifier': '',  # Can be empty for initial auth
            'continueUri': redirect_uri,
            'providerId': 'google.com',  # Google OAuth provider
            'oauthScope': 'openid email profile',
            'sessionId': self.session_id
        }
        
        try:
            response = requests.post(
                f"{self.CREATE_AUTH_URI}?key={self.FIREBASE_API_KEY}",
                json=payload,
                headers={'Content-Type': 'application/json'}
            )
            
            if response.status_code != 200:
                error_data = response.json()
                error_msg = error_data.get('error', {}).get('message', 'Unknown error')
                raise FirebaseAuthError(f"Failed to create auth URI: {error_msg}\nFull error: {error_data}")
            
            data = response.json()
            return data['authUri']
            
        except requests.exceptions.RequestException as e:
            raise FirebaseAuthError(f"Failed to create auth URI: {str(e)}")
    
    def _sign_in_with_idp(self, callback_url: str, original_redirect_uri: str) -> Dict[str, str]:
        """
        Complete sign in with IDP using the callback data.
        
        Args:
            callback_url: The full callback URL with parameters
            original_redirect_uri: The original redirect URI we requested
            
        Returns:
            Dictionary with tokens
        """
        # Firebase returns the auth response in the URL fragment or query
        # We need to extract it and send it back to Firebase
        
        # The callback URL should contain the OAuth response
        # This might be in fragments (#) or query parameters (?)
        parsed = urllib.parse.urlparse(f"http://localhost{callback_url}")
        
        # Try query parameters first
        params = urllib.parse.parse_qs(parsed.query)
        
        # If we have an auth response, send it to signInWithIdp
        payload = {
            'requestUri': original_redirect_uri,
            'postBody': parsed.query if parsed.query else '',
            'returnSecureToken': True,
            'returnIdpCredential': True
        }
        
        try:
            response = requests.post(
                f"{self.SIGN_IN_WITH_IDP}?key={self.FIREBASE_API_KEY}",
                json=payload,
                headers={'Content-Type': 'application/json'}
            )
            
            if response.status_code != 200:
                error_data = response.json()
                raise FirebaseAuthError(f"Sign in failed: {error_data.get('error', {}).get('message', 'Unknown error')}")
            
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
            raise FirebaseAuthError(f"Failed to sign in with IDP: {str(e)}")


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