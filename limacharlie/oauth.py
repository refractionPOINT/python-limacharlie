import json
import webbrowser
import urllib.parse
import requests
import time
from typing import Dict, Optional, Tuple
import os
import sys
import hashlib
import base64
import secrets

from .oauth_server import OAuthCallbackServer
from . import utils


class OAuthError(Exception):
    """OAuth-related errors."""
    pass


class OAuthManager:
    """Manages OAuth authentication flow for LimaCharlie CLI."""
    
    # Firebase configuration for LimaCharlie
    # These are public identifiers, not secrets
    FIREBASE_API_KEY = os.environ.get('LC_FIREBASE_API_KEY', 'AIzaSyB5VyO6qS-XlnVD3zOIuEVNBD5JFn22_1w')
    FIREBASE_AUTH_DOMAIN = os.environ.get('LC_FIREBASE_AUTH_DOMAIN', 'refractionpoint-lce.firebaseapp.com')
    
    # OAuth endpoints
    GOOGLE_OAUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
    FIREBASE_TOKEN_EXCHANGE_URL = 'https://identitytoolkit.googleapis.com/v1/accounts:signInWithIdp'
    FIREBASE_REFRESH_URL = 'https://securetoken.googleapis.com/v1/token'
    
    # Use Firebase's hosted auth domain for the flow
    def get_firebase_auth_url(self):
        """Get the Firebase hosted auth URL."""
        return f"https://{self.FIREBASE_AUTH_DOMAIN}/__/auth/handler"
    
    def __init__(self):
        """Initialize OAuth manager."""
        self.callback_server = None
    
    def _generate_pkce_challenge(self) -> Tuple[str, str]:
        """Generate PKCE code verifier and challenge."""
        # Generate a random code verifier
        code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')
        
        # Create the code challenge using SHA256
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode('utf-8')).digest()
        ).decode('utf-8').rstrip('=')
        
        return code_verifier, code_challenge
    
    def start_oauth_flow(self, no_browser: bool = False) -> Dict[str, str]:
        """
        Start the OAuth authentication flow.
        
        Args:
            no_browser: If True, print URL instead of opening browser
            
        Returns:
            Dictionary containing tokens and expiry information
            
        Raises:
            OAuthError: If authentication fails
        """
        # Firebase configuration is now built-in, no need to check
        
        # Generate PKCE parameters
        self.code_verifier, code_challenge = self._generate_pkce_challenge()
        
        # Start local callback server
        self.callback_server = OAuthCallbackServer()
        port = self.callback_server.start()
        redirect_uri = f'http://localhost:{port}'
        
        print(f"OAuth callback server started on port {port}")
        
        # Warn if using non-standard port
        if port not in [8085, 8086, 8087, 8088, 8089]:
            print(f"\nWARNING: Using non-standard port {port} which may not be authorized for OAuth.")
            print("Preferred ports (8085-8089) are in use.")
            print("The authentication may fail with redirect_uri_mismatch error.\n")
        
        # Build OAuth URL with PKCE
        auth_params = {
            'client_id': self._get_google_client_id(),
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'scope': 'openid email profile',
            'access_type': 'offline',
            'prompt': 'consent',  # Ensure we get refresh token
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256'
        }
        
        auth_url = f"{self.GOOGLE_OAUTH_URL}?{urllib.parse.urlencode(auth_params)}"
        
        # Open browser or print URL
        if no_browser:
            print(f"\nPlease visit this URL to authenticate:\n{auth_url}\n")
        else:
            print(f"Opening browser for authentication...")
            if not webbrowser.open(auth_url):
                print(f"\nCould not open browser. Please visit this URL:\n{auth_url}\n")
        
        print("Waiting for authentication...")
        
        # Wait for callback
        success, auth_code, error = self.callback_server.wait_for_callback()
        self.callback_server.stop()
        
        if not success:
            raise OAuthError(f"Authentication failed: {error}")
        
        # Exchange authorization code for tokens (pass the code_verifier for PKCE)
        tokens = self._exchange_code_for_tokens(auth_code, redirect_uri, self.code_verifier)
        
        return tokens
    
    def _get_google_client_id(self) -> str:
        """Get Google OAuth client ID from Firebase config."""
        # This is a public identifier, not a secret
        return os.environ.get('LC_GOOGLE_CLIENT_ID', '978632190035-55qjfjojrf1hg1oauo41r0mv8kdhpluf.apps.googleusercontent.com')
    
    def _exchange_code_for_tokens(self, auth_code: str, redirect_uri: str, code_verifier: str) -> Dict[str, str]:
        """
        Exchange authorization code for Firebase ID token and refresh token.
        
        Args:
            auth_code: Authorization code from OAuth callback
            redirect_uri: Redirect URI used in OAuth flow
            code_verifier: PKCE code verifier
            
        Returns:
            Dictionary with id_token, refresh_token, and expires_in
            
        Raises:
            OAuthError: If token exchange fails
        """
        # First, exchange the authorization code for Google tokens using PKCE
        google_token_url = 'https://oauth2.googleapis.com/token'
        
        google_payload = {
            'code': auth_code,
            'client_id': self._get_google_client_id(),
            'client_secret': '',  # Empty for Desktop OAuth clients
            'redirect_uri': redirect_uri,
            'grant_type': 'authorization_code',
            'code_verifier': code_verifier  # PKCE verifier for additional security
        }
        
        try:
            # Exchange code for Google tokens
            response = requests.post(google_token_url, data=google_payload)
            
            if response.status_code != 200:
                error_data = response.json()
                error_msg = error_data.get('error_description', error_data.get('error', 'Unknown error'))
                
                # Special handling for client_secret error
                if 'client_secret' in error_msg:
                    raise OAuthError(
                        "OAuth client configuration error: This OAuth client requires a client secret.\n"
                        "For a public CLI tool, the OAuth client in Google Cloud Console should be:\n"
                        "1. Type: 'Desktop' or 'Installed' application (not 'Web application')\n"
                        "2. Or use a different authentication method\n\n"
                        "Please contact LimaCharlie support to report this issue."
                    )
                
                raise OAuthError(f"Google token exchange failed: {error_msg}")
            
            google_tokens = response.json()
            id_token = google_tokens.get('id_token')
            
            if not id_token:
                raise OAuthError("No ID token received from Google")
            
            # Now sign in to Firebase with the Google ID token
            firebase_payload = {
                'postBody': f'id_token={id_token}&providerId=google.com',
                'requestUri': 'http://localhost',  # Firebase requires this but doesn't use it
                'returnIdpCredential': True,
                'returnSecureToken': True
            }
            
            response = requests.post(
                f"{self.FIREBASE_TOKEN_EXCHANGE_URL}?key={self.FIREBASE_API_KEY}",
                json=firebase_payload,
                headers={'Content-Type': 'application/json'}
            )
            response.raise_for_status()
            
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
            raise OAuthError(f"Failed to exchange authorization code: {str(e)}")
        except (KeyError, ValueError) as e:
            raise OAuthError(f"Invalid response from token exchange: {str(e)}")
    
    @staticmethod
    def refresh_token(refresh_token: str) -> Dict[str, str]:
        """
        Refresh an expired ID token.
        
        Args:
            refresh_token: The refresh token
            
        Returns:
            Dictionary with new id_token and expires_at
            
        Raises:
            OAuthError: If token refresh fails
        """
        payload = {
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token
        }
        
        try:
            response = requests.post(
                f"{OAuthManager.FIREBASE_REFRESH_URL}?key={OAuthManager.FIREBASE_API_KEY}",
                data=payload,
                headers={'Content-Type': 'application/x-www-form-urlencoded'}
            )
            response.raise_for_status()
            
            data = response.json()
            
            # Calculate new expiry
            expires_in = int(data.get('expires_in', '3600'))
            expires_at = int(time.time()) + expires_in
            
            return {
                'id_token': data['id_token'],
                'expires_at': expires_at
            }
            
        except requests.exceptions.RequestException as e:
            raise OAuthError(f"Failed to refresh token: {str(e)}")
        except (KeyError, ValueError) as e:
            raise OAuthError(f"Invalid response from token refresh: {str(e)}")
    
    @staticmethod
    def is_token_expired(expires_at: int) -> bool:
        """
        Check if a token is expired.
        
        Args:
            expires_at: Unix timestamp when token expires
            
        Returns:
            True if token is expired or will expire in next 5 minutes
        """
        # Add 5 minute buffer to refresh before actual expiry
        return int(time.time()) >= (expires_at - 300)
    
    @staticmethod
    def validate_oauth_config(config: Dict) -> bool:
        """
        Validate OAuth configuration.
        
        Args:
            config: OAuth configuration dictionary
            
        Returns:
            True if configuration is valid
        """
        required_fields = ['id_token', 'refresh_token', 'expires_at', 'provider']
        return all(field in config for field in required_fields)


def perform_oauth_login(oid: Optional[str] = None, 
                       environment: Optional[str] = None,
                       no_browser: bool = False) -> bool:
    """
    Perform OAuth login and save credentials.
    
    Args:
        oid: Organization ID (optional)
        environment: Environment name (optional)
        no_browser: If True, print URL instead of opening browser
        
    Returns:
        True if login successful
    """
    try:
        # Initialize OAuth manager
        oauth_mgr = OAuthManager()
        
        # Perform OAuth flow
        tokens = oauth_mgr.start_oauth_flow(no_browser=no_browser)
        
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
        
        # Save to appropriate location
        if environment:
            # Save to named environment
            if 'env' not in config:
                config['env'] = {}
            if environment not in config['env']:
                config['env'][environment] = {}
            config['env'][environment].update(oauth_data)
            print(f"\nOAuth credentials saved to environment: {environment}")
        else:
            # Save to default
            config.update(oauth_data)
            print("\nOAuth credentials saved as default")
        
        # Write config
        utils.writeCredentialsToConfig(
            config.get('oid'),
            config.get('api_key'),
            config.get('uid'),
            environment=environment,
            oauth_creds=oauth_data.get('oauth')
        )
        
        return True
        
    except OAuthError as e:
        print(f"\nOAuth login failed: {str(e)}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"\nUnexpected error during OAuth login: {str(e)}", file=sys.stderr)
        return False